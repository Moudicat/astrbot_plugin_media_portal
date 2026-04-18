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
        logger.warning(
            "未找到 astrbot.core.utils.astrbot_path.get_astrbot_data_path，"
            "将回退到当前工作目录下的 data 目录。"
        )
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
    except (TypeError, ValueError):
        if value is not None and str(value).strip() != "":
            logger.warning("整数配置值无效: %r，已回退默认值 %s。", value, default)
        parsed = default
    if minimum is not None and parsed < minimum:
        return minimum
    return parsed


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _as_str_list(value: Any) -> list[str]:
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


def _normalize_base_url(url: str) -> str:
    normalized = url.strip()
    if not normalized:
        return ""
    # 防止配置误填 javascript:/file: 等危险 scheme 被直接写进分享链接。
    try:
        from urllib.parse import urlparse

        parsed = urlparse(normalized)
    except Exception:  # pragma: no cover - urlparse 极少抛错
        parsed = None
    if parsed is not None and parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
        logger.warning(
            "public_base_url 的协议 %r 非 http/https，已忽略该配置。", parsed.scheme
        )
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
    intersection = parsed & {"image", "video", "audio"}
    dropped = parsed - {"image", "video", "audio"}
    if dropped and not intersection:
        logger.warning(
            "downloader.allowed_kinds=%s 未包含任何合法值（image/video/audio），将回退默认。",
            sorted(parsed),
        )
        return default
    if dropped:
        logger.warning(
            "downloader.allowed_kinds 中存在未识别项 %s，已忽略。", sorted(dropped)
        )
    return intersection


@dataclass(slots=True)
class WebUISettings:
    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = 7003
    access_password: str = ""
    session_timeout: int = 3600
    public_base_url: str = ""
    expose_astrbot_data: bool = False
    allowed_origins: list[str] = field(default_factory=list)
    readonly_token_ttl: int = 3600
    share_url_ttl: int = 3600
    data_token_ttl: int = 3600


@dataclass(slots=True)
class StorageSettings:
    location_mode: str = "plugin_data"


@dataclass(slots=True)
class DownloaderSettings:
    max_file_size_mb: int = 500
    allowed_kinds: set[str] = field(default_factory=lambda: {"image", "video", "audio"})
    default_move_local: bool = True


@dataclass(slots=True)
class PluginSettings:
    webui: WebUISettings
    storage: StorageSettings
    downloader: DownloaderSettings
    astrbot_data_dir: Path
    plugin_data_dir: Path
    media_root: Path
    media_location_mode: str = "plugin_data"
    raw_config: dict[str, Any] = field(default_factory=dict)


_VALID_LOCATION_MODES = {"astrbot_data", "plugin_data"}


def _resolve_media_root(
    storage: StorageSettings,
    astrbot_data_dir: Path,
    plugin_data_dir: Path,
) -> tuple[Path, str]:
    """解析媒体根目录。

    返回 ``(media_root, effective_mode)``，其中 ``effective_mode`` 为最终生效的模式。
    """
    mode = (storage.location_mode or "plugin_data").strip().lower()
    if mode not in _VALID_LOCATION_MODES:
        logger.warning(
            "未知的 storage.location_mode=%s，回退到 plugin_data。", mode
        )
        mode = "plugin_data"

    if mode == "plugin_data":
        return (plugin_data_dir / "media").resolve(), "plugin_data"
    return (astrbot_data_dir / "media").resolve(), "astrbot_data"


def load_plugin_settings(
    config: dict[str, Any] | None,
    plugin_data_dir: Path | None = None,
) -> PluginSettings:
    """加载插件配置并解析关键目录。

    Args:
        config: AstrBot 注入的原始配置字典。
        plugin_data_dir: 插件独立数据目录，通常由 ``StarTools.get_data_dir()`` 得到。
            为空时会退化到 ``{astrbot_data}/plugin_data/astrbot_plugin_media_portal``。
    """
    raw_config = config or {}
    webui_raw = _read_section(raw_config, "webui")
    storage_raw = _read_section(raw_config, "storage")
    downloader_raw = _read_section(raw_config, "downloader")

    # 兼容旧平铺配置
    if not webui_raw and "webui_port" in raw_config:
        webui_raw = {
            "enabled": False,
            "port": raw_config.get("webui_port"),
        }

    webui = WebUISettings(
        enabled=_as_bool(webui_raw.get("enabled"), False),
        host=_as_str(webui_raw.get("host"), "0.0.0.0") or "0.0.0.0",
        port=_as_int(webui_raw.get("port"), 7003, minimum=1),
        access_password=_as_str(webui_raw.get("access_password"), ""),
        session_timeout=_as_int(webui_raw.get("session_timeout"), 3600, minimum=60),
        public_base_url=_normalize_base_url(_as_str(webui_raw.get("public_base_url"), "")),
        expose_astrbot_data=_as_bool(webui_raw.get("expose_astrbot_data"), False),
        allowed_origins=_as_str_list(webui_raw.get("allowed_origins")),
        readonly_token_ttl=_as_int(
            webui_raw.get("readonly_token_ttl"), 3600, minimum=60
        ),
        share_url_ttl=_as_int(webui_raw.get("share_url_ttl"), 3600, minimum=60),
        data_token_ttl=_as_int(webui_raw.get("data_token_ttl"), 3600, minimum=60),
    )
    storage = StorageSettings(
        location_mode=(
            _as_str(storage_raw.get("location_mode"), "plugin_data")
            or "plugin_data"
        ),
    )
    downloader = DownloaderSettings(
        max_file_size_mb=_as_int(downloader_raw.get("max_file_size_mb"), 500, minimum=1),
        allowed_kinds=_parse_allowed_kinds(downloader_raw.get("allowed_kinds")),
        default_move_local=_as_bool(downloader_raw.get("default_move_local"), True),
    )

    astrbot_data_dir = Path(get_astrbot_data_path()).resolve()
    if plugin_data_dir is None:
        plugin_data_dir = (
            astrbot_data_dir / "plugin_data" / "astrbot_plugin_media_portal"
        ).resolve()
    else:
        plugin_data_dir = Path(plugin_data_dir).resolve()

    media_root, effective_mode = _resolve_media_root(
        storage, astrbot_data_dir, plugin_data_dir
    )
    storage.location_mode = effective_mode

    try:
        media_root.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.error("创建媒体目录失败: %s", exc, exc_info=True)
        raise

    logger.info(
        "[media_portal] 媒体库位置: mode=%s path=%s", effective_mode, media_root
    )

    return PluginSettings(
        webui=webui,
        storage=storage,
        downloader=downloader,
        astrbot_data_dir=astrbot_data_dir,
        plugin_data_dir=plugin_data_dir,
        media_root=media_root,
        media_location_mode=effective_mode,
        raw_config=raw_config,
    )
