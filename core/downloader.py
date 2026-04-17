"""下载与消息附件提取。"""

from __future__ import annotations

import mimetypes
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import aiofiles
import aiohttp

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


class MediaDownloader:
    def __init__(self, temp_dir: Path, max_file_size_mb: int = 50):
        self.temp_dir = ensure_dir(temp_dir)
        self.max_file_size = max_file_size_mb * 1024 * 1024

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
        path = Path(src).expanduser().resolve()
        return MediaSource(source_type="local", value=str(path), filename_hint=path.name)

    async def download_to_temp(
        self, url: str, filename_hint: str = ""
    ) -> DownloadedFile:
        timeout = aiohttp.ClientTimeout(total=180)
        headers = {"User-Agent": "astrbot-media-portal/1.0"}

        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url, allow_redirects=True) as resp:
                if resp.status >= 400:
                    raise RuntimeError(f"下载失败，HTTP {resp.status}")

                declared = int(resp.headers.get("Content-Length", "0") or 0)
                if declared > self.max_file_size:
                    raise ValueError("文件过大，超过限制。")

                header_name = self._filename_from_headers(resp.headers.get("Content-Disposition", ""))
                guessed_name = (
                    filename_hint
                    or header_name
                    or guess_filename_from_url(url, default="download")
                )
                clean_name = sanitize_filename(guessed_name, fallback="download")
                content_type = str(resp.headers.get("Content-Type", "")).split(";")[0].strip()
                suffix = Path(clean_name).suffix
                if not suffix and content_type:
                    suffix = mimetypes.guess_extension(content_type) or ""

                temp_name = f"download_{secrets.token_hex(8)}{suffix}"
                temp_path = unique_path(self.temp_dir / temp_name)

                downloaded = 0
                async with aiofiles.open(temp_path, "wb") as fp:
                    async for chunk in resp.content.iter_chunked(1024 * 64):
                        downloaded += len(chunk)
                        if downloaded > self.max_file_size:
                            await fp.close()
                            try:
                                temp_path.unlink(missing_ok=True)
                            except Exception:
                                pass
                            raise ValueError("文件过大，超过限制。")
                        await fp.write(chunk)

        return DownloadedFile(path=temp_path, filename=clean_name, content_type=content_type)

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
        if not content_disposition:
            return ""
        segments = [segment.strip() for segment in content_disposition.split(";")]
        for segment in segments:
            if not segment.lower().startswith("filename="):
                continue
            value = segment.split("=", 1)[1].strip().strip('"').strip("'")
            return sanitize_filename(unquote(value), fallback="")
        return ""

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
            text = unquote(parsed.path or "")
        if self.is_http_url(text):
            return ""
        local_path = Path(text).expanduser()
        if local_path.exists() and local_path.is_file():
            return str(local_path.resolve())
        return ""
