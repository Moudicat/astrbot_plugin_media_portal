"""Media Portal 核心模块。"""

from .category_manager import CategoryManager
from .config import PluginSettings, load_plugin_settings
from .derivatives import DerivativesManager, THUMBNAIL_SIZE
from .downloader import MediaDownloader
from .media_manager import DuplicateMediaError, MediaManager, MediaRecord, TrashRecord

__all__ = [
    "CategoryManager",
    "DerivativesManager",
    "PluginSettings",
    "load_plugin_settings",
    "MediaDownloader",
    "DuplicateMediaError",
    "MediaManager",
    "MediaRecord",
    "TrashRecord",
    "THUMBNAIL_SIZE",
]
