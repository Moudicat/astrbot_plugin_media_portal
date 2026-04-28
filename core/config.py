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


def _as_float(
    value: Any,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    """把任意输入解析为浮点数；解析失败时回退默认值。"""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        if value is not None and str(value).strip() != "":
            logger.warning("浮点配置值无效: %r，已回退默认值 %s。", value, default)
        parsed = default
    if minimum is not None and parsed < minimum:
        return minimum
    if maximum is not None and parsed > maximum:
        return maximum
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
    if parsed is None:
        return ""
    scheme = str(parsed.scheme or "").lower()
    if scheme not in {"http", "https"} or not parsed.netloc:
        logger.warning(
            "public_base_url %r 不是完整的 http/https URL，已忽略该配置。",
            normalized,
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
    totp_enabled: bool = False
    totp_issuer: str = "Media Portal"
    totp_account: str = "admin"


@dataclass(slots=True)
class StorageSettings:
    location_mode: str = "plugin_data"


_DEFAULT_LOCAL_PATH_WHITELIST: tuple[str, ...] = (
    "/AstrBot/data/workspaces",
    "/AstrBot/data/temp",
)


@dataclass(slots=True)
class DownloaderSettings:
    max_file_size_mb: int = 500
    allowed_kinds: set[str] = field(default_factory=lambda: {"image", "video", "audio"})
    default_move_local: bool = True
    allow_local_path_source: bool = True
    local_path_whitelist: list[str] = field(
        default_factory=lambda: list(_DEFAULT_LOCAL_PATH_WHITELIST)
    )


@dataclass(slots=True)
class IntelligenceSettings:
    enabled: bool = False
    hf_mirror_url: str = ""
    clip_enabled: bool = False
    face_enabled: bool = False
    max_concurrent_downloads: int = 1
    face_min_det_score: float = 0.6
    """人脸检测置信度下限（SCRFD 0~1）。"""

    face_min_face_size: int = 60
    """人脸框最短边像素下限，过滤远景小脸。"""

    face_min_blur_var: float = 60.0
    """112×112 对齐人脸的拉普拉斯方差下限，过滤糊脸。0 表示不过滤。"""


@dataclass(slots=True)
class PluginSettings:
    webui: WebUISettings
    storage: StorageSettings
    downloader: DownloaderSettings
    intelligence: IntelligenceSettings
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
    intelligence_raw = _read_section(raw_config, "intelligence")

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
        totp_enabled=_as_bool(webui_raw.get("totp_enabled"), False),
        totp_issuer=_as_str(webui_raw.get("totp_issuer"), "Media Portal") or "Media Portal",
        totp_account=_as_str(webui_raw.get("totp_account"), "admin") or "admin",
    )
    storage = StorageSettings(
        location_mode=(
            _as_str(storage_raw.get("location_mode"), "plugin_data")
            or "plugin_data"
        ),
    )
    raw_whitelist = downloader_raw.get("local_path_whitelist")
    if raw_whitelist is None:
        local_path_whitelist = list(_DEFAULT_LOCAL_PATH_WHITELIST)
    else:
        local_path_whitelist = _as_str_list(raw_whitelist)
    downloader = DownloaderSettings(
        max_file_size_mb=_as_int(downloader_raw.get("max_file_size_mb"), 500, minimum=1),
        allowed_kinds=_parse_allowed_kinds(downloader_raw.get("allowed_kinds")),
        default_move_local=_as_bool(downloader_raw.get("default_move_local"), True),
        allow_local_path_source=_as_bool(
            downloader_raw.get("allow_local_path_source"), True
        ),
        local_path_whitelist=local_path_whitelist,
    )
    intelligence = IntelligenceSettings(
        enabled=_as_bool(intelligence_raw.get("enabled"), False),
        hf_mirror_url=_normalize_base_url(
            _as_str(intelligence_raw.get("hf_mirror_url"), "")
        ),
        clip_enabled=_as_bool(intelligence_raw.get("clip_enabled"), False),
        face_enabled=_as_bool(intelligence_raw.get("face_enabled"), False),
        max_concurrent_downloads=max(
            1,
            min(3, _as_int(intelligence_raw.get("max_concurrent_downloads"), 1, minimum=1)),
        ),
        face_min_det_score=_as_float(
            intelligence_raw.get("face_min_det_score"),
            0.6,
            minimum=0.0,
            maximum=1.0,
        ),
        face_min_face_size=_as_int(
            intelligence_raw.get("face_min_face_size"), 60, minimum=0
        ),
        face_min_blur_var=_as_float(
            intelligence_raw.get("face_min_blur_var"), 60.0, minimum=0.0
        ),
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
        intelligence=intelligence,
        astrbot_data_dir=astrbot_data_dir,
        plugin_data_dir=plugin_data_dir,
        media_root=media_root,
        media_location_mode=effective_mode,
        raw_config=raw_config,
    )
