"""通用工具函数。"""

from __future__ import annotations

import hashlib
import ipaddress
import mimetypes
import os
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


# Docker 默认 bridge 在 172.17.0.0/16；用户自定义 bridge 通常在 172.18.0.0/16 - 172.31.0.0/16。
# 172.16.0.0/12 整体属于私有地址，但企业局域网极少使用 172.17+，这里按经验判定为“疑似容器内部 IP”。
# 额外覆盖 K8s 常见的 pod/service 段 10.42.0.0/16、10.43.0.0/16（k3s）等。这里只匹配最典型的 docker bridge。


def is_loopback_ip(ip: str) -> bool:
    try:
        return ipaddress.ip_address(str(ip).strip()).is_loopback
    except ValueError:
        return False


def is_link_local_ip(ip: str) -> bool:
    try:
        return ipaddress.ip_address(str(ip).strip()).is_link_local
    except ValueError:
        return False


def is_docker_bridge_ip(ip: str) -> bool:
    """根据经验判断 IP 是否位于典型 Docker bridge 子网。

    判定规则：IPv4 且第二段在 17-31 之间（即 172.17.x.x ~ 172.31.x.x）。
    保留 172.16.x.x 给企业常用 LAN，避免误伤。
    """
    try:
        addr = ipaddress.ip_address(str(ip).strip())
    except ValueError:
        return False
    if not isinstance(addr, ipaddress.IPv4Address):
        return False
    octets = str(addr).split(".")
    if len(octets) != 4 or octets[0] != "172":
        return False
    try:
        second = int(octets[1])
    except ValueError:
        return False
    return 17 <= second <= 31


def _cgroup_has_container_marker() -> bool:
    for candidate in ("/proc/1/cgroup", "/proc/self/cgroup", "/proc/1/mountinfo"):
        try:
            with open(candidate, "rb") as fp:
                blob = fp.read(32768)
        except OSError:
            continue
        text = blob.decode("utf-8", errors="ignore").lower()
        for marker in ("docker", "kubepods", "containerd", "crio", "podman", "lxc"):
            if marker in text:
                return True
    return False


def is_container_environment() -> bool:
    """粗略检测当前进程是否运行在容器（Docker/Podman/K8s 等）中。"""
    if os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv"):
        return True
    for env_name in (
        "KUBERNETES_SERVICE_HOST",
        "DOCKER_CONTAINER",
        "container",
    ):
        if os.environ.get(env_name):
            return True
    return _cgroup_has_container_marker()


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
