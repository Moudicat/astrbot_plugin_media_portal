"""通用工具函数。"""

from __future__ import annotations

import hashlib
import mimetypes
import re
import secrets
import time
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlparse

MEDIA_KIND_EXTENSIONS: dict[str, set[str]] = {
    "image": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"},
    "video": {".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".m4v"},
    "audio": {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".wma"},
}


def now_ts() -> float:
    return time.time()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def parse_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def slugify_category(name: str, default: str = "default") -> str:
    text = (name or "").strip()
    if not text:
        return default
    text = text.replace("\\", "/")
    text = re.sub(r"/+", "_", text)
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[^\w\u4e00-\u9fff.\-]+", "", text, flags=re.UNICODE)
    text = text.strip("._-")
    return text or default


def sanitize_filename(filename: str, fallback: str = "") -> str:
    name = (filename or "").strip()
    if not name:
        name = fallback.strip()
    if not name:
        return ""
    name = Path(name).name.replace("\\", "_").replace("/", "_")
    stem = re.sub(r"[^\w\u4e00-\u9fff.\-]+", "_", Path(name).stem, flags=re.UNICODE)
    ext = re.sub(r"[^\w.]+", "", Path(name).suffix.lower())
    stem = stem.strip("._-") or "media"
    return f"{stem}{ext}"


def guess_filename_from_url(url: str, default: str = "media") -> str:
    parsed = urlparse(url)
    candidate = unquote(Path(parsed.path).name)
    return sanitize_filename(candidate, fallback=default) or default


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    index = 1
    while True:
        candidate = parent / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def safe_join(base: Path, *parts: str) -> Path:
    target = base.resolve()
    for part in parts:
        target = (target / str(part)).resolve()
    try:
        target.relative_to(base.resolve())
    except Exception as exc:
        raise ValueError("路径越界，拒绝访问。") from exc
    return target


def relative_posix(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fp:
        while True:
            chunk = fp.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def detect_mime_and_kind(path: Path) -> tuple[str, str]:
    mime, _encoding = mimetypes.guess_type(str(path))
    suffix = path.suffix.lower()
    if mime:
        if mime.startswith("image/"):
            return mime, "image"
        if mime.startswith("video/"):
            return mime, "video"
        if mime.startswith("audio/"):
            return mime, "audio"
    for kind, extensions in MEDIA_KIND_EXTENSIONS.items():
        if suffix in extensions:
            if kind == "image":
                return mime or "image/*", kind
            if kind == "video":
                return mime or "video/*", kind
            if kind == "audio":
                return mime or "audio/*", kind
    return mime or "application/octet-stream", "other"


def is_kind_allowed(kind: str, allowed_kinds: Iterable[str]) -> bool:
    allowed = {str(item).lower() for item in allowed_kinds}
    return kind.lower() in allowed


def generate_password(length: int = 16) -> str:
    if length <= 8:
        return secrets.token_urlsafe(8)[:length]
    raw = secrets.token_urlsafe(max(12, length))
    return raw[:length]


def format_size(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    units = ["KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        value /= 1024.0
        if value < 1024:
            return f"{value:.1f}{unit}"
    return f"{value:.1f}PB"
