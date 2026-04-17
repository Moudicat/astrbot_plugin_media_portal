"""媒体分类管理。"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from astrbot.api import logger

from .utils import ensure_dir, slugify_category


class CategoryManager:
    """管理分类描述与分类元数据。"""

    def __init__(self, categories_file: Path, media_root: Path):
        self.categories_file = categories_file
        self.media_root = media_root
        self._lock = threading.RLock()
        self._descriptions: dict[str, str] = {}
        ensure_dir(self.media_root)
        self._load()
        self.sync_with_filesystem()
        if "default" not in self._descriptions:
            self._descriptions["default"] = "默认分类"
            self._save()

    def _load(self) -> None:
        with self._lock:
            if not self.categories_file.exists():
                return
            try:
                raw = json.loads(self.categories_file.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    for key, value in raw.items():
                        category = slugify_category(str(key))
                        self._descriptions[category] = str(value or "").strip()
            except Exception as exc:
                logger.warning("读取分类配置失败，将使用空配置: %s", exc)

    def _save(self) -> None:
        with self._lock:
            ensure_dir(self.categories_file.parent)
            self.categories_file.write_text(
                json.dumps(self._descriptions, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def get_descriptions(self) -> dict[str, str]:
        with self._lock:
            return dict(self._descriptions)

    def list_categories(self) -> list[str]:
        with self._lock:
            return sorted(self._descriptions.keys())

    def get_description(self, category: str) -> str:
        normalized = slugify_category(category)
        with self._lock:
            return self._descriptions.get(normalized, "")

    def ensure_category(self, category: str, description: str = "") -> str:
        normalized = slugify_category(category)
        with self._lock:
            if normalized not in self._descriptions:
                self._descriptions[normalized] = description.strip()
                self._save()
        ensure_dir(self.media_root / normalized)
        return normalized

    def set_description(self, category: str, description: str) -> bool:
        normalized = slugify_category(category)
        with self._lock:
            if normalized not in self._descriptions:
                self._descriptions[normalized] = ""
            self._descriptions[normalized] = description.strip()
            self._save()
        return True

    def rename_category(self, old_name: str, new_name: str) -> tuple[bool, str]:
        old_normalized = slugify_category(old_name)
        new_normalized = slugify_category(new_name)
        if old_normalized == new_normalized:
            return True, new_normalized
        with self._lock:
            if old_normalized not in self._descriptions:
                return False, old_normalized
            if new_normalized in self._descriptions:
                return False, new_normalized
            self._descriptions[new_normalized] = self._descriptions.pop(old_normalized, "")
            self._save()
        return True, new_normalized

    def delete_category(self, category: str) -> bool:
        normalized = slugify_category(category)
        with self._lock:
            if normalized not in self._descriptions:
                return False
            self._descriptions.pop(normalized, None)
            self._save()
        return True

    def sync_with_filesystem(self) -> None:
        with self._lock:
            if not self.media_root.exists():
                return
            changed = False
            for item in self.media_root.iterdir():
                if not item.is_dir():
                    continue
                key = slugify_category(item.name)
                if key not in self._descriptions:
                    self._descriptions[key] = ""
                    changed = True
            if changed:
                self._save()

    def prune_missing_folders(self, *, protected: set[str] | None = None) -> list[str]:
        """移除本地文件夹已不存在的分类元数据（默认保护 default）。

        典型场景：用户在文件系统手动删除或重命名了某个分类目录后，
        原分类的描述条目仍残留在 ``categories.json`` 中，通过本方法可安全清理。
        """
        keep = {"default"} if protected is None else set(protected)
        removed: list[str] = []
        with self._lock:
            for key in list(self._descriptions.keys()):
                if key in keep:
                    continue
                if not (self.media_root / key).exists():
                    self._descriptions.pop(key, None)
                    removed.append(key)
            if removed:
                self._save()
        return removed

    def export_with_counts(self, counts: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        with self._lock:
            categories = set(self._descriptions.keys()) | set(counts.keys())
            result: list[dict[str, Any]] = []
            for category in sorted(categories):
                item_count = int(counts.get(category, {}).get("count", 0))
                total_size = int(counts.get(category, {}).get("size", 0))
                result.append(
                    {
                        "category": category,
                        "description": self._descriptions.get(category, ""),
                        "count": item_count,
                        "size": total_size,
                    }
                )
            return result
