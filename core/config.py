"""插件配置与路径解析。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from astrbot.api import logger

try:
    from astrbot.core.utils.astrbot_path import get_astrbot_data_path
except Exception:  # pragma: no cover - 仅用于本地离线开发环境兜底

    def get_astrbot_data_path() -> str:
        return str((Path.cwd() / "data").resolve())


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
        return default
    return bool(value)


def _as_int(value: Any, default: int, minimum: int | None = None) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    if minimum is not None and parsed < minimum:
        return minimum
    return parsed


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _normalize_base_url(url: str) -> str:
    normalized = url.strip()
    if not normalized:
        return ""
    return normalized.rstrip("/")


def _read_section(config: dict[str, Any], key: str) -> dict[str, Any]:
    section = config.get(key, {})
    if isinstance(section, dict):
        return section
    return {}


def _parse_allowed_kinds(value: Any) -> set[str]:
    default = {"image", "video", "audio"}
    if value is None:
        return default
    parsed: set[str] = set()
    if isinstance(value, str):
        tokens = [item.strip().lower() for item in value.replace(";", ",").split(",")]
        parsed.update(item for item in tokens if item)
    elif isinstance(value, (list, tuple, set)):
        parsed.update(str(item).strip().lower() for item in value if str(item).strip())
    if not parsed:
        return default
    return parsed & {"image", "video", "audio"}


@dataclass(slots=True)
class WebUISettings:
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 7003
    access_password: str = ""
    session_timeout: int = 3600
    public_base_url: str = ""
    expose_astrbot_data: bool = True


@dataclass(slots=True)
class StorageSettings:
    media_dir_override: str = ""


@dataclass(slots=True)
class DownloaderSettings:
    max_file_size_mb: int = 50
    allowed_kinds: set[str] = field(default_factory=lambda: {"image", "video", "audio"})
    default_move_local: bool = True


@dataclass(slots=True)
class PluginSettings:
    webui: WebUISettings
    storage: StorageSettings
    downloader: DownloaderSettings
    astrbot_data_dir: Path
    media_root: Path
    raw_config: dict[str, Any] = field(default_factory=dict)


def _resolve_media_root(storage: StorageSettings, astrbot_data_dir: Path) -> Path:
    raw_override = storage.media_dir_override.strip()
    if not raw_override:
        return (astrbot_data_dir / "media").resolve()

    override_path = Path(raw_override).expanduser()
    if not override_path.is_absolute():
        override_path = (astrbot_data_dir / override_path).resolve()
    return override_path.resolve()


def load_plugin_settings(config: dict[str, Any] | None) -> PluginSettings:
    """加载插件配置并解析关键目录。"""
    raw_config = config or {}
    webui_raw = _read_section(raw_config, "webui")
    storage_raw = _read_section(raw_config, "storage")
    downloader_raw = _read_section(raw_config, "downloader")

    # 兼容旧平铺配置
    if not webui_raw and "webui_port" in raw_config:
        webui_raw = {
            "enabled": True,
            "port": raw_config.get("webui_port"),
        }

    webui = WebUISettings(
        enabled=_as_bool(webui_raw.get("enabled"), True),
        host=_as_str(webui_raw.get("host"), "0.0.0.0") or "0.0.0.0",
        port=_as_int(webui_raw.get("port"), 7003, minimum=1),
        access_password=_as_str(webui_raw.get("access_password"), ""),
        session_timeout=_as_int(webui_raw.get("session_timeout"), 3600, minimum=60),
        public_base_url=_normalize_base_url(_as_str(webui_raw.get("public_base_url"), "")),
        expose_astrbot_data=_as_bool(webui_raw.get("expose_astrbot_data"), True),
    )
    storage = StorageSettings(
        media_dir_override=_as_str(storage_raw.get("media_dir_override"), "")
    )
    downloader = DownloaderSettings(
        max_file_size_mb=_as_int(downloader_raw.get("max_file_size_mb"), 50, minimum=1),
        allowed_kinds=_parse_allowed_kinds(downloader_raw.get("allowed_kinds")),
        default_move_local=_as_bool(downloader_raw.get("default_move_local"), True),
    )
    if not downloader.allowed_kinds:
        downloader.allowed_kinds = {"image", "video", "audio"}

    astrbot_data_dir = Path(get_astrbot_data_path()).resolve()
    media_root = _resolve_media_root(storage, astrbot_data_dir)

    try:
        media_root.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.error("创建媒体目录失败: %s", exc)
        raise

    return PluginSettings(
        webui=webui,
        storage=storage,
        downloader=downloader,
        astrbot_data_dir=astrbot_data_dir,
        media_root=media_root,
        raw_config=raw_config,
    )
