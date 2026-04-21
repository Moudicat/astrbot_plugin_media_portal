"""FTS5 全文搜索 + DerivativesManager 单元测试。"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path

import pytest

from core.category_manager import CategoryManager
from core.derivatives import DerivativesManager, THUMBNAIL_SIZE
from core.downloader import MediaDownloader
from core.media_manager import MediaManager


def _build_manager(base_dir: Path) -> MediaManager:
    plugin_data_dir = (base_dir / "plugin_data").resolve()
    media_root = (base_dir / "media").resolve()
    category_manager = CategoryManager(
        categories_file=plugin_data_dir / "categories.json",
        media_root=media_root,
    )
    downloader = MediaDownloader(
        temp_dir=plugin_data_dir / "temp",
        max_file_size_mb=5,
    )
    return MediaManager(
        media_root=media_root,
        plugin_data_dir=plugin_data_dir,
        category_manager=category_manager,
        downloader=downloader,
        allowed_kinds={"image", "video", "audio"},
        max_file_size_mb=5,
        default_move_local=True,
    )


def _write_png(path: Path, *, size: tuple[int, int] = (24, 24), color=(220, 60, 60)) -> None:
    """写入一个真正的小 PNG，避免 Pillow 解码失败。"""
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - 项目已声明 pillow 依赖
        pytest.skip("Pillow 未安装")
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    path.write_bytes(buf.getvalue())


# ---------------- FTS5 ----------------


def test_fts_search_by_filename_description_and_tags(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = _build_manager(tmp_path)
        await manager.initialize()
        try:
            cat = tmp_path / "cat_sunset.png"
            _write_png(cat)
            dog = tmp_path / "dog_beach.png"
            _write_png(dog, color=(20, 180, 120))
            fox = tmp_path / "random.png"
            _write_png(fox, color=(60, 60, 220))

            await manager.save_from_local_path(
                str(cat),
                category="gallery",
                description="橘色日落下的猫",
                tags=["cute", "kitten"],
                move=False,
            )
            await manager.save_from_local_path(
                str(dog),
                category="gallery",
                description="海边奔跑的狗",
                tags=["puppy"],
                move=False,
            )
            await manager.save_from_local_path(
                str(fox),
                category="wild",
                description="a fox in the forest",
                tags=["fox", "forest"],
                move=False,
            )

            by_filename = await manager.search_media("sunset", limit=10)
            by_description = await manager.search_media("日落", limit=10)
            by_tag = await manager.search_media("kitten", limit=10)
            by_category = await manager.search_media("wild", limit=10)
            no_hit = await manager.search_media("zzzzzzzzzz", limit=10)

            assert [r.filename for r in by_filename] == ["cat_sunset.png"]
            assert [r.filename for r in by_description] == ["cat_sunset.png"]
            assert [r.filename for r in by_tag] == ["cat_sunset.png"]
            assert any(r.filename == "random.png" for r in by_category)
            assert no_hit == []
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_list_media_query_ranks_by_relevance(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = _build_manager(tmp_path)
        await manager.initialize()
        try:
            alpha = tmp_path / "alpha.png"
            beta = tmp_path / "beta.png"
            _write_png(alpha)
            _write_png(beta)
            await manager.save_from_local_path(
                str(alpha),
                category="gallery",
                description="alpha item rare",
                move=False,
            )
            await manager.save_from_local_path(
                str(beta),
                category="gallery",
                description="beta item",
                move=False,
            )

            hits = await manager.list_media(query="rare", page=1, page_size=10)
            assert hits["total"] == 1
            assert hits["items"][0]["filename"] == "alpha.png"
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_rebuild_fts_index_restores_after_raw_truncate(tmp_path: Path) -> None:
    """手工清空 media_fts，rebuild_fts_index 后搜索应重新生效。"""

    async def scenario() -> None:
        manager = _build_manager(tmp_path)
        await manager.initialize()
        try:
            img = tmp_path / "hello.png"
            _write_png(img)
            await manager.save_from_local_path(
                str(img),
                category="gallery",
                description="hello world",
                move=False,
            )
            if not manager._fts_enabled:
                pytest.skip("当前运行环境不支持 FTS5")

            assert manager._conn is not None
            await manager._conn.execute("DELETE FROM media_fts")
            await manager._conn.commit()

            rebuilt = await manager.rebuild_fts_index()
            assert rebuilt is True

            results = await manager.search_media("hello", limit=10)
            assert [r.filename for r in results] == ["hello.png"]
        finally:
            await manager.close()

    asyncio.run(scenario())


# ---------------- DerivativesManager ----------------


def test_derivatives_generate_image_thumbnails(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    plugin_data_dir = tmp_path / "plugin_data"
    media_root.mkdir(parents=True, exist_ok=True)
    plugin_data_dir.mkdir(parents=True, exist_ok=True)

    rel = "gallery/hello.png"
    source = media_root / rel
    source.parent.mkdir(parents=True, exist_ok=True)
    _write_png(source, size=(128, 128))

    manager = DerivativesManager(media_root=media_root, plugin_data_dir=plugin_data_dir)
    manager.generate_all_sync(rel, "image")

    target = manager.thumbnail_path(rel)
    assert target.exists(), f"缩略图应在 {target} 生成"
    assert target.read_bytes().startswith(b"RIFF")  # WebP 容器头
    assert str(THUMBNAIL_SIZE) in target.parts


def test_derivatives_skips_non_image_kinds(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    plugin_data_dir = tmp_path / "plugin_data"
    media_root.mkdir(parents=True, exist_ok=True)
    plugin_data_dir.mkdir(parents=True, exist_ok=True)

    rel = "songs/tune.mp3"
    source = media_root / rel
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"\x00\x00\x00")

    manager = DerivativesManager(media_root=media_root, plugin_data_dir=plugin_data_dir)
    manager.generate_all_sync(rel, "audio")
    manager.generate_all_sync("videos/clip.mp4", "video")

    assert not manager.thumbnail_path(rel).exists()
    assert not manager.thumbnail_path("videos/clip.mp4").exists()


def test_derivatives_purge_removes_generated_files(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    plugin_data_dir = tmp_path / "plugin_data"
    media_root.mkdir(parents=True, exist_ok=True)
    plugin_data_dir.mkdir(parents=True, exist_ok=True)

    rel = "purge/me.png"
    source = media_root / rel
    source.parent.mkdir(parents=True, exist_ok=True)
    _write_png(source, size=(96, 96))

    manager = DerivativesManager(media_root=media_root, plugin_data_dir=plugin_data_dir)
    manager.generate_all_sync(rel, "image")

    thumb = manager.thumbnail_path(rel)
    assert thumb.exists()

    manager.purge_for(rel)
    assert not thumb.exists()


def test_derivatives_purge_for_category(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    plugin_data_dir = tmp_path / "plugin_data"
    media_root.mkdir(parents=True, exist_ok=True)
    plugin_data_dir.mkdir(parents=True, exist_ok=True)

    # 准备两个分类的缩略图
    for cat, name in (("foo", "a.png"), ("bar", "b.png")):
        rel = f"{cat}/{name}"
        source = media_root / rel
        source.parent.mkdir(parents=True, exist_ok=True)
        _write_png(source, size=(64, 64))

    manager = DerivativesManager(media_root=media_root, plugin_data_dir=plugin_data_dir)
    manager.generate_all_sync("foo/a.png", "image")
    manager.generate_all_sync("bar/b.png", "image")

    for rel in ("foo/a.png", "bar/b.png"):
        assert manager.thumbnail_path(rel).exists()

    manager.purge_for_category("foo")

    assert not manager.thumbnail_path("foo/a.png").exists()
    assert manager.thumbnail_path("bar/b.png").exists()


def test_derivatives_ignores_missing_source(tmp_path: Path) -> None:
    manager = DerivativesManager(
        media_root=tmp_path / "media",
        plugin_data_dir=tmp_path / "plugin_data",
    )
    manager.generate_all_sync("not/exist.png", "image")
    assert not manager.thumbnail_path("not/exist.png").exists()
