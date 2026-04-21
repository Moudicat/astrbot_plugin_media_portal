"""图片缩略图缓存。

设计要点：
- 产物是"只读缓存"，源文件删除 / 更新后可随时重建；
- 以 ``rel_path``（相对 ``media_root``）作为键，避免文件被重命名 / 迁移分类后
  缓存键错位；
- 仅对 ``image`` 生成单档 webp 缩略图；视频 / 音频不再产出衍生资源，由前端直接
  使用原生 ``<video>`` / 占位图展示。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from astrbot.api import logger

from .utils import detect_mime_and_kind

THUMBNAIL_SIZE: int = 480


class DerivativesManager:
    """图片缩略图生成器（视频 / 音频不生成任何产物）。"""

    def __init__(self, media_root: Path, plugin_data_dir: Path):
        self.media_root = media_root.resolve()
        self.root = (plugin_data_dir / "derivatives").resolve()
        self.thumbnail_dir = self.root / "thumbnails"
        try:
            self.thumbnail_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # pragma: no cover - 权限问题只能告警
            logger.warning("创建缩略图目录失败: %s (%s)", self.thumbnail_dir, exc)

    # ---------- 路径 ----------

    def thumbnail_path(self, rel_path: str, size: int = THUMBNAIL_SIZE) -> Path:
        return self.thumbnail_dir / str(int(size)) / f"{rel_path}.webp"

    def _abs_source(self, rel_path: str) -> Path:
        return (self.media_root / rel_path).resolve()

    @staticmethod
    def _should_regenerate(target: Path, source: Path) -> bool:
        """``target`` 不存在，或源文件比它更新，就视为需要重新生成。"""
        try:
            return not (
                target.exists()
                and target.is_file()
                and target.stat().st_mtime >= source.stat().st_mtime
            )
        except Exception:
            return True

    # ---------- 缩略图 ----------

    @staticmethod
    def _render_image_thumbnail(source: Path, target: Path, size: int) -> Path:
        from PIL import Image, ImageOps

        target.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail((size, size), Image.LANCZOS)
            if img.mode not in ("RGB", "RGBA"):
                if "A" in img.mode:
                    img = img.convert("RGBA")
                else:
                    img = img.convert("RGB")
            tmp = target.with_suffix(target.suffix + ".part")
            img.save(tmp, "WEBP", quality=78, method=4)
        tmp.replace(target)
        return target

    def ensure_thumbnail_sync(
        self,
        rel_path: str,
        size: int = THUMBNAIL_SIZE,
        *,
        kind: str = "",
    ) -> Path | None:
        """保证 ``rel_path`` 在 ``size`` 档位下存在缩略图，返回产物路径或 ``None``。

        仅图片生成产物，视频 / 音频一律返回 ``None``（前端走占位图 / 原生元素）。
        """
        source = self._abs_source(rel_path)
        if not source.exists() or not source.is_file():
            return None
        if not kind:
            _mime, kind = detect_mime_and_kind(source)
        if kind != "image":
            return None
        target = self.thumbnail_path(rel_path, size)
        if not self._should_regenerate(target, source):
            return target
        try:
            return self._render_image_thumbnail(source, target, size)
        except Exception as exc:
            logger.debug("生成缩略图失败 %s@%s: %s", rel_path, size, exc)
            return None

    async def ensure_thumbnail(
        self, rel_path: str, size: int = THUMBNAIL_SIZE, *, kind: str = ""
    ) -> Path | None:
        return await asyncio.to_thread(
            self.ensure_thumbnail_sync, rel_path, size, kind=kind
        )

    # ---------- 清理 ----------

    def purge_for(self, rel_path: str) -> None:
        """删除媒体时同步清理缩略图，避免遗留文件。"""
        target = self.thumbnail_path(rel_path)
        try:
            target.unlink(missing_ok=True)
        except Exception:
            pass

    def purge_for_category(self, category: str) -> None:
        """分类被整体删除 / 重命名时，粗粒度清理对应目录。"""
        safe = str(category or "").strip()
        if not safe:
            return
        target = self.thumbnail_dir / str(THUMBNAIL_SIZE) / safe
        self._remove_tree(target)

    @staticmethod
    def _remove_tree(path: Path) -> None:
        try:
            if not path.exists():
                return
            if path.is_file() or path.is_symlink():
                path.unlink(missing_ok=True)
                return
            import shutil as _shutil

            _shutil.rmtree(path, ignore_errors=True)
        except Exception:
            pass

    # ---------- 组合任务 ----------

    def generate_all_sync(self, rel_path: str, kind: str) -> None:
        if kind == "image":
            self.ensure_thumbnail_sync(rel_path, THUMBNAIL_SIZE, kind=kind)

    async def generate_all(self, rel_path: str, kind: str) -> None:
        try:
            await asyncio.to_thread(self.generate_all_sync, rel_path, kind)
        except Exception as exc:  # pragma: no cover
            logger.debug("后台生成缩略图失败 %s: %s", rel_path, exc)


__all__ = ["DerivativesManager", "THUMBNAIL_SIZE"]
