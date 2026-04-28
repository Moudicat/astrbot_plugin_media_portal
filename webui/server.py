"""Media Portal WebUI 服务。"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import math
import mimetypes
import secrets
import shutil
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

# CLIP 检索结果的最低展示阈值。
#
# 业界经验：OpenCLIP / CN-CLIP / OpenAI CLIP ViT-B 系列在 cosine 归一化后的
# 「弱相关」阈值大约落在 0.22 附近，低于该值基本是噪声。这里默认裁掉「仅供参考」
# 档（< 0.22）以及任何非有限值（NaN / Inf，多见于早期写入的坏向量），
# 这样前端就不会再展示明显不相关的图片，但仍允许较弱的相关结果（≥0.22）出现。
_CLIP_SCORE_MIN_DISPLAY = 0.22

import aiofiles
import uvicorn
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from starlette.background import BackgroundTask
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from astrbot.api import logger

TEXT_PREVIEW_EXTENSIONS: set[str] = {
    ".txt",
    ".log",
    ".md",
    ".markdown",
    ".json",
    ".json5",
    ".jsonl",
    ".ndjson",
    ".xml",
    ".html",
    ".htm",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".conf",
    ".cfg",
    ".env",
    ".properties",
    ".csv",
    ".tsv",
    ".sql",
    ".py",
    ".pyi",
    ".pyx",
    ".js",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".jsx",
    ".vue",
    ".svelte",
    ".css",
    ".scss",
    ".less",
    ".sass",
    ".sh",
    ".bash",
    ".zsh",
    ".fish",
    ".bat",
    ".cmd",
    ".ps1",
    ".rb",
    ".php",
    ".pl",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".kts",
    ".dart",
    ".swift",
    ".c",
    ".h",
    ".cc",
    ".cpp",
    ".cxx",
    ".hpp",
    ".hh",
    ".m",
    ".mm",
    ".lua",
    ".r",
    ".jl",
    ".ex",
    ".exs",
    ".erl",
    ".hs",
    ".tex",
    ".gradle",
    ".groovy",
    ".proto",
    ".dockerfile",
    ".makefile",
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
    ".lock",
    ".map",
    ".srt",
    ".ass",
    ".vtt",
}
TEXT_PREVIEW_FILENAMES: set[str] = {"dockerfile", "makefile"}
TEXT_PREVIEW_MAX_BYTES = 1_500_000

try:
    from astrbot.core.utils.io import get_local_ip_addresses
except Exception:  # pragma: no cover

    def get_local_ip_addresses() -> list[str]:
        return []

from ..core.category_manager import CategoryManager
from ..core.derivatives import DerivativesManager
from ..core.media_manager import DuplicateMediaError, MediaManager, MediaRecord
from ..core.security import TotpStore
from ..core.utils import (
    detect_mime_and_kind,
    generate_password,
    is_container_environment,
    is_docker_bridge_ip,
    is_link_local_ip,
    is_loopback_ip,
    safe_join,
    slugify_category,
    unique_path,
)


def _build_otpauth_qrcode_svg(uri: str) -> str:
    """把 otpauth:// URI 渲染成 SVG 字符串，前端可直接 `v-html` / `<img src=data:image/svg+xml;...>`。

    依赖 ``qrcode[pil]`` 中的纯 Python QRCode 编码器（不依赖 PIL 渲染本身），失败时返回空串，
    前端会降级为只展示 secret 文本 + 手动输入的提示。
    """
    text = str(uri or "").strip()
    if not text:
        return ""
    try:
        import qrcode
        from qrcode.image.svg import SvgPathImage
    except ImportError:
        return ""
    try:
        img = qrcode.make(text, image_factory=SvgPathImage, box_size=10, border=2)
        import io as _io

        buf = _io.BytesIO()
        img.save(buf)
        return buf.getvalue().decode("utf-8")
    except Exception:
        return ""


def _copy_tree_overlay(src: Path, dst: Path) -> None:
    """把 src 目录递归 overlay 到 dst（已存在同名文件会被覆盖，不会删除 dst 额外文件）。"""
    if not src.is_dir():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for entry in src.iterdir():
        target = dst / entry.name
        if entry.is_dir():
            _copy_tree_overlay(entry, target)
        else:
            try:
                if target.exists() and target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
                shutil.copy2(entry, target)
            except Exception as exc:
                logger.warning("恢复媒体文件失败: %s -> %s (%s)", entry, target, exc)


class WebUIServer:
    CAPABILITY_SECRET_FILENAME = ".capability_secret"

    @staticmethod
    def _safe_int(value: Any, default: int, minimum: int = 0) -> int:
        try:
            parsed = int(value)
        except Exception:
            parsed = default
        return max(minimum, parsed)

    @staticmethod
    def _parse_secret_bytes(raw: bytes) -> bytes | None:
        if len(raw) == 32:
            return raw
        text = raw.decode("utf-8", errors="ignore").strip()
        if not text:
            return None
        try:
            decoded = bytes.fromhex(text)
        except ValueError:
            return None
        return decoded if len(decoded) == 32 else None

    def __init__(
        self,
        media_manager: MediaManager,
        category_manager: CategoryManager,
        config: dict[str, Any],
        data_root: Path,
        callback_api_base: str = "",
        intelligence_manager: Any = None,
    ):
        self.media_manager = media_manager
        self.category_manager = category_manager
        self.config = config
        self.intelligence_manager = intelligence_manager
        self.data_root = data_root.resolve()
        self.media_root = self.media_manager.media_root
        # 缩略图目录转由 DerivativesManager 管辖（plugin_data/derivatives/thumbnails）。
        # 单测里 media_manager 可能是 mock，不自带 derivatives，这里做一次兜底构造。
        self._derivatives = getattr(self.media_manager, "derivatives", None)
        if self._derivatives is None:
            plugin_dir = getattr(
                self.media_manager, "plugin_data_dir", None
            ) or (self.media_root.parent / "plugin_data")
            self._derivatives = DerivativesManager(
                media_root=self.media_root,
                plugin_data_dir=Path(plugin_dir),
            )
        self.thumbnail_dir = self._derivatives.thumbnail_dir

        self.host = str(config.get("host", "0.0.0.0") or "0.0.0.0")
        self.port = self._safe_int(config.get("port", 7003) or 7003, 7003, minimum=1)
        self.enabled = bool(config.get("enabled", False))
        self.expose_astrbot_data = bool(config.get("expose_astrbot_data", False))
        self.session_timeout = self._safe_int(
            config.get("session_timeout", 3600) or 3600, 3600, minimum=60
        )
        self.public_base_url = str(config.get("public_base_url", "") or "").strip().rstrip("/")
        self.callback_api_base = str(callback_api_base or "").strip().rstrip("/")
        self.readonly_token_ttl = self._safe_int(
            config.get("readonly_token_ttl", self.session_timeout) or self.session_timeout,
            self.session_timeout,
            minimum=60,
        )
        self.share_url_ttl = self._safe_int(
            config.get("share_url_ttl", 3600) or 3600, 3600, minimum=60
        )
        self.data_token_ttl = self._safe_int(
            config.get("data_token_ttl", self.session_timeout) or self.session_timeout,
            self.session_timeout,
            minimum=60,
        )
        self.allowed_origins = self._parse_allowed_origins(config.get("allowed_origins"))
        self._capability_secret = self._load_or_create_capability_secret()
        self.totp_feature_enabled = bool(config.get("totp_enabled", False))
        # TotpStore 始终持有（即便功能开关关闭也能查询是否曾绑定过），
        # 但路由开关由 totp_feature_enabled & store.enabled 联合决定。
        self._totp_store = TotpStore(
            state_dir=self.media_manager.plugin_data_dir,
            issuer=str(config.get("totp_issuer", "Media Portal") or "Media Portal"),
            account=str(config.get("totp_account", "admin") or "admin"),
        )

        self._access_password = str(config.get("access_password", "") or "").strip()
        self._password_generated = False
        if not self._access_password:
            self._access_password = generate_password(16)
            self._password_generated = True
            logger.warning(
                "Media Portal WebUI 未配置密码，已自动生成随机密码: %s"
                "（建议尽快在配置中设置 access_password 固定密码）。",
                self._access_password,
            )

        self._tokens: dict[str, dict[str, float]] = {}
        self._failed_attempts: dict[str, list[float]] = {}
        self._token_lock = asyncio.Lock()
        self._attempt_lock = asyncio.Lock()

        self._app = FastAPI(title="Media Portal WebUI", version="1.0.0")
        self._server: uvicorn.Server | None = None
        self._server_task: asyncio.Task | None = None
        self._cleanup_task: asyncio.Task | None = None
        self._setup_routes()

    @property
    def app(self) -> FastAPI:
        return self._app

    @property
    def access_password(self) -> str:
        return self._access_password

    @property
    def readonly_token(self) -> str:
        return self._issue_capability_token("media", "*", self.readonly_token_ttl)

    @property
    def password_generated(self) -> bool:
        return self._password_generated

    @property
    def totp_active(self) -> bool:
        """实际是否要在登录时强制 TOTP 二次验证。"""
        return bool(self.totp_feature_enabled and self._totp_store.enabled)

    def _build_intelligence_summary(self) -> dict[str, Any]:
        """对外暴露 intelligence 总开关 + 子能力当前状态。

        - 不强依赖 ``IntelligenceManager`` 已挂载，缺失时返回禁用占位，前端会按
          ``feature_enabled=false`` 隐藏入口。
        - 子能力是否「真正可用」取决于：
            (1) feature_enabled；
            (2) 对应 *_enabled 子开关；
            (3) 模型在磁盘上的状态为 ``ready``。
        """
        manager = self.intelligence_manager
        if manager is None:
            return {
                "feature_enabled": False,
                "clip_enabled": False,
                "face_enabled": False,
                "clip_ready": False,
                "face_ready": False,
                "hf_mirror_url": "",
            }
        snapshots = manager.snapshots()
        clip_ready = any(
            snap.capability == "clip" and snap.status.value == "ready"
            for snap in snapshots
        )
        face_ready = any(
            snap.capability == "face" and snap.status.value == "ready"
            for snap in snapshots
        )
        return {
            "feature_enabled": manager.feature_enabled,
            "clip_enabled": manager.clip_enabled,
            "face_enabled": manager.face_enabled,
            "clip_ready": clip_ready and manager.clip_enabled,
            "face_ready": face_ready and manager.face_enabled,
            "hf_mirror_url": manager.hf_mirror_url,
        }

    async def _get_trash_retention_days(self) -> int:
        getter = getattr(self.media_manager, "get_trash_retention_days", None)
        if callable(getter):
            try:
                return max(1, int(await getter()))
            except Exception:
                return 30
        return 30

    async def _set_trash_retention_days(self, days: int) -> int:
        setter = getattr(self.media_manager, "set_trash_retention_days", None)
        normalized = max(1, min(3650, int(days)))
        if callable(setter):
            return max(1, int(await setter(normalized)))
        return normalized

    def _capability_secret_path(self) -> Path:
        return (self.media_manager.plugin_data_dir / self.CAPABILITY_SECRET_FILENAME).resolve()

    def _load_or_create_capability_secret(self) -> bytes:
        secret_path = self._capability_secret_path()
        try:
            if secret_path.exists() and secret_path.is_file():
                parsed = self._parse_secret_bytes(secret_path.read_bytes())
                if parsed is not None:
                    return parsed
                logger.warning("capability secret 文件无效，将重新生成: %s", secret_path)

            secret = secrets.token_bytes(32)
            secret_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = secret_path.parent / f"{secret_path.name}.tmp"
            tmp_path.write_text(secret.hex(), encoding="utf-8")
            tmp_path.replace(secret_path)
            return secret
        except Exception as exc:
            logger.warning("capability secret 持久化失败，回退临时 secret: %s", exc)
            return secrets.token_bytes(32)

    @staticmethod
    def _parse_allowed_origins(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            tokens = [item.strip() for item in value.replace(";", ",").split(",")]
            return [item for item in tokens if item]
        if isinstance(value, (list, tuple, set)):
            result: list[str] = []
            for item in value:
                text = str(item).strip()
                if text:
                    result.append(text)
            return result
        text = str(value).strip()
        return [text] if text else []

    async def start(self) -> None:
        if self._server_task and not self._server_task.done():
            return
        config = uvicorn.Config(
            app=self._app,
            host=self.host,
            port=self.port,
            loop="asyncio",
            lifespan="on",
            log_level="warning",
        )
        self._server = uvicorn.Server(config)
        self._server_task = asyncio.create_task(self._server.serve())
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

        for _ in range(50):
            if getattr(self._server, "started", False):
                logger.info("Media Portal WebUI 已启动: %s", self.get_preferred_base_url())
                for note in self.get_environment_notes():
                    logger.warning("Media Portal WebUI 部署提示: %s", note)
                return
            if self._server_task.done():
                error = self._server_task.exception()
                raise RuntimeError(f"WebUI 启动失败: {error}") from error
            await asyncio.sleep(0.1)
        # 5 秒内未就绪：让调用方明确感知，而不是静默返回一个不可用的 server。
        raise TimeoutError("Media Portal WebUI 在 5 秒内未就绪，启动可能失败。")

    async def stop(self) -> None:
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        if self._server:
            self._server.should_exit = True
        if self._server_task:
            try:
                await asyncio.wait_for(self._server_task, timeout=10)
            except asyncio.TimeoutError:
                logger.warning("WebUI 在 10 秒内未能优雅停止，强制取消。")
                self._server_task.cancel()
                try:
                    await self._server_task
                except (asyncio.CancelledError, Exception):
                    pass
        self._cleanup_task = None
        self._server_task = None
        self._server = None

    async def rotate_password(self, password: str | None = None) -> str:
        """重置 WebUI 访问密码。

        传入非空字符串会固定为该密码；传入 ``None`` 或空字符串则随机生成一个。
        重置完成后会清理所有现有会话 token，强制重新登录。
        """
        candidate = (password or "").strip()
        new_password = candidate or generate_password(16)
        self._access_password = new_password
        self._password_generated = not bool(candidate)
        async with self._token_lock:
            self._tokens.clear()
        if self._password_generated:
            logger.warning(
                "Media Portal WebUI 已重置为随机密码: %s",
                new_password,
            )
        else:
            logger.info("Media Portal WebUI 密码已更新（由配置指定）。")
        return self._access_password

    def _classify_access_ips(self) -> dict[str, list[str]]:
        """扫描本机网卡 IP 并按用途分组。"""
        lan_ips: list[str] = []
        container_ips: list[str] = []
        for ip in get_local_ip_addresses():
            if not ip:
                continue
            if is_loopback_ip(ip) or is_link_local_ip(ip):
                continue
            if is_docker_bridge_ip(ip):
                container_ips.append(ip)
            else:
                lan_ips.append(ip)
        return {"lan": lan_ips, "container": container_ips}

    def get_access_urls(self, include_container: bool | None = None) -> list[str]:
        """构造 WebUI 访问地址列表。

        - 始终包含 localhost / 127.0.0.1，便于宿主机直接访问。
        - 默认过滤掉疑似 Docker 网桥 IP（172.17-172.31），除非没有其它可用 IP。
        - 配置了 ``public_base_url`` 时把它放在最前面。
        """
        urls: list[str] = []
        if self.public_base_url:
            urls.append(self.public_base_url)
        urls.append(f"http://localhost:{self.port}")
        urls.append(f"http://127.0.0.1:{self.port}")

        if self.host not in {"0.0.0.0", "::"} and self.host not in {"127.0.0.1", "localhost"}:
            urls.append(f"http://{self.host}:{self.port}")
        else:
            groups = self._classify_access_ips()
            for ip in groups["lan"]:
                urls.append(f"http://{ip}:{self.port}")
            # 仅在没有普通局域网 IP，或调用方显式要求时，才输出疑似容器内部 IP。
            should_include_container = (
                include_container
                if include_container is not None
                else not groups["lan"]
            )
            if should_include_container:
                for ip in groups["container"]:
                    urls.append(f"http://{ip}:{self.port}")

        dedup: list[str] = []
        seen: set[str] = set()
        for url in urls:
            if url in seen:
                continue
            seen.add(url)
            dedup.append(url)
        return dedup

    def get_environment_notes(self) -> list[str]:
        """返回与部署环境相关的人类可读提示。"""
        notes: list[str] = []
        groups = self._classify_access_ips()
        in_container = is_container_environment()
        has_container_ip = bool(groups["container"])
        has_lan_ip = bool(groups["lan"])
        if not self.public_base_url and (in_container or (has_container_ip and not has_lan_ip)):
            notes.append(
                "检测到当前进程可能运行在容器（Docker / K8s 等）中，"
                "局域网/外网通常无法直接访问容器内部 IP（如 172.17.x.x）。"
            )
            if has_container_ip:
                container_preview = ", ".join(groups["container"][:3])
                notes.append(f"已忽略疑似容器内部地址: {container_preview}。")
            notes.append(
                "建议在插件配置的 webui.public_base_url 中填写可从外部访问的地址"
                "（例如 http://<宿主机IP>:<映射端口> 或反向代理域名），"
                "以便 URL/分享链接正确指向公开入口。"
            )
        return notes

    def get_preferred_base_url(self) -> str:
        if self.public_base_url:
            return self.public_base_url
        if self.host in {"0.0.0.0", "::"}:
            groups = self._classify_access_ips()
            if groups["lan"]:
                return f"http://{groups['lan'][0]}:{self.port}"
            if groups["container"]:
                return f"http://{groups['container'][0]}:{self.port}"
            return f"http://localhost:{self.port}"
        if self.host in {"127.0.0.1", "localhost"}:
            return f"http://localhost:{self.port}"
        return f"http://{self.host}:{self.port}"

    @staticmethod
    def _b64url_encode(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @staticmethod
    def _b64url_decode(text: str) -> bytes:
        padding = "=" * (-len(text) % 4)
        return base64.urlsafe_b64decode((text + padding).encode("ascii"))

    def _issue_capability_token(self, scope: str, subject: str, ttl_seconds: int) -> str:
        now = int(time.time())
        payload = {
            "scp": scope,
            "sub": subject,
            "iat": now,
            "exp": now + max(60, int(ttl_seconds)),
        }
        payload_raw = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        payload_b64 = self._b64url_encode(payload_raw)
        signature = hmac.new(
            self._capability_secret,
            payload_b64.encode("ascii"),
            hashlib.sha256,
        ).digest()
        return f"{payload_b64}.{self._b64url_encode(signature)}"

    def _decode_capability_payload(self, token: str) -> dict[str, Any] | None:
        token_text = str(token or "").strip()
        if not token_text or "." not in token_text:
            return None
        payload_b64, signature_b64 = token_text.split(".", 1)
        if not payload_b64 or not signature_b64:
            return None
        expected_signature = hmac.new(
            self._capability_secret,
            payload_b64.encode("ascii"),
            hashlib.sha256,
        ).digest()
        expected_b64 = self._b64url_encode(expected_signature)
        if not hmac.compare_digest(signature_b64, expected_b64):
            return None
        try:
            payload = json.loads(self._b64url_decode(payload_b64).decode("utf-8"))
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        try:
            exp = int(payload.get("exp", 0) or 0)
        except Exception:
            return None
        if exp < int(time.time()):
            return None
        return payload

    def _validate_capability_token(self, token: str, *, scope: str, subject: str) -> bool:
        payload = self._decode_capability_payload(token)
        if not payload:
            return False
        if str(payload.get("scp", "")) != scope:
            return False
        token_subject = str(payload.get("sub", ""))
        return token_subject in {"*", subject}

    def build_media_url(self, record: MediaRecord) -> str:
        base_url = self.get_preferred_base_url()
        rel_path = str(record.rel_path or f"{record.category}/{record.filename}")
        token = self._issue_capability_token("media", rel_path, self.share_url_ttl)
        return (
            f"{base_url}/files/{quote(record.category)}/{quote(record.filename)}"
            f"?token={quote(token)}"
        )

    async def _periodic_cleanup(self) -> None:
        # 周期与 session_timeout 联动，避免会话窗口过短时清理滞后。
        interval = max(30, min(300, self.session_timeout))
        while True:
            try:
                await asyncio.sleep(interval)
                async with self._token_lock:
                    self._cleanup_tokens_locked()
                async with self._attempt_lock:
                    self._cleanup_attempts_locked()
                purge = getattr(self.media_manager, "purge_expired_trash", None)
                if callable(purge):
                    retention_days = await self._get_trash_retention_days()
                    try:
                        await purge(retention_days=retention_days)
                    except TypeError:
                        await purge()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("WebUI 周期清理失败: %s", exc)

    def _cleanup_tokens_locked(self) -> None:
        now = time.time()
        expired: list[str] = []
        for token, info in self._tokens.items():
            created = info.get("created_at", 0.0)
            active = info.get("last_active", 0.0)
            if now - created > 86400:
                expired.append(token)
                continue
            if now - active > self.session_timeout:
                expired.append(token)
        for token in expired:
            self._tokens.pop(token, None)

    def _cleanup_attempts_locked(self) -> None:
        now = time.time()
        ips_to_remove: list[str] = []
        for ip, records in self._failed_attempts.items():
            fresh = [item for item in records if now - item < 300]
            if fresh:
                self._failed_attempts[ip] = fresh
            else:
                ips_to_remove.append(ip)
        for ip in ips_to_remove:
            self._failed_attempts.pop(ip, None)

    async def _check_rate_limit(self, client_ip: str) -> bool:
        async with self._attempt_lock:
            self._cleanup_attempts_locked()
            records = self._failed_attempts.get(client_ip, [])
            return len(records) < 5

    async def _record_failed_attempt(self, client_ip: str) -> bool:
        async with self._attempt_lock:
            self._cleanup_attempts_locked()
            records = self._failed_attempts.setdefault(client_ip, [])
            if len(records) >= 5:
                return False
            records.append(time.time())
            return True

    async def _clear_failed_attempts(self, client_ip: str) -> None:
        async with self._attempt_lock:
            self._failed_attempts.pop(client_ip, None)

    async def _issue_login_session(self) -> dict[str, Any]:
        """登录密码 / TOTP 都通过后，构造完整的会话 token + capability token 响应。"""
        token = secrets.token_urlsafe(32)
        now = time.time()
        async with self._token_lock:
            self._cleanup_tokens_locked()
            self._tokens[token] = {
                "created_at": now,
                "last_active": now,
            }
        media_token = self._issue_capability_token(
            "media", "*", self.readonly_token_ttl
        )
        data_token = (
            self._issue_capability_token("data", "*", self.data_token_ttl)
            if self.expose_astrbot_data
            else ""
        )
        return {
            "token": token,
            "expires_in": self.session_timeout,
            "readonly_token": media_token,
            "readonly_expires_in": self.readonly_token_ttl,
            "data_token": data_token,
            "data_expires_in": self.data_token_ttl if self.expose_astrbot_data else 0,
            "base_url": self.get_preferred_base_url(),
        }

    def _extract_token(self, request: Request) -> str:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        return request.headers.get("X-Auth-Token", "")

    async def _validate_token(self, token: str) -> str:
        if not token:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="缺少认证 token")
        async with self._token_lock:
            info = self._tokens.get(token)
            if not info:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="token 无效")
            now = time.time()
            created = info.get("created_at", 0.0)
            active = info.get("last_active", 0.0)
            if now - created > 86400:
                self._tokens.pop(token, None)
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="token 已过期")
            if now - active > self.session_timeout:
                self._tokens.pop(token, None)
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="会话超时")
            info["last_active"] = now
        return token

    def _auth_dependency(self):
        async def dependency(request: Request) -> str:
            token = self._extract_token(request)
            return await self._validate_token(token)

        return dependency

    async def _can_access_media_file(self, request: Request, subject: str) -> bool:
        token = request.query_params.get("token", "")
        if token and self._validate_capability_token(token, scope="media", subject=subject):
            return True
        bearer = self._extract_token(request)
        if not bearer:
            return False
        try:
            await self._validate_token(bearer)
            return True
        except HTTPException:
            return False

    async def _can_access_data_file(self, request: Request, subject: str) -> bool:
        token = request.query_params.get("token", "")
        if token and self._validate_capability_token(token, scope="data", subject=subject):
            return True
        bearer = self._extract_token(request)
        if not bearer:
            return False
        try:
            await self._validate_token(bearer)
            return True
        except HTTPException:
            return False

    def _resolve_data_path(self, raw_path: str) -> Path:
        normalized = str(raw_path or "").strip().lstrip("/")
        return safe_join(self.data_root, normalized)

    def _thumbnail_target(self, source: Path, size: int) -> Path:
        """兼容旧调用：把磁盘路径换算成衍生缩略图缓存位置。"""
        rel = source.resolve().relative_to(self.media_root).as_posix()
        return self._derivatives.thumbnail_path(rel, size)

    async def _ensure_thumbnail(self, source: Path, size: int) -> Path:
        """保留历史签名（图片）；内部委托 DerivativesManager 完成生成。"""
        rel = source.resolve().relative_to(self.media_root).as_posix()
        target = await self._derivatives.ensure_thumbnail(rel, size, kind="image")
        if target is None:
            raise RuntimeError(f"生成缩略图失败: {rel}")
        return target

    async def _ensure_thumbnail_for_record(
        self, source: Path, size: int, *, kind: str
    ) -> Path | None:
        rel = source.resolve().relative_to(self.media_root).as_posix()
        return await self._derivatives.ensure_thumbnail(rel, size, kind=kind)

    def _build_data_item(self, path: Path) -> dict[str, Any]:
        try:
            is_dir = path.is_dir()
        except OSError:
            is_dir = False
        try:
            rel_path = path.resolve().relative_to(self.data_root).as_posix()
        except Exception:
            rel_path = path.name
        if rel_path == ".":
            rel_path = ""
        try:
            size = 0 if is_dir else path.stat().st_size
        except OSError:
            size = 0
        if is_dir:
            mime, kind = ("", "folder")
        else:
            try:
                mime, kind = detect_mime_and_kind(path)
            except OSError:
                mime, kind = ("application/octet-stream", "other")
        return {
            "name": path.name,
            "path": rel_path,
            "is_dir": is_dir,
            "size": size,
            "mime": mime,
            "kind": kind,
        }

    async def _create_backup_archive(self, *, include_media: bool) -> FileResponse:
        """打包 index.db + categories.json + (可选) media 目录 为 tar.gz 并以 FileResponse 返回。

        生成的临时归档会在响应发送完成后由 BackgroundTask 清理。
        """
        categories_file = getattr(self.category_manager, "categories_file", None)
        db_path: Path = getattr(self.media_manager, "db_path", self.media_manager.plugin_data_dir / "index.db")
        media_root: Path = self.media_root
        trash_root: Path = getattr(
            self.media_manager,
            "trash_root",
            self.media_manager.plugin_data_dir / "trash",
        )

        stamp = time.strftime("%Y%m%d-%H%M%S")
        suffix = "full" if include_media else "meta"
        base_name = f"media-portal-backup-{stamp}-{suffix}.tar.gz"

        tmp_dir = Path(tempfile.mkdtemp(prefix="media_portal_backup_"))
        archive_path = tmp_dir / base_name

        def _build_archive() -> None:
            try:
                with tarfile.open(archive_path, "w:gz", compresslevel=5) as tar:
                    manifest: dict[str, Any] = {
                        "version": 1,
                        "created_at": int(time.time()),
                        "has_media": bool(include_media),
                    }
                    if db_path and db_path.exists() and db_path.is_file():
                        tar.add(db_path, arcname="index.db")
                        manifest["has_db"] = True
                    if (
                        categories_file
                        and isinstance(categories_file, Path)
                        and categories_file.exists()
                        and categories_file.is_file()
                    ):
                        tar.add(categories_file, arcname="categories.json")
                        manifest["has_categories"] = True
                    if include_media and media_root and media_root.exists() and media_root.is_dir():
                        tar.add(media_root, arcname="media")
                    if include_media and trash_root and trash_root.exists() and trash_root.is_dir():
                        tar.add(trash_root, arcname="trash")
                        manifest["has_trash"] = True

                    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
                    info = tarfile.TarInfo(name="manifest.json")
                    info.size = len(manifest_bytes)
                    info.mtime = int(time.time())
                    import io as _io

                    tar.addfile(info, _io.BytesIO(manifest_bytes))
            except Exception:
                shutil.rmtree(tmp_dir, ignore_errors=True)
                raise

        try:
            await asyncio.to_thread(_build_archive)
        except Exception as exc:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"生成备份失败: {exc}",
            ) from exc

        def _cleanup() -> None:
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

        response = FileResponse(
            path=archive_path,
            media_type="application/gzip",
            filename=base_name,
            background=BackgroundTask(_cleanup),
        )
        response.headers["Content-Disposition"] = (
            f"attachment; filename*=UTF-8''{quote(base_name)}"
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    async def _restore_backup_archive(
        self,
        *,
        upload: UploadFile,
        replace_media: bool,
    ) -> dict[str, Any]:
        """从上传的 tar.gz 恢复 index.db / categories.json / media 目录。

        - ``replace_media=True`` 时会先清空 ``media_root`` 再解压归档内的 ``media/``；
        - 为 False 则只覆盖同名文件，保留当前磁盘上多出来的文件（更安全）。
        恢复过程中 DB 连接会被关闭，完成后重新初始化。
        """
        staging_root = Path(tempfile.mkdtemp(prefix="media_portal_restore_"))
        archive_path = staging_root / "upload.tar.gz"
        extracted_root = staging_root / "extracted"
        extracted_root.mkdir(parents=True, exist_ok=True)

        try:
            bytes_written = 0
            hard_limit = 20 * 1024 * 1024 * 1024  # 20GB 上限，避免磁盘写爆
            try:
                async with aiofiles.open(archive_path, "wb") as fp:
                    while True:
                        chunk = await upload.read(1024 * 1024)
                        if not chunk:
                            break
                        bytes_written += len(chunk)
                        if bytes_written > hard_limit:
                            raise HTTPException(
                                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                detail="备份文件过大",
                            )
                        await fp.write(chunk)
            finally:
                await upload.close()

            if bytes_written == 0:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="空文件")

            def _extract_safe() -> None:
                with tarfile.open(archive_path, "r:gz") as tar:
                    members = []
                    for member in tar.getmembers():
                        name = member.name.replace("\\", "/").lstrip("/")
                        if not name or name.startswith("../") or "/../" in name:
                            continue
                        member.name = name
                        members.append(member)
                    tar.extractall(extracted_root, members=members)

            try:
                await asyncio.to_thread(_extract_safe)
            except tarfile.TarError as exc:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"归档格式非法: {exc}",
                ) from exc

            has_db = (extracted_root / "index.db").exists()
            has_categories = (extracted_root / "categories.json").exists()
            has_media_dir = (extracted_root / "media").exists() and (extracted_root / "media").is_dir()
            has_trash_dir = (extracted_root / "trash").exists() and (extracted_root / "trash").is_dir()

            if not (has_db or has_categories or has_media_dir or has_trash_dir):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="归档中未包含 index.db / categories.json / media / trash，无法恢复",
                )

            try:
                await self.media_manager.close()
            except Exception as exc:
                logger.warning("关闭媒体索引数据库失败，继续恢复: %s", exc)

            restored: list[str] = []

            try:
                if has_db:
                    target_db = Path(self.media_manager.db_path)
                    target_db.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(extracted_root / "index.db", target_db)
                    restored.append("index.db")

                if has_categories:
                    categories_file = getattr(self.category_manager, "categories_file", None)
                    if isinstance(categories_file, Path):
                        categories_file.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(extracted_root / "categories.json", categories_file)
                        restored.append("categories.json")

                if has_media_dir:
                    target_media = self.media_root
                    if replace_media and target_media.exists():
                        for child in target_media.iterdir():
                            try:
                                if child.is_dir():
                                    shutil.rmtree(child, ignore_errors=True)
                                else:
                                    child.unlink(missing_ok=True)
                            except Exception as exc:
                                logger.warning("清理旧媒体目录项失败: %s (%s)", child, exc)
                    target_media.mkdir(parents=True, exist_ok=True)
                    _copy_tree_overlay(extracted_root / "media", target_media)
                    restored.append("media/")
                if has_trash_dir:
                    target_trash = getattr(
                        self.media_manager,
                        "trash_root",
                        self.media_manager.plugin_data_dir / "trash",
                    )
                    target_trash = Path(target_trash)
                    if replace_media and target_trash.exists():
                        for child in target_trash.iterdir():
                            try:
                                if child.is_dir():
                                    shutil.rmtree(child, ignore_errors=True)
                                else:
                                    child.unlink(missing_ok=True)
                            except Exception as exc:
                                logger.warning("清理旧回收站目录项失败: %s (%s)", child, exc)
                    target_trash.mkdir(parents=True, exist_ok=True)
                    _copy_tree_overlay(extracted_root / "trash", target_trash)
                    restored.append("trash/")
            finally:
                try:
                    await self.media_manager.initialize()
                except Exception as exc:
                    logger.error("恢复后重新初始化数据库失败: %s", exc)
                try:
                    self.category_manager._load()  # type: ignore[attr-defined]
                    self.category_manager.sync_with_filesystem()
                except Exception as exc:
                    logger.warning("恢复后刷新 category_manager 失败: %s", exc)

            return {
                "restored": restored,
                "replace_media": bool(replace_media),
                "bytes": bytes_written,
            }
        finally:
            shutil.rmtree(staging_root, ignore_errors=True)

    def _setup_routes(self) -> None:
        static_root = Path(__file__).resolve().parent / "static"
        index_file = static_root / "index.html"

        if self.allowed_origins:
            self._app.add_middleware(
                CORSMiddleware,
                allow_origins=self.allowed_origins,
                allow_credentials=False,
                allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
                allow_headers=["Authorization", "Content-Type", "X-Auth-Token"],
            )

        if static_root.exists():
            self._app.mount("/static", StaticFiles(directory=static_root), name="static")

            # 对 /static/*.(html|js|mjs|css) 响应追加 no-cache 头（走 ETag 协商），
            # 避免浏览器 / 反代 / CDN 长时间强缓存旧版本；图片、字体、vendor 等
            # 其它资源保持默认行为。
            _no_cache_suffixes = (".html", ".htm", ".js", ".mjs", ".css")

            @self._app.middleware("http")
            async def _static_no_cache_middleware(request: Request, call_next):
                response = await call_next(request)
                try:
                    path = request.url.path or ""
                except Exception:
                    path = ""
                if path.startswith("/static/") and path.lower().endswith(_no_cache_suffixes):
                    response.headers["Cache-Control"] = "no-cache, must-revalidate"
                    if "Expires" in response.headers:
                        del response.headers["Expires"]
                return response

        @self._app.get("/", response_class=HTMLResponse)
        async def index_page() -> HTMLResponse:
            # 产物由 Vite 构建生成，文件名自带 hash 指纹，无需再做 URL 重写。
            if not index_file.exists():
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND,
                    detail="前端文件不存在，请先在 webui/frontend 下执行 `bun install && bun run build`",
                )
            html = index_file.read_text(encoding="utf-8")
            response = HTMLResponse(html)
            # index.html 本身永不缓存，保证每次都能拿到最新的 hash 指纹文件。
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response

        @self._app.get("/api/health")
        async def health() -> dict[str, Any]:
            return {"status": "ok", "service": "media_portal_webui", "version": "1.0.0"}

        @self._app.post("/api/login")
        async def login(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
            password = str(payload.get("password", "") or "").strip()
            if not password:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="密码不能为空")
            client_ip = request.client.host if request.client else "unknown"
            if not hmac.compare_digest(
                password.encode("utf-8"),
                self._access_password.encode("utf-8"),
            ):
                accepted = await self._record_failed_attempt(client_ip)
                await asyncio.sleep(0.6)
                if not accepted:
                    raise HTTPException(
                        status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="尝试过于频繁，请稍后再试",
                    )
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="认证失败")
            await self._clear_failed_attempts(client_ip)

            if self.totp_active:
                # TOTP 已启用：先发短期 challenge_token，前端跳到第二步收集 6 位码。
                challenge = self._issue_capability_token("login_totp", "*", 300)
                return {
                    "challenge": "totp",
                    "challenge_token": challenge,
                    "expires_in": 300,
                    "issuer": self._totp_store.state.issuer,
                    "account": self._totp_store.state.account,
                }
            return await self._issue_login_session()

        @self._app.post("/api/login/totp")
        async def login_totp(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
            challenge_token = str(payload.get("challenge_token", "") or "").strip()
            code = str(payload.get("code", "") or "").strip()
            recovery_code = str(payload.get("recovery_code", "") or "").strip()
            client_ip = request.client.host if request.client else "unknown"

            if not challenge_token:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, detail="缺少 challenge_token"
                )
            if not code and not recovery_code:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, detail="请输入 6 位验证码或恢复码"
                )
            if not self._validate_capability_token(
                challenge_token, scope="login_totp", subject="*"
            ):
                raise HTTPException(
                    status.HTTP_401_UNAUTHORIZED, detail="登录会话已过期，请重新输入密码"
                )
            if not self.totp_active:
                # 例如管理员在 challenge 期间关闭了 TOTP，此时直接放行。
                return await self._issue_login_session()

            ok = False
            if code:
                ok = await self._totp_store.verify_code(code)
            if not ok and recovery_code:
                ok = await self._totp_store.consume_recovery_code(recovery_code)
            if not ok:
                accepted = await self._record_failed_attempt(client_ip)
                await asyncio.sleep(0.6)
                if not accepted:
                    raise HTTPException(
                        status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="尝试过于频繁，请稍后再试",
                    )
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="验证码错误")
            await self._clear_failed_attempts(client_ip)
            return await self._issue_login_session()

        @self._app.get("/api/account/totp/status")
        async def get_totp_status(
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            return {
                "feature_enabled": self.totp_feature_enabled,
                **self._totp_store.public_status(),
            }

        @self._app.post("/api/account/totp/setup")
        async def post_totp_setup(
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            if not self.totp_feature_enabled:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="未启用 TOTP 功能，请先在插件配置中开启 webui.totp_enabled。",
                )
            try:
                payload = await self._totp_store.begin_setup()
            except RuntimeError as exc:
                raise HTTPException(
                    status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
                ) from exc
            payload["qrcode_svg"] = _build_otpauth_qrcode_svg(payload["otpauth_uri"])
            return payload

        @self._app.post("/api/account/totp/confirm")
        async def post_totp_confirm(
            payload: dict[str, Any],
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            try:
                return await self._totp_store.confirm_setup(
                    str(payload.get("code", "") or "")
                )
            except RuntimeError as exc:
                raise HTTPException(
                    status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
                ) from exc
            except ValueError as exc:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, detail=str(exc)
                ) from exc

        @self._app.post("/api/account/totp/cancel-setup")
        async def post_totp_cancel_setup(
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            await self._totp_store.cancel_setup()
            return {"cancelled": True}

        @self._app.post("/api/account/totp/disable")
        async def post_totp_disable(
            payload: dict[str, Any],
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            code = str(payload.get("code", "") or "").strip()
            recovery_code = str(payload.get("recovery_code", "") or "").strip()
            try:
                await self._totp_store.disable(
                    code=code or None, recovery_code=recovery_code or None
                )
            except ValueError as exc:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, detail=str(exc)
                ) from exc
            return {"enabled": False}

        @self._app.post("/api/account/totp/regenerate-recovery")
        async def post_totp_regen_recovery(
            payload: dict[str, Any],
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            code = str(payload.get("code", "") or "").strip()
            try:
                codes = await self._totp_store.regenerate_recovery_codes(code=code)
            except ValueError as exc:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, detail=str(exc)
                ) from exc
            return {"recovery_codes": codes, "remaining_recovery_codes": len(codes)}

        @self._app.post("/api/logout")
        async def logout(token: str = Depends(self._auth_dependency())) -> dict[str, str]:
            async with self._token_lock:
                self._tokens.pop(token, None)
            return {"message": "ok"}

        @self._app.get("/api/config")
        async def get_config(token: str = Depends(self._auth_dependency())) -> dict[str, Any]:
            _ = token
            max_bytes = int(getattr(self.media_manager, "max_file_size", 0) or 0)
            max_mb = max_bytes // (1024 * 1024) if max_bytes > 0 else 0
            trash_retention_days = await self._get_trash_retention_days()
            media_token = self._issue_capability_token(
                "media", "*", self.readonly_token_ttl
            )
            data_token = (
                self._issue_capability_token("data", "*", self.data_token_ttl)
                if self.expose_astrbot_data
                else ""
            )
            return {
                "host": self.host,
                "port": self.port,
                "public_base_url": self.get_preferred_base_url(),
                "access_urls": self.get_access_urls(),
                "allowed_origins": self.allowed_origins,
                "readonly_token": media_token,
                "readonly_expires_in": self.readonly_token_ttl,
                "data_token": data_token,
                "data_expires_in": self.data_token_ttl if self.expose_astrbot_data else 0,
                "expose_astrbot_data": self.expose_astrbot_data,
                "password_generated": self._password_generated,
                "max_file_size_mb": max_mb,
                "max_file_size_bytes": max_bytes,
                "trash_retention_days": trash_retention_days,
                "totp_feature_enabled": self.totp_feature_enabled,
                "totp_active": self.totp_active,
                "intelligence": self._build_intelligence_summary(),
            }

        @self._app.get("/api/settings/trash")
        async def get_trash_settings(
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            return {"trash_retention_days": await self._get_trash_retention_days()}

        @self._app.patch("/api/settings/trash")
        async def patch_trash_settings(
            payload: dict[str, Any],
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            days = payload.get("trash_retention_days")
            if days is None:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="trash_retention_days 不能为空",
                )
            try:
                normalized = await self._set_trash_retention_days(int(days))
            except Exception as exc:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"trash_retention_days 无效: {exc}",
                ) from exc
            return {"trash_retention_days": normalized}

        @self._app.get("/api/stats")
        async def stats(token: str = Depends(self._auth_dependency())) -> dict[str, Any]:
            _ = token
            return await self.media_manager.get_stats()

        @self._app.get("/api/categories")
        async def categories(token: str = Depends(self._auth_dependency())) -> dict[str, Any]:
            _ = token
            stats_payload = await self.media_manager.get_stats()
            return {"items": stats_payload.get("categories", [])}

        @self._app.post("/api/categories")
        async def create_category(
            payload: dict[str, Any], token: str = Depends(self._auth_dependency())
        ) -> dict[str, Any]:
            _ = token
            name = str(payload.get("category", "") or "").strip()
            if not name:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="category 不能为空")
            desc = str(payload.get("description", "") or "").strip()
            normalized = await self.media_manager.create_category(name, desc)
            return {"category": normalized, "description": self.category_manager.get_description(normalized)}

        @self._app.patch("/api/categories/{category}")
        async def patch_category(
            category: str,
            payload: dict[str, Any],
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            current = slugify_category(category)
            new_name = str(payload.get("new_name", "") or "").strip()
            description = payload.get("description")
            target = current
            if new_name:
                ok, result = await self.media_manager.rename_category(current, new_name)
                if not ok:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=result)
                target = result
            if description is not None:
                self.category_manager.set_description(target, str(description))
            return {"category": target, "description": self.category_manager.get_description(target)}

        @self._app.delete("/api/categories/{category}")
        async def remove_category(
            category: str,
            remove_files: bool = True,
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            return await self.media_manager.delete_category(category, remove_files=remove_files)

        @self._app.post("/api/categories/prune")
        async def prune_categories(
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            return await self.media_manager.prune_empty_categories()

        @self._app.get("/api/media")
        async def list_media(
            category: str = "",
            kind: str = "",
            query: str = "",
            page: int = 1,
            page_size: int = 20,
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            return await self.media_manager.list_media(
                category=category,
                kind=kind,
                query=query,
                page=page,
                page_size=page_size,
            )

        @self._app.get("/api/media/duplicates")
        async def list_duplicate_media(
            mode: str = "exact",
            page: int = 1,
            page_size: int = 20,
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            list_duplicates = getattr(self.media_manager, "list_duplicate_groups", None)
            if not callable(list_duplicates):
                return {
                    "items": [],
                    "total": 0,
                    "page": max(1, int(page)),
                    "page_size": max(1, int(page_size)),
                    "total_pages": 0,
                    "mode": mode,
                }
            return await list_duplicates(
                mode=mode,
                page=page,
                page_size=page_size,
            )

        @self._app.get("/api/media/{media_id}")
        async def get_media(
            media_id: int, token: str = Depends(self._auth_dependency())
        ) -> dict[str, Any]:
            _ = token
            record = await self.media_manager.get_by_id(media_id)
            if not record:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="媒体不存在")
            payload = record.to_dict()
            payload["public_url"] = self.build_media_url(record)
            return payload

        @self._app.patch("/api/media/{media_id}")
        async def update_media(
            media_id: int,
            payload: dict[str, Any],
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            updated = await self.media_manager.update_media(
                media_id,
                description=payload.get("description"),
                tags=payload.get("tags"),
                category=payload.get("category"),
                filename=payload.get("filename"),
            )
            data = updated.to_dict()
            data["public_url"] = self.build_media_url(updated)
            return data

        @self._app.delete("/api/media/{media_id}")
        async def delete_media(
            media_id: int, token: str = Depends(self._auth_dependency())
        ) -> dict[str, Any]:
            _ = token
            trash_media = getattr(self.media_manager, "trash_media", None)
            if callable(trash_media):
                trashed = await trash_media(media_id)
                if not trashed:
                    raise HTTPException(status.HTTP_404_NOT_FOUND, detail="媒体不存在")
                return {"deleted": True, "soft_deleted": True, "trash_id": trashed.id}
            ok = await self.media_manager.delete_media(media_id)
            if not ok:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="媒体不存在")
            return {"deleted": True}

        @self._app.get("/api/trash")
        async def list_trash(
            category: str = "",
            query: str = "",
            page: int = 1,
            page_size: int = 20,
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            list_trash_fn = getattr(self.media_manager, "list_trash", None)
            if not callable(list_trash_fn):
                return {
                    "items": [],
                    "total": 0,
                    "page": max(1, int(page)),
                    "page_size": max(1, int(page_size)),
                    "total_pages": 0,
                }
            data = await list_trash_fn(
                category=category,
                query=query,
                page=page,
                page_size=page_size,
            )
            retention_days = await self._get_trash_retention_days()
            now = time.time()
            for item in data.get("items", []):
                try:
                    deleted_at = float(item.get("deleted_at") or 0)
                except (TypeError, ValueError):
                    deleted_at = 0.0
                expires_at = deleted_at + float(retention_days) * 86400.0 if deleted_at else 0.0
                item["expires_at"] = expires_at
                item["remaining_days"] = (
                    max(0, int((expires_at - now) // 86400)) if expires_at else 0
                )
            return data

        @self._app.get("/api/trash/stats")
        async def trash_stats(
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            stats_fn = getattr(self.media_manager, "get_trash_stats", None)
            if not callable(stats_fn):
                return {
                    "total_count": 0,
                    "total_size": 0,
                    "total_size_human": "0B",
                    "expired_count": 0,
                    "retention_days": await self._get_trash_retention_days(),
                }
            return await stats_fn()

        @self._app.post("/api/trash/{trash_id}/restore")
        async def restore_trash_media(
            trash_id: int,
            payload: dict[str, Any] | None = None,
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            restore_fn = getattr(self.media_manager, "restore_from_trash", None)
            if not callable(restore_fn):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="当前后端不支持回收站恢复")
            body = payload or {}
            try:
                restored = await restore_fn(
                    trash_id,
                    category=str(body.get("category", "") or ""),
                    filename=str(body.get("filename", "") or ""),
                )
            except FileNotFoundError as exc:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
            data = restored.to_dict()
            data["public_url"] = self.build_media_url(restored)
            return data

        @self._app.delete("/api/trash/{trash_id}")
        async def purge_trash_media(
            trash_id: int,
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            purge_fn = getattr(self.media_manager, "purge_trash", None)
            if not callable(purge_fn):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="当前后端不支持回收站删除")
            ok = await purge_fn(trash_id)
            if not ok:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="回收站记录不存在")
            return {"deleted": True}

        @self._app.post("/api/trash/purge-expired")
        async def purge_expired_trash(
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            purge_fn = getattr(self.media_manager, "purge_expired_trash", None)
            if not callable(purge_fn):
                return {"purged": 0}
            retention_days = await self._get_trash_retention_days()
            return await purge_fn(retention_days=retention_days)

        @self._app.post("/api/media/save-url")
        async def save_media_by_url(
            payload: dict[str, Any], token: str = Depends(self._auth_dependency())
        ) -> dict[str, Any]:
            _ = token
            url = str(payload.get("url", "") or "").strip()
            if not url:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="url 不能为空")
            category = str(payload.get("category", "default") or "default")
            description = str(payload.get("description", "") or "")
            filename = str(payload.get("filename", "") or "")
            duplicate_policy = str(payload.get("duplicate_policy", "error") or "error")
            try:
                try:
                    record = await self.media_manager.save_from_url(
                        url,
                        category=category,
                        description=description,
                        filename=filename,
                        duplicate_policy=duplicate_policy,
                    )
                except TypeError:
                    record = await self.media_manager.save_from_url(
                        url,
                        category=category,
                        description=description,
                        filename=filename,
                    )
            except DuplicateMediaError as exc:
                existing = exc.record.to_dict()
                existing["public_url"] = self.build_media_url(exc.record)
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail={
                        "code": "duplicate_sha256",
                        "message": "检测到重复文件",
                        "existing": existing,
                    },
                ) from exc
            data = record.to_dict()
            data["public_url"] = self.build_media_url(record)
            return data

        @self._app.post("/api/media/upload")
        async def upload_media(
            category: str = Form("default"),
            description: str = Form(""),
            duplicate_policy: str = Form("error"),
            files: list[UploadFile] = File(default=[]),
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            if not files:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="未提供上传文件")

            saved: list[dict[str, Any]] = []
            errors: list[str] = []
            duplicates: list[dict[str, Any]] = []
            for upload in files:
                temp_name = unique_path(
                    self.media_manager.downloader.temp_dir
                    / f"upload_{secrets.token_hex(8)}{Path(upload.filename or '').suffix}"
                )
                size = 0
                try:
                    async with aiofiles.open(temp_name, "wb") as fp:
                        while True:
                            chunk = await upload.read(1024 * 64)
                            if not chunk:
                                break
                            size += len(chunk)
                            if size > self.media_manager.max_file_size:
                                raise ValueError("文件体积超过上限")
                            await fp.write(chunk)
                    try:
                        record = await self.media_manager.save_from_local_path(
                            str(temp_name),
                            category=category,
                            description=description,
                            filename=upload.filename or temp_name.name,
                            move=True,
                            duplicate_policy=duplicate_policy,
                        )
                    except TypeError:
                        record = await self.media_manager.save_from_local_path(
                            str(temp_name),
                            category=category,
                            description=description,
                            filename=upload.filename or temp_name.name,
                            move=True,
                        )
                    item = record.to_dict()
                    item["public_url"] = self.build_media_url(record)
                    saved.append(item)
                except DuplicateMediaError as exc:
                    existing = exc.record.to_dict()
                    existing["public_url"] = self.build_media_url(exc.record)
                    duplicates.append(
                        {
                            "name": upload.filename or temp_name.name,
                            "code": "duplicate_sha256",
                            "existing": existing,
                        }
                    )
                    temp_name.unlink(missing_ok=True)
                except Exception as exc:
                    errors.append(f"{upload.filename or temp_name.name}: {exc}")
                    temp_name.unlink(missing_ok=True)
                finally:
                    await upload.close()
            return {"saved": saved, "errors": errors, "duplicates": duplicates}

        @self._app.get("/files/{category}/{filename:path}")
        async def serve_media_file(category: str, filename: str, request: Request):
            try:
                file_path = safe_join(self.media_root, category, filename)
            except ValueError as exc:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
            subject = file_path.resolve().relative_to(self.media_root).as_posix()
            if not await self._can_access_media_file(request, subject):
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="无权访问文件")
            if not file_path.exists() or not file_path.is_file():
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="文件不存在")
            mime, _kind = detect_mime_and_kind(file_path)
            response = FileResponse(path=file_path, media_type=mime or None)
            response.headers["Accept-Ranges"] = "bytes"
            return response

        @self._app.get("/thumb/{category}/{filename:path}")
        async def serve_thumbnail(
            category: str,
            filename: str,
            request: Request,
            size: int = 480,
        ):
            # 默认预生成尺寸为 480；其它值允许传入，会现场生成后缓存。
            safe_size = max(96, min(1024, int(size or 480)))
            try:
                source = safe_join(self.media_root, category, filename)
            except ValueError as exc:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
            subject = source.resolve().relative_to(self.media_root).as_posix()
            if not await self._can_access_media_file(request, subject):
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="无权访问文件")
            if not source.exists() or not source.is_file():
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="文件不存在")
            mime, kind = detect_mime_and_kind(source)
            if kind == "image" and source.suffix.lower() == ".svg":
                # SVG 矢量图不做光栅化，直接回源
                response = FileResponse(path=source, media_type=mime or None)
                response.headers["Accept-Ranges"] = "bytes"
                return response
            if kind != "image":
                # 仅图片生成缩略图；其它类型直接回源（前端会基于类型决定展示方式）。
                response = FileResponse(path=source, media_type=mime or None)
                response.headers["Accept-Ranges"] = "bytes"
                return response
            try:
                target = await self._ensure_thumbnail_for_record(source, safe_size, kind=kind)
            except Exception as exc:
                logger.debug("缩略图生成失败: %s", exc)
                target = None
            if target is None or not target.exists():
                return FileResponse(path=source, media_type=mime or None)
            response = FileResponse(path=target, media_type="image/webp")
            response.headers["Cache-Control"] = "public, max-age=86400"
            return response

        @self._app.get("/api/data-tree")
        async def data_tree(path: str = "", token: str = Depends(self._auth_dependency())):
            _ = token
            if not self.expose_astrbot_data:
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail="未启用 data 浏览")
            try:
                target = self._resolve_data_path(path)
            except ValueError as exc:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
            if not target.exists():
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="路径不存在")
            if not target.is_dir():
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="目标不是目录")

            children = sorted(
                target.iterdir(),
                key=lambda item: (not item.is_dir(), item.name.lower()),
            )
            items = [self._build_data_item(child) for child in children]
            rel = target.resolve().relative_to(self.data_root).as_posix()
            if rel == ".":
                rel = ""
            parent = ""
            if rel:
                parent = str(Path(rel).parent).replace("\\", "/")
                if parent == ".":
                    parent = ""
            return {"path": rel, "parent": parent, "items": items}

        @self._app.get("/api/data-file")
        async def data_file(path: str, request: Request, download: int = 0):
            if not self.expose_astrbot_data:
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail="未启用 data 浏览")
            try:
                target = self._resolve_data_path(path)
            except ValueError as exc:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
            subject = target.resolve().relative_to(self.data_root).as_posix()
            if not await self._can_access_data_file(request, subject):
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="无权访问文件")
            if not target.exists() or not target.is_file():
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="文件不存在")
            mime, _kind = detect_mime_and_kind(target)
            response = FileResponse(path=target, media_type=mime or None)
            response.headers["Accept-Ranges"] = "bytes"
            if download:
                filename_safe = quote(target.name)
                response.headers["Content-Disposition"] = (
                    f"attachment; filename*=UTF-8''{filename_safe}"
                )
            return response

        @self._app.get("/api/data-text")
        async def data_text(
            path: str, token: str = Depends(self._auth_dependency())
        ) -> dict[str, Any]:
            _ = token
            if not self.expose_astrbot_data:
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail="未启用 data 浏览")
            try:
                target = self._resolve_data_path(path)
            except ValueError as exc:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
            if not target.exists() or not target.is_file():
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="文件不存在")

            stat = target.stat()
            mime, kind = detect_mime_and_kind(target)
            suffix = target.suffix.lower()
            rel = target.resolve().relative_to(self.data_root).as_posix()

            payload: dict[str, Any] = {
                "name": target.name,
                "path": rel,
                "size": int(stat.st_size),
                "mime": mime,
                "kind": kind,
                "suffix": suffix,
                "is_text": False,
                "content": "",
                "encoding": "",
                "truncated": False,
                "read_bytes": 0,
            }

            read_size = min(stat.st_size, TEXT_PREVIEW_MAX_BYTES)
            try:
                async with aiofiles.open(target, "rb") as fp:
                    raw = await fp.read(read_size)
            except Exception as exc:
                raise HTTPException(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"读取失败: {exc}",
                ) from exc

            payload["read_bytes"] = len(raw)
            payload["truncated"] = stat.st_size > read_size

            decoded_text: str | None = None
            used_encoding = ""
            for encoding in ("utf-8", "utf-8-sig", "gbk", "gb18030", "latin-1"):
                try:
                    decoded_text = raw.decode(encoding)
                    used_encoding = encoding
                    break
                except Exception:
                    continue

            name_hints_text = target.name.lower() in TEXT_PREVIEW_FILENAMES
            ext_hints_text = (
                suffix in TEXT_PREVIEW_EXTENSIONS
                or name_hints_text
            )
            is_text = False
            if decoded_text is not None and "\x00" not in decoded_text:
                if ext_hints_text:
                    is_text = True
                else:
                    printable = sum(
                        1
                        for ch in decoded_text[:2048]
                        if ch.isprintable() or ch in "\n\r\t"
                    )
                    ratio = (printable / len(decoded_text[:2048])) if decoded_text else 0.0
                    is_text = ratio >= 0.92

            if is_text and decoded_text is not None:
                payload["is_text"] = True
                payload["content"] = decoded_text
                payload["encoding"] = used_encoding
            return payload

        @self._app.get("/api/backup/export")
        async def backup_export(
            include_media: int = 1,
            token: str = Depends(self._auth_dependency()),
        ) -> FileResponse:
            _ = token
            return await self._create_backup_archive(include_media=bool(include_media))

        @self._app.post("/api/backup/import")
        async def backup_import(
            archive: UploadFile = File(...),
            replace_media: int = Form(0),
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            return await self._restore_backup_archive(
                upload=archive,
                replace_media=bool(replace_media),
            )

        # ---- Intelligence (CLIP / Face) ----

        def _require_intelligence():
            if self.intelligence_manager is None:
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="智能能力未启用",
                )
            return self.intelligence_manager

        @self._app.get("/api/intelligence/models")
        async def intel_list_models(
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            manager = _require_intelligence()
            return {
                "feature_enabled": manager.feature_enabled,
                "clip_enabled": manager.clip_enabled,
                "face_enabled": manager.face_enabled,
                "hf_mirror_url": manager.hf_mirror_url,
                "face_quality": manager.face_quality_thresholds,
                "models": [snap.to_dict() for snap in manager.snapshots()],
            }

        @self._app.post("/api/intelligence/models/{model_key}/download")
        async def intel_start_download(
            model_key: str,
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            manager = _require_intelligence()
            spec = manager.get_spec(model_key)
            if spec is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="模型不存在")
            try:
                await manager.start_download(model_key)
            except KeyError:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="模型不存在") from None
            snap = manager.snapshot(model_key)
            return {"started": True, "model": snap.to_dict() if snap else None}

        @self._app.post("/api/intelligence/models/{model_key}/cancel")
        async def intel_cancel_download(
            model_key: str,
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            manager = _require_intelligence()
            cancelled = await manager.cancel_download(model_key)
            snap = manager.snapshot(model_key)
            return {
                "cancelled": cancelled,
                "model": snap.to_dict() if snap else None,
            }

        @self._app.delete("/api/intelligence/models/{model_key}")
        async def intel_remove_model(
            model_key: str,
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            manager = _require_intelligence()
            spec = manager.get_spec(model_key)
            if spec is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="模型不存在")
            await manager.remove_model(model_key)
            snap = manager.snapshot(model_key)
            return {"removed": True, "model": snap.to_dict() if snap else None}

        @self._app.patch("/api/intelligence/settings")
        async def intel_patch_settings(
            payload: dict[str, Any],
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            manager = _require_intelligence()
            manager.update_settings(
                feature_enabled=payload.get("feature_enabled"),
                clip_enabled=payload.get("clip_enabled"),
                face_enabled=payload.get("face_enabled"),
                hf_mirror_url=payload.get("hf_mirror_url"),
                max_concurrent_downloads=payload.get("max_concurrent_downloads"),
                face_min_det_score=payload.get("face_min_det_score"),
                face_min_face_size=payload.get("face_min_face_size"),
                face_min_blur_var=payload.get("face_min_blur_var"),
            )
            return {
                "feature_enabled": manager.feature_enabled,
                "clip_enabled": manager.clip_enabled,
                "face_enabled": manager.face_enabled,
                "hf_mirror_url": manager.hf_mirror_url,
                "face_quality": manager.face_quality_thresholds,
            }

        # ---- CLIP 索引与语义搜索 ----

        async def _iter_image_records():
            getter = getattr(self.media_manager, "list_image_records_minimal", None)
            if not callable(getter):
                return []
            return await getter()

        @self._app.get("/api/intelligence/clip/status")
        async def intel_clip_status(
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            manager = _require_intelligence()
            store = await manager.get_clip_store()
            indexed = await store.count() if store is not None else 0
            engine = await manager.get_clip_engine()
            scan_task = manager._clip_scan_task  # type: ignore[attr-defined]
            scanning = bool(scan_task and not scan_task.done())
            worker = manager._clip_worker  # type: ignore[attr-defined]
            stats = getattr(worker, "stats", None) if worker is not None else None
            stats_payload: dict[str, Any] = {}
            if stats is not None:
                stats_payload = {
                    "indexed": stats.indexed,
                    "skipped": stats.skipped,
                    "failed": stats.failed,
                    "last_run_at": stats.last_run_at,
                    "last_error": stats.last_error,
                }
            return {
                "engine_ready": engine is not None,
                "indexed_count": indexed,
                "scanning": scanning,
                "stats": stats_payload,
            }

        @self._app.post("/api/intelligence/clip/scan")
        async def intel_clip_scan(
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            manager = _require_intelligence()
            started = await manager.trigger_clip_scan(
                iter_image_records=_iter_image_records
            )
            return {"started": started}

        @self._app.get("/api/intelligence/clip/search")
        async def intel_clip_search(
            q: str,
            top_k: int = 20,
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            manager = _require_intelligence()
            text = (q or "").strip()
            if not text:
                return {"results": [], "engine_ready": False}
            limit = max(1, min(100, int(top_k or 20)))
            pairs = await manager.search_clip_by_text(text, top_k=limit)
            results: list[dict[str, Any]] = []
            for media_id, score in pairs:
                if not math.isfinite(score) or score < _CLIP_SCORE_MIN_DISPLAY:
                    # 「仅供参考」档（含坏向量产生的 NaN）一律不返回，
                    # 避免前端列表里出现明显不相关的结果。
                    continue
                getter = getattr(self.media_manager, "get_by_id", None)
                if not callable(getter):
                    continue
                record = await getter(media_id)
                if record is None:
                    continue
                payload = record.to_dict() if hasattr(record, "to_dict") else dict(record)
                payload["score"] = float(score)
                results.append(payload)
            return {
                "results": results,
                "engine_ready": True,
                "query": text,
                "min_score": _CLIP_SCORE_MIN_DISPLAY,
            }

        @self._app.delete("/api/intelligence/clip/index/{media_id}")
        async def intel_clip_remove_one(
            media_id: int,
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            manager = _require_intelligence()
            store = await manager.get_clip_store()
            if store is None:
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE, detail="CLIP 未启用"
                )
            await store.delete(int(media_id))
            return {"removed": True, "media_id": media_id}

        # ---- 人脸 / Person 管理 ----

        async def _require_face_store():
            manager = _require_intelligence()
            store = await manager.get_face_store()
            if store is None:
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE, detail="人脸功能未启用"
                )
            return manager, store

        async def _require_face_clusterer():
            manager = _require_intelligence()
            clusterer = await manager.get_face_clusterer()
            if clusterer is None:
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE, detail="人脸功能未启用"
                )
            return manager, clusterer

        async def _attach_media_meta(items: list[dict[str, Any]]) -> None:
            getter = getattr(self.media_manager, "get_by_id", None)
            if not callable(getter):
                return
            cache: dict[int, Any] = {}
            for item in items:
                mid = item.get("media_id")
                if mid is None:
                    continue
                if mid not in cache:
                    cache[mid] = await getter(int(mid))
                record = cache[mid]
                if record is None:
                    continue
                payload = (
                    record.to_dict() if hasattr(record, "to_dict") else dict(record)
                )
                item["media"] = {
                    "id": payload.get("id"),
                    "filename": payload.get("filename"),
                    "category": payload.get("category"),
                    "kind": payload.get("kind"),
                    "rel_path": payload.get("rel_path"),
                    "size": payload.get("size"),
                    "size_human": payload.get("size_human"),
                    "tags": payload.get("tags"),
                }

        @self._app.get("/api/intelligence/face/status")
        async def intel_face_status(
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            manager = _require_intelligence()
            store = await manager.get_face_store()
            engine = await manager.get_face_engine()
            face_count = await store.count_faces() if store else 0
            person_count = await store.count_persons() if store else 0
            scan_task = manager._face_scan_task  # type: ignore[attr-defined]
            scanning = bool(scan_task and not scan_task.done())
            worker = manager._face_worker  # type: ignore[attr-defined]
            stats = getattr(worker, "stats", None) if worker is not None else None
            stats_payload: dict[str, Any] = {}
            if stats is not None:
                stats_payload = {
                    "media_processed": stats.media_processed,
                    "faces_indexed": stats.faces_indexed,
                    "faces_filtered": getattr(stats, "faces_filtered", 0),
                    "skipped": stats.skipped,
                    "failed": stats.failed,
                    "last_run_at": stats.last_run_at,
                    "last_error": stats.last_error,
                }
            return {
                "engine_ready": engine is not None,
                "face_count": face_count,
                "person_count": person_count,
                "scanning": scanning,
                "stats": stats_payload,
                "thresholds": manager.face_quality_thresholds,
            }

        @self._app.post("/api/intelligence/face/scan")
        async def intel_face_scan(
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            manager = _require_intelligence()
            started = await manager.trigger_face_scan(
                iter_image_records=_iter_image_records
            )
            return {"started": started}

        @self._app.post("/api/intelligence/face/recluster")
        async def intel_face_recluster(
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            _, clusterer = await _require_face_clusterer()
            report = await clusterer.recluster_dbscan()
            return {
                "persons_before": report.persons_before,
                "persons_after": report.persons_after,
                "merged": report.merged,
                "created": report.created,
                "moved_faces": report.moved_faces,
            }

        @self._app.get("/api/intelligence/face/persons")
        async def intel_face_list_persons(
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            _, store = await _require_face_store()
            persons = await store.list_persons()
            return {"persons": [p.to_dict() for p in persons]}

        @self._app.get("/api/intelligence/face/persons/{person_id}")
        async def intel_face_person_detail(
            person_id: int,
            limit: int = 200,
            offset: int = 0,
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            _, store = await _require_face_store()
            person = await store.get_person(person_id)
            if person is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="角色不存在")
            faces = await store.list_faces_by_person(
                person_id, limit=max(1, min(500, limit)), offset=max(0, offset)
            )
            face_dicts = [face.to_dict() for face in faces]
            await _attach_media_meta(face_dicts)
            return {
                "person": person.to_dict(),
                "faces": face_dicts,
            }

        @self._app.patch("/api/intelligence/face/persons/{person_id}")
        async def intel_face_person_rename(
            person_id: int,
            payload: dict[str, Any],
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            _, store = await _require_face_store()
            name = payload.get("name")
            sample = payload.get("sample_face_id")
            await store.update_person(
                person_id,
                name=str(name) if name is not None else None,
                sample_face_id=int(sample) if sample is not None else None,
            )
            person = await store.get_person(person_id)
            return {"person": person.to_dict() if person else None}

        @self._app.post("/api/intelligence/face/persons/merge")
        async def intel_face_person_merge(
            payload: dict[str, Any],
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            _, clusterer = await _require_face_clusterer()
            target = payload.get("target_id")
            sources = payload.get("source_ids") or []
            if target is None or not isinstance(sources, list) or not sources:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="缺少 target_id 或 source_ids",
                )
            moved = await clusterer.merge_persons(
                [int(v) for v in sources], int(target)
            )
            return {"merged": True, "moved_faces": moved}

        @self._app.post("/api/intelligence/face/persons/{person_id}/split")
        async def intel_face_person_split(
            person_id: int,
            payload: dict[str, Any],
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            _, clusterer = await _require_face_clusterer()
            face_ids = payload.get("face_ids") or []
            new_name = str(payload.get("name") or "")
            if not isinstance(face_ids, list) or not face_ids:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, detail="缺少 face_ids"
                )
            new_id = await clusterer.split_persons(
                int(person_id),
                [int(v) for v in face_ids],
                new_name=new_name,
            )
            return {"new_person_id": new_id}

        @self._app.delete("/api/intelligence/face/persons/{person_id}")
        async def intel_face_person_delete(
            person_id: int,
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            _, store = await _require_face_store()
            await store.delete_person(int(person_id))
            return {"deleted": True}

        async def _list_valid_media_ids() -> set[int]:
            getter = getattr(self.media_manager, "list_image_records_minimal", None)
            if not callable(getter):
                return set()
            try:
                records = await getter()
            except Exception:
                records = []
            ids: set[int] = set()
            for rec in records or []:
                try:
                    ids.add(int(rec[0]))
                except Exception:
                    continue
            return ids

        async def _resolve_media_path(media_id: int) -> str | None:
            getter = getattr(self.media_manager, "get_by_id", None)
            if not callable(getter):
                return None
            try:
                record = await getter(int(media_id))
            except Exception:
                return None
            if record is None:
                return None
            payload = record.to_dict() if hasattr(record, "to_dict") else dict(record)
            abs_path = payload.get("abs_path") or ""
            if not abs_path:
                return None
            return str(abs_path)

        @self._app.post("/api/intelligence/face/cleanup")
        async def intel_face_cleanup(
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            manager = _require_intelligence()
            valid = await _list_valid_media_ids()
            removed = await manager.cleanup_face_orphans(valid)
            return {"removed": int(removed)}

        @self._app.post("/api/intelligence/face/prune")
        async def intel_face_prune(
            payload: dict[str, Any] | None = None,
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            """按当前阈值（或 payload 显式指定）清理已有低质量人脸。"""
            _ = token
            manager = _require_intelligence()
            payload = payload or {}
            result = await manager.prune_low_quality_faces(
                min_det_score=payload.get("min_det_score"),
                min_face_size=payload.get("min_face_size"),
                min_blur_var=payload.get("min_blur_var"),
                ignore_blur_var_zero=bool(
                    payload.get("ignore_blur_var_zero", True)
                ),
            )
            removed_ids = list(result.get("removed", []))
            return {
                "removed": len(removed_ids),
                "removed_ids": removed_ids,
                "thresholds": result.get("thresholds", {}),
            }

        @self._app.post("/api/intelligence/face/thumbs/rebuild")
        async def intel_face_thumbs_rebuild(
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            manager = _require_intelligence()
            processed, failed = await manager.regenerate_face_thumbs(
                _resolve_media_path
            )
            return {"processed": int(processed), "failed": int(failed)}

        @self._app.get("/api/intelligence/face/{face_id}/thumb")
        async def intel_face_thumb(
            face_id: int,
            request: Request,
        ) -> FileResponse:
            if not await self._can_access_media_file(request, "*"):
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="未认证")
            _, store = await _require_face_store()
            face = await store.get_face(int(face_id))
            if face is None or not face.thumb_path:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="缩略图不存在")
            path = Path(face.thumb_path)
            if not path.is_file():
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="缩略图文件丢失")
            return FileResponse(path=path, media_type="image/jpeg")
