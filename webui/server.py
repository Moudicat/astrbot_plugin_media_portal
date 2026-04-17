"""Media Portal WebUI 服务。"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import mimetypes
import secrets
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import aiofiles
import uvicorn
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
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
TEXT_PREVIEW_MAX_BYTES = 1_500_000

try:
    from astrbot.core.utils.io import get_local_ip_addresses
except Exception:  # pragma: no cover

    def get_local_ip_addresses() -> list[str]:
        return []

from ..core.category_manager import CategoryManager
from ..core.media_manager import MediaManager, MediaRecord
from ..core.utils import (
    detect_mime_and_kind,
    generate_password,
    safe_join,
    slugify_category,
    unique_path,
)


class WebUIServer:
    def __init__(
        self,
        media_manager: MediaManager,
        category_manager: CategoryManager,
        config: dict[str, Any],
        data_root: Path,
        callback_api_base: str = "",
    ):
        self.media_manager = media_manager
        self.category_manager = category_manager
        self.config = config
        self.data_root = data_root.resolve()
        self.media_root = self.media_manager.media_root
        self.thumbnail_dir = (self.media_manager.plugin_data_dir / "thumbnails").resolve()
        try:
            self.thumbnail_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # pragma: no cover
            logger.warning("创建缩略图目录失败: %s", exc)

        self.host = str(config.get("host", "0.0.0.0") or "0.0.0.0")
        self.port = int(config.get("port", 7003) or 7003)
        self.enabled = bool(config.get("enabled", False))
        self.expose_astrbot_data = bool(config.get("expose_astrbot_data", False))
        self.session_timeout = max(60, int(config.get("session_timeout", 3600) or 3600))
        self.public_base_url = str(config.get("public_base_url", "") or "").strip().rstrip("/")
        self.callback_api_base = str(callback_api_base or "").strip().rstrip("/")
        self.readonly_token_ttl = max(
            60, int(config.get("readonly_token_ttl", self.session_timeout) or self.session_timeout)
        )
        self.share_url_ttl = max(60, int(config.get("share_url_ttl", 3600) or 3600))
        self.data_token_ttl = max(
            60, int(config.get("data_token_ttl", self.session_timeout) or self.session_timeout)
        )
        self.allowed_origins = self._parse_allowed_origins(config.get("allowed_origins"))
        self._capability_secret = secrets.token_bytes(32)

        self._access_password = str(config.get("access_password", "") or "").strip()
        self._password_generated = False
        if not self._access_password:
            self._access_password = generate_password(16)
            self._password_generated = True
            logger.warning(
                "Media Portal WebUI 未配置密码，已自动生成随机密码: %s （建议通过 /media password set 固定，或在配置中设置 access_password）",
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
                return
            if self._server_task.done():
                error = self._server_task.exception()
                raise RuntimeError(f"WebUI 启动失败: {error}") from error
            await asyncio.sleep(0.1)

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
            await self._server_task
        self._cleanup_task = None
        self._server_task = None
        self._server = None

    async def rotate_password(self, password: str = "") -> str:
        new_password = password.strip() or generate_password(16)
        self._access_password = new_password
        self._password_generated = not bool(password.strip())
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

    def get_access_urls(self) -> list[str]:
        urls: list[str] = []
        if self.public_base_url:
            urls.append(self.public_base_url)
        urls.append(f"http://localhost:{self.port}")
        urls.append(f"http://127.0.0.1:{self.port}")

        if self.host not in {"0.0.0.0", "::"} and self.host not in {"127.0.0.1", "localhost"}:
            urls.append(f"http://{self.host}:{self.port}")
        else:
            for ip in get_local_ip_addresses():
                if not ip or ip.startswith("127."):
                    continue
                urls.append(f"http://{ip}:{self.port}")

        dedup: list[str] = []
        seen: set[str] = set()
        for url in urls:
            if url in seen:
                continue
            seen.add(url)
            dedup.append(url)
        return dedup

    def get_preferred_base_url(self) -> str:
        if self.public_base_url:
            return self.public_base_url
        if self.host in {"0.0.0.0", "::"}:
            for ip in get_local_ip_addresses():
                if ip and not ip.startswith("127."):
                    return f"http://{ip}:{self.port}"
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
        while True:
            try:
                await asyncio.sleep(300)
                async with self._token_lock:
                    self._cleanup_tokens_locked()
                async with self._attempt_lock:
                    self._cleanup_attempts_locked()
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

    async def _record_failed_attempt(self, client_ip: str) -> None:
        async with self._attempt_lock:
            self._failed_attempts.setdefault(client_ip, []).append(time.time())

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
        rel = source.resolve().relative_to(self.media_root).as_posix()
        return self.thumbnail_dir / str(size) / f"{rel}.webp"

    def _ensure_thumbnail_sync(self, source: Path, size: int) -> Path:
        target = self._thumbnail_target(source, size)
        try:
            if target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
                return target
        except Exception:
            pass
        target.parent.mkdir(parents=True, exist_ok=True)
        from PIL import Image, ImageOps

        with Image.open(source) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail((size, size), Image.LANCZOS)
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA") if "A" in img.mode else img.convert("RGB")
            tmp_target = target.with_suffix(target.suffix + ".part")
            img.save(tmp_target, "WEBP", quality=78, method=4)
        tmp_target.replace(target)
        return target

    async def _ensure_thumbnail(self, source: Path, size: int) -> Path:
        return await asyncio.to_thread(self._ensure_thumbnail_sync, source, size)

    def _build_data_item(self, path: Path) -> dict[str, Any]:
        is_dir = path.is_dir()
        rel_path = path.resolve().relative_to(self.data_root).as_posix()
        if rel_path == ".":
            rel_path = ""
        size = 0 if is_dir else path.stat().st_size
        mime, kind = detect_mime_and_kind(path) if not is_dir else ("", "folder")
        return {
            "name": path.name,
            "path": rel_path,
            "is_dir": is_dir,
            "size": size,
            "mime": mime,
            "kind": kind,
        }

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

        @self._app.get("/", response_class=HTMLResponse)
        async def index_page() -> HTMLResponse:
            if not index_file.exists():
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="前端文件不存在")
            return HTMLResponse(index_file.read_text(encoding="utf-8"))

        @self._app.get("/api/health")
        async def health() -> dict[str, Any]:
            return {"status": "ok", "service": "media_portal_webui", "version": "1.0.0"}

        @self._app.post("/api/login")
        async def login(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
            password = str(payload.get("password", "") or "").strip()
            if not password:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="密码不能为空")
            client_ip = request.client.host if request.client else "unknown"
            if not await self._check_rate_limit(client_ip):
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="尝试过于频繁，请稍后再试",
                )
            if password != self._access_password:
                await self._record_failed_attempt(client_ip)
                await asyncio.sleep(0.6)
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="认证失败")

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

        @self._app.post("/api/logout")
        async def logout(token: str = Depends(self._auth_dependency())) -> dict[str, str]:
            async with self._token_lock:
                self._tokens.pop(token, None)
            return {"message": "ok"}

        @self._app.get("/api/config")
        async def config(token: str = Depends(self._auth_dependency())) -> dict[str, Any]:
            _ = token
            max_bytes = int(getattr(self.media_manager, "max_file_size", 0) or 0)
            max_mb = max_bytes // (1024 * 1024) if max_bytes > 0 else 0
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
            }

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
            )
            data = updated.to_dict()
            data["public_url"] = self.build_media_url(updated)
            return data

        @self._app.delete("/api/media/{media_id}")
        async def delete_media(
            media_id: int, token: str = Depends(self._auth_dependency())
        ) -> dict[str, Any]:
            _ = token
            ok = await self.media_manager.delete_media(media_id)
            if not ok:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="媒体不存在")
            return {"deleted": True}

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
            record = await self.media_manager.save_from_url(
                url,
                category=category,
                description=description,
                filename=filename,
            )
            data = record.to_dict()
            data["public_url"] = self.build_media_url(record)
            return data

        @self._app.post("/api/media/upload")
        async def upload_media(
            category: str = Form("default"),
            description: str = Form(""),
            files: list[UploadFile] = File(default=[]),
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            if not files:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="未提供上传文件")

            saved: list[dict[str, Any]] = []
            errors: list[str] = []
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
                except Exception as exc:
                    errors.append(f"{upload.filename or temp_name.name}: {exc}")
                    temp_name.unlink(missing_ok=True)
                finally:
                    await upload.close()
            return {"saved": saved, "errors": errors}

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
            if kind != "image" or source.suffix.lower() == ".svg":
                response = FileResponse(path=source, media_type=mime or None)
                response.headers["Accept-Ranges"] = "bytes"
                return response
            try:
                target = await self._ensure_thumbnail(source, safe_size)
            except Exception as exc:
                logger.debug("缩略图生成失败，回退原图: %s", exc)
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

            ext_hints_text = suffix in TEXT_PREVIEW_EXTENSIONS or kind in {"text", "code"}
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
