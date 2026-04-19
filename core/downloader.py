"""下载与消息附件提取。"""

from __future__ import annotations

import asyncio
import ipaddress
import mimetypes
import secrets
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urljoin, urlparse

import aiofiles
import aiohttp

from astrbot.api import logger

from .utils import ensure_dir, guess_filename_from_url, sanitize_filename, unique_path


@dataclass(slots=True)
class MediaSource:
    source_type: str  # url | local
    value: str
    filename_hint: str = ""
    component_type: str = ""


@dataclass(slots=True)
class DownloadedFile:
    path: Path
    filename: str
    content_type: str = ""


class _PublicIPResolver(aiohttp.abc.AbstractResolver):
    """在 DNS 解析阶段只允许公网 IP，防止 DNS rebinding。"""

    def __init__(self, is_public_ip: Callable[[str], bool]):
        self._is_public_ip = is_public_ip

    async def resolve(
        self,
        host: str,
        port: int = 0,
        family: int = socket.AF_UNSPEC,
    ) -> list[dict[str, Any]]:
        text = str(host or "").strip().lower()
        if not text:
            raise OSError("URL 缺少有效主机名。")
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(
                text,
                port,
                family=family,
                type=socket.SOCK_STREAM,
                proto=socket.IPPROTO_TCP,
            )
        except Exception as exc:
            raise OSError(f"无法解析目标地址: {text}") from exc
        resolved: list[dict[str, Any]] = []
        for family_value, _type_value, proto_value, _canonname, sockaddr in infos:
            if not isinstance(sockaddr, tuple) or not sockaddr:
                continue
            ip_text = str(sockaddr[0])
            if not self._is_public_ip(ip_text):
                raise OSError("禁止访问本地或内网地址。")
            resolved_port = int(sockaddr[1]) if len(sockaddr) > 1 else int(port or 0)
            resolved.append(
                {
                    "hostname": text,
                    "host": ip_text,
                    "port": resolved_port,
                    "family": family_value,
                    "proto": proto_value or socket.IPPROTO_TCP,
                    "flags": socket.AI_NUMERICHOST,
                }
            )
        if not resolved:
            raise OSError(f"无法解析目标地址: {text}")
        return resolved

    async def close(self) -> None:
        return None


class MediaDownloader:
    MAX_REDIRECTS = 6

    def __init__(
        self,
        temp_dir: Path,
        max_file_size_mb: int = 50,
        allow_local_path_source: bool = True,
        local_path_whitelist: list[str] | tuple[str, ...] | None = None,
    ):
        self.temp_dir = ensure_dir(temp_dir)
        self.max_file_size = max_file_size_mb * 1024 * 1024
        self.allow_local_path_source = bool(allow_local_path_source)
        # ``None`` 表示不启用白名单（向后兼容 / 非生产场景）；
        # 传入列表或元组（含空 ``[]``）则进入强制白名单模式，空列表 = 全部拒绝。
        if local_path_whitelist is None:
            self._whitelist_enforced: bool = False
            self._local_path_whitelist: tuple[Path, ...] = ()
        else:
            self._whitelist_enforced = True
            self._local_path_whitelist = self._normalize_whitelist(local_path_whitelist)

    @staticmethod
    def _normalize_whitelist(
        entries: list[str] | tuple[str, ...],
    ) -> tuple[Path, ...]:
        resolved: list[Path] = []
        seen: set[str] = set()
        for entry in entries:
            text = str(entry or "").strip()
            if not text:
                continue
            try:
                candidate = Path(text).expanduser().resolve()
            except Exception as exc:  # pragma: no cover - 仅极端路径会抛
                logger.warning("本地路径白名单条目解析失败 %r: %s", text, exc)
                continue
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            resolved.append(candidate)
        return tuple(resolved)

    def _is_local_path_allowed(self, path: Path) -> bool:
        if not self._whitelist_enforced:
            return True
        if not self._local_path_whitelist:
            return False
        for allowed in self._local_path_whitelist:
            try:
                if path == allowed or path.is_relative_to(allowed):
                    return True
            except (OSError, ValueError):
                continue
        return False

    @staticmethod
    def is_http_url(value: str) -> bool:
        text = str(value or "").strip().lower()
        return text.startswith("http://") or text.startswith("https://")

    def parse_source(self, source: str) -> MediaSource:
        src = str(source or "").strip()
        if not src:
            raise ValueError("source 不能为空。")
        if self.is_http_url(src):
            return MediaSource(source_type="url", value=src, filename_hint="")
        if not self.allow_local_path_source:
            raise ValueError(
                "出于安全考虑，source 参数仅支持 URL；本地文件请通过消息附件上传。"
            )
        path = Path(src).expanduser().resolve()
        if not self._is_local_path_allowed(path):
            raise ValueError(
                f"本地路径 “{path}” 不在白名单范围内，无法保存。"
                "请让用户前往 AstrBot 插件管理面板 → astrbot_plugin_media_portal → "
                "下载配置 → “本地路径白名单 local_path_whitelist” 中追加该目录（或其上级目录），保存后重试。"
            )
        return MediaSource(source_type="local", value=str(path), filename_hint=path.name)

    @staticmethod
    def _is_public_ip(ip_text: str) -> bool:
        try:
            ip_obj = ipaddress.ip_address(ip_text)
        except Exception:
            return False
        return not (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_multicast
            or ip_obj.is_reserved
            or ip_obj.is_unspecified
        )

    async def _assert_public_host(self, hostname: str) -> None:
        text = str(hostname or "").strip().lower()
        if not text:
            raise ValueError("URL 缺少有效主机名。")
        if text in {"localhost", "localhost.localdomain"}:
            raise ValueError("禁止访问本地或内网地址。")

        try:
            ip_obj = ipaddress.ip_address(text)
        except ValueError:
            # 域名场景的 DNS 公网校验交由 _PublicIPResolver，在真正连接前执行。
            return
        if not self._is_public_ip(str(ip_obj)):
            raise ValueError("禁止访问本地或内网地址。")

    async def _assert_safe_url(self, raw_url: str) -> None:
        parsed = urlparse(str(raw_url or "").strip())
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"}:
            raise ValueError("仅支持 http/https URL。")
        if not parsed.hostname:
            raise ValueError("URL 缺少主机名。")
        await self._assert_public_host(parsed.hostname)

    async def download_to_temp(
        self, url: str, filename_hint: str = ""
    ) -> DownloadedFile:
        timeout = aiohttp.ClientTimeout(total=180)
        headers = {"User-Agent": "astrbot-media-portal/1.0"}
        current_url = str(url or "").strip()
        if not current_url:
            raise ValueError("URL 不能为空。")

        connector = aiohttp.TCPConnector(
            resolver=_PublicIPResolver(self._is_public_ip),
            ttl_dns_cache=0,
            use_dns_cache=False,
        )
        async with aiohttp.ClientSession(
            timeout=timeout,
            headers=headers,
            connector=connector,
        ) as session:
            for _ in range(self.MAX_REDIRECTS):
                await self._assert_safe_url(current_url)
                async with session.get(current_url, allow_redirects=False) as resp:
                    if resp.status in {301, 302, 303, 307, 308}:
                        location = str(resp.headers.get("Location", "") or "").strip()
                        if not location:
                            raise RuntimeError("下载重定向缺少 Location。")
                        current_url = urljoin(current_url, location)
                        continue

                    if resp.status >= 400:
                        raise RuntimeError(f"下载失败，HTTP {resp.status}")

                    raw_declared = str(resp.headers.get("Content-Length", "0") or "0").strip()
                    try:
                        declared = int(raw_declared)
                    except ValueError:
                        declared = 0
                    if declared > self.max_file_size:
                        raise ValueError("文件过大，超过限制。")

                    header_name = self._filename_from_headers(
                        resp.headers.get("Content-Disposition", "")
                    )
                    guessed_name = (
                        filename_hint
                        or header_name
                        or guess_filename_from_url(current_url, default="download")
                    )
                    clean_name = sanitize_filename(guessed_name, fallback="download")
                    content_type = str(resp.headers.get("Content-Type", "")).split(";")[0].strip()
                    suffix = Path(clean_name).suffix
                    if not suffix and content_type:
                        suffix = mimetypes.guess_extension(content_type) or ""

                    temp_name = f"download_{secrets.token_hex(8)}{suffix}"
                    temp_path = unique_path(self.temp_dir / temp_name)

                    downloaded = 0
                    write_ok = False
                    try:
                        async with aiofiles.open(temp_path, "wb") as fp:
                            async for chunk in resp.content.iter_chunked(1024 * 64):
                                downloaded += len(chunk)
                                if downloaded > self.max_file_size:
                                    raise ValueError("文件过大，超过限制。")
                                await fp.write(chunk)
                        if downloaded == 0:
                            # 某些服务器在 2xx 中返回空 body（例如异常回源），
                            # 不应把 0 字节文件当作“下载成功”。
                            raise RuntimeError("下载得到空响应（0 字节），已拒绝保存。")
                        write_ok = True
                    finally:
                        if not write_ok:
                            try:
                                temp_path.unlink(missing_ok=True)
                            except Exception:
                                pass
                    return DownloadedFile(
                        path=temp_path,
                        filename=clean_name,
                        content_type=content_type,
                    )
        raise RuntimeError(f"重定向次数过多（>{self.MAX_REDIRECTS} 次），已拒绝下载。")

    async def extract_sources_from_event(self, event: Any) -> list[MediaSource]:
        components = list(getattr(getattr(event, "message_obj", None), "message", []) or [])
        if not components and hasattr(event, "get_messages"):
            try:
                components = list(event.get_messages() or [])
            except Exception:
                components = []

        results: list[MediaSource] = []
        seen: set[str] = set()

        for component in components:
            filename_hint = str(
                getattr(component, "name", "")
                or getattr(component, "filename", "")
                or ""
            )
            comp_name = component.__class__.__name__.lower()

            url_value = getattr(component, "url", None)
            if isinstance(url_value, str) and self.is_http_url(url_value):
                key = f"url:{url_value}"
                if key not in seen:
                    seen.add(key)
                    results.append(
                        MediaSource(
                            source_type="url",
                            value=url_value,
                            filename_hint=filename_hint,
                            component_type=comp_name,
                        )
                    )
                continue

            file_value = getattr(component, "file", None)
            parsed_local = self._parse_local_value(file_value)
            if parsed_local:
                key = f"local:{parsed_local}"
                if key not in seen:
                    seen.add(key)
                    results.append(
                        MediaSource(
                            source_type="local",
                            value=parsed_local,
                            filename_hint=filename_hint or Path(parsed_local).name,
                            component_type=comp_name,
                        )
                    )
                continue

            parsed_url = self._parse_url_value(file_value)
            if parsed_url:
                key = f"url:{parsed_url}"
                if key not in seen:
                    seen.add(key)
                    results.append(
                        MediaSource(
                            source_type="url",
                            value=parsed_url,
                            filename_hint=filename_hint,
                            component_type=comp_name,
                        )
                    )
                continue

            path_value = getattr(component, "path", None)
            if isinstance(path_value, str) and path_value.strip():
                possible = Path(path_value).expanduser()
                if possible.exists() and possible.is_file():
                    real = str(possible.resolve())
                    key = f"local:{real}"
                    if key not in seen:
                        seen.add(key)
                        results.append(
                            MediaSource(
                                source_type="local",
                                value=real,
                                filename_hint=filename_hint or possible.name,
                                component_type=comp_name,
                            )
                        )
                    continue

            converter = getattr(component, "convert_to_file_path", None)
            if callable(converter):
                try:
                    converted = await converter()
                    if converted:
                        real = str(Path(converted).expanduser().resolve())
                        if Path(real).exists():
                            key = f"local:{real}"
                            if key not in seen:
                                seen.add(key)
                                results.append(
                                    MediaSource(
                                        source_type="local",
                                        value=real,
                                        filename_hint=filename_hint or Path(real).name,
                                        component_type=comp_name,
                                    )
                                )
                except Exception:
                    continue

        return results

    @staticmethod
    def _filename_from_headers(content_disposition: str) -> str:
        """从 ``Content-Disposition`` 中提取文件名。

        优先识别 RFC 5987 的 ``filename*=UTF-8''xxx`` 扩展形式，其次回退到
        传统的 ``filename="xxx"`` 形式，以便正确处理非 ASCII 文件名。
        """
        if not content_disposition:
            return ""
        segments = [segment.strip() for segment in content_disposition.split(";")]

        extended_value = ""
        legacy_value = ""
        for segment in segments:
            lower = segment.lower()
            if lower.startswith("filename*="):
                raw = segment.split("=", 1)[1].strip().strip('"').strip("'")
                # 形如 "UTF-8''%E4%B8%AD%E6%96%87.png"；charset 与 lang 可能省略。
                parts = raw.split("'", 2)
                if len(parts) == 3:
                    charset = parts[0].strip() or "utf-8"
                    encoded_name = parts[2]
                else:
                    charset = "utf-8"
                    encoded_name = raw
                try:
                    extended_value = unquote(encoded_name, encoding=charset, errors="replace")
                except (LookupError, ValueError):
                    extended_value = unquote(encoded_name, errors="replace")
            elif lower.startswith("filename="):
                value = segment.split("=", 1)[1].strip().strip('"').strip("'")
                legacy_value = unquote(value)

        chosen = extended_value or legacy_value
        if not chosen:
            return ""
        return sanitize_filename(chosen, fallback="")

    def _parse_url_value(self, raw_value: Any) -> str:
        if not isinstance(raw_value, str):
            return ""
        text = raw_value.strip()
        if self.is_http_url(text):
            return text
        return ""

    def _parse_local_value(self, raw_value: Any) -> str:
        if not isinstance(raw_value, str):
            return ""
        text = raw_value.strip()
        if not text:
            return ""
        if text.startswith("file:///"):
            parsed = urlparse(text)
            uri_path = unquote(parsed.path or "")
            # Windows file URI 通常是 /C:/path，Path 直接处理会找不到文件。
            if len(uri_path) >= 3 and uri_path[0] == "/" and uri_path[2] == ":":
                drive_letter = uri_path[1]
                if drive_letter.isalpha():
                    uri_path = uri_path[1:]
            text = uri_path
        if self.is_http_url(text):
            return ""
        local_path = Path(text).expanduser()
        if local_path.exists() and local_path.is_file():
            return str(local_path.resolve())
        return ""
