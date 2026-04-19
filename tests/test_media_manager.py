from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from core.category_manager import CategoryManager
from core.downloader import DownloadedFile, MediaDownloader
from core.media_manager import MediaManager


def _build_manager(base_dir: Path) -> MediaManager:
    return _build_manager_with_options(base_dir)


def _build_manager_with_options(
    base_dir: Path,
    *,
    allowed_kinds: set[str] | None = None,
    max_file_size_mb: int = 5,
) -> MediaManager:
    plugin_data_dir = (base_dir / "plugin_data").resolve()
    media_root = (base_dir / "media").resolve()
    category_manager = CategoryManager(
        categories_file=plugin_data_dir / "categories.json",
        media_root=media_root,
    )
    downloader = MediaDownloader(
        temp_dir=plugin_data_dir / "temp",
        max_file_size_mb=max_file_size_mb,
    )
    return MediaManager(
        media_root=media_root,
        plugin_data_dir=plugin_data_dir,
        category_manager=category_manager,
        downloader=downloader,
        allowed_kinds=allowed_kinds or {"image", "video", "audio"},
        max_file_size_mb=max_file_size_mb,
        default_move_local=True,
    )


def test_save_from_local_path_and_list_media(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = _build_manager(tmp_path)
        await manager.initialize()
        try:
            source = tmp_path / "cat.png"
            source.write_bytes(b"fake-image-data")

            record = await manager.save_from_local_path(
                str(source),
                category="cats",
                description="  cute cat ",
                move=False,
            )

            payload = await manager.list_media(category="cats", page=1, page_size=10)
            assert record.id > 0
            assert record.category == "cats"
            assert Path(record.abs_path).exists()
            assert payload["total"] == 1
            assert payload["items"][0]["description"] == "cute cat"
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_save_from_local_path_deduplicates_by_sha256(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = _build_manager(tmp_path)
        await manager.initialize()
        try:
            first = tmp_path / "first.jpg"
            first.write_bytes(b"same-content")
            first_record = await manager.save_from_local_path(
                str(first), category="dup", move=False
            )

            duplicate = tmp_path / "duplicate.jpg"
            duplicate.write_bytes(b"same-content")
            second_record = await manager.save_from_local_path(
                str(duplicate), category="dup", move=True
            )

            payload = await manager.list_media(category="dup", page=1, page_size=10)
            assert first_record.id == second_record.id
            assert payload["total"] == 1
            assert duplicate.exists() is False
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_save_from_local_path_rejects_unsupported_kind(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = _build_manager(tmp_path)
        await manager.initialize()
        try:
            source = tmp_path / "notes.txt"
            source.write_text("hello", encoding="utf-8")
            with pytest.raises(ValueError, match="文件类型不受支持"):
                await manager.save_from_local_path(str(source), category="text")
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_update_and_move_media(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = _build_manager(tmp_path)
        await manager.initialize()
        try:
            source = tmp_path / "voice.mp3"
            source.write_bytes(b"audio")
            record = await manager.save_from_local_path(
                str(source), category="music", move=False
            )

            updated = await manager.update_media(
                record.id,
                description=" lo-fi ",
                tags=[" chill ", "", "focus "],
            )
            moved = await manager.move_media(record.id, "podcast")

            assert updated.description == "lo-fi"
            assert updated.tags == ["chill", "focus"]
            assert moved.category == "podcast"
            assert moved.rel_path.startswith("podcast/")
            assert Path(moved.abs_path).exists()
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_ensure_scanned_indexes_and_prunes(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = _build_manager(tmp_path)
        await manager.initialize()
        try:
            category_dir = manager.media_root / "scan"
            category_dir.mkdir(parents=True, exist_ok=True)
            file_path = category_dir / "new.png"
            file_path.write_bytes(b"scan-me")

            first_scan = await manager.ensure_scanned()
            payload = await manager.list_media(category="scan", page=1, page_size=10)

            file_path.unlink()
            second_scan = await manager.ensure_scanned()
            payload_after = await manager.list_media(category="scan", page=1, page_size=10)

            assert first_scan["indexed"] == 1
            assert payload["total"] == 1
            assert second_scan["removed"] == 1
            assert payload_after["total"] == 0
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_delete_category_removes_rows_and_files(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = _build_manager(tmp_path)
        await manager.initialize()
        try:
            source = tmp_path / "trash.jpg"
            source.write_bytes(b"trash")
            record = await manager.save_from_local_path(
                str(source), category="trash", move=False
            )

            result = await manager.delete_category("trash", remove_files=True)
            payload = await manager.list_media(category="trash", page=1, page_size=10)

            assert result["deleted_rows"] == 1
            assert result["deleted_files"] == 1
            assert payload["total"] == 0
            assert Path(record.abs_path).exists() is False
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_delete_media_returns_false_when_missing(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = _build_manager(tmp_path)
        await manager.initialize()
        try:
            assert await manager.delete_media(999999) is False
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_rename_category_moves_files_and_updates_records(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = _build_manager(tmp_path)
        await manager.initialize()
        try:
            source = tmp_path / "rename_me.jpg"
            source.write_bytes(b"rename")
            record = await manager.save_from_local_path(
                str(source), category="oldcat", move=False
            )

            ok, target = await manager.rename_category("oldcat", "newcat")
            refreshed = await manager.get_by_id(record.id)

            assert ok is True
            assert target == "newcat"
            assert refreshed is not None
            assert refreshed.category == "newcat"
            assert refreshed.rel_path.startswith("newcat/")
            assert Path(refreshed.abs_path).exists()
            assert (manager.media_root / "oldcat").exists() is False
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_rename_category_rejects_existing_target(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = _build_manager(tmp_path)
        await manager.initialize()
        try:
            source = tmp_path / "exists.jpg"
            source.write_bytes(b"exists")
            await manager.save_from_local_path(str(source), category="src", move=False)
            await manager.create_category("dst")

            ok, message = await manager.rename_category("src", "dst")

            assert ok is False
            assert "目标分类已存在" in message
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_prune_empty_categories_removes_non_default_only(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = _build_manager(tmp_path)
        await manager.initialize()
        try:
            await manager.create_category("empty")
            result = await manager.prune_empty_categories()

            assert "empty" in result["removed"]
            assert "default" not in result["removed"]
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_delete_category_without_removing_files_keeps_physical_file(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = _build_manager(tmp_path)
        await manager.initialize()
        try:
            source = tmp_path / "keep.jpg"
            source.write_bytes(b"keep")
            record = await manager.save_from_local_path(
                str(source), category="keepcat", move=False
            )

            result = await manager.delete_category("keepcat", remove_files=False)
            payload = await manager.list_media(category="keepcat", page=1, page_size=10)

            assert result["deleted_rows"] == 1
            assert result["deleted_files"] == 0
            assert payload["total"] == 0
            assert Path(record.abs_path).exists() is True
            assert (manager.media_root / "keepcat").exists() is True
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_save_from_url_moves_downloaded_file_and_cleans_temp(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = _build_manager(tmp_path)
        await manager.initialize()
        try:
            downloaded = tmp_path / "downloaded.png"
            downloaded.write_bytes(b"downloaded-image")

            async def fake_download_to_temp(url: str, filename_hint: str = "") -> DownloadedFile:
                _ = (url, filename_hint)
                return DownloadedFile(path=downloaded, filename="remote.png", content_type="image/png")

            manager.downloader.download_to_temp = fake_download_to_temp  # type: ignore[method-assign]

            record = await manager.save_from_url(
                "https://example.com/remote.png",
                category="remote",
                description="from-url",
            )

            assert record.category == "remote"
            assert Path(record.abs_path).exists()
            assert downloaded.exists() is False
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_save_from_event_returns_partial_errors(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = _build_manager(tmp_path)
        await manager.initialize()
        try:
            valid_file = tmp_path / "ok.jpg"
            valid_file.write_bytes(b"ok")
            missing_file = tmp_path / "missing.jpg"

            async def fake_extract(_event):
                return [
                    manager.downloader.parse_source(str(valid_file)),
                    manager.downloader.parse_source(str(missing_file)),
                ]

            manager.downloader.extract_sources_from_event = fake_extract  # type: ignore[method-assign]

            result = await manager.save_from_event(object(), category="batch")

            assert len(result["saved"]) == 1
            assert len(result["errors"]) == 1
            assert "本地文件不存在" in result["errors"][0]
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_list_media_and_search_support_query_and_paging(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = _build_manager(tmp_path)
        await manager.initialize()
        try:
            f1 = tmp_path / "alpha.jpg"
            f1.write_bytes(b"a")
            f2 = tmp_path / "beta.jpg"
            f2.write_bytes(b"b")

            await manager.save_from_local_path(
                str(f1),
                category="gallery",
                description="alpha item",
                tags=["cat", "meme"],
                move=False,
            )
            await manager.save_from_local_path(
                str(f2),
                category="gallery",
                description="beta item",
                tags=["dog"],
                move=False,
            )

            list_page_1 = await manager.list_media(query="item", page=1, page_size=1)
            list_page_2 = await manager.list_media(query="item", page=2, page_size=1)
            search_alpha = await manager.search_media("alpha", limit=5, category="gallery")
            search_blank = await manager.search_media("   ", limit=5, category="gallery")

            assert list_page_1["total"] == 2
            assert list_page_1["total_pages"] == 2
            assert len(list_page_1["items"]) == 1
            assert len(list_page_2["items"]) == 1
            assert len(search_alpha) == 1
            assert search_alpha[0].filename == "alpha.jpg"
            assert search_blank == []
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_get_stats_counts_by_kind_and_category(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = _build_manager(tmp_path)
        await manager.initialize()
        try:
            image = tmp_path / "i.png"
            image.write_bytes(b"img")
            audio = tmp_path / "a.mp3"
            audio.write_bytes(b"aud")

            await manager.save_from_local_path(str(image), category="mix", move=False)
            await manager.save_from_local_path(str(audio), category="mix", move=False)

            stats = await manager.get_stats()
            by_kind = stats["by_kind"]
            categories = {item["category"]: item for item in stats["categories"]}

            assert stats["total_count"] == 2
            assert by_kind["image"] == 1
            assert by_kind["audio"] == 1
            assert categories["mix"]["count"] == 2
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_save_from_event_returns_error_when_no_sources(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = _build_manager(tmp_path)
        await manager.initialize()
        try:
            async def fake_extract(_event):
                return []

            manager.downloader.extract_sources_from_event = fake_extract  # type: ignore[method-assign]
            result = await manager.save_from_event(object(), category="empty")
            assert result["saved"] == []
            assert result["errors"] == ["未在消息中找到可保存的媒体。"]
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_list_recent_in_category_with_kind_filter(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = _build_manager(tmp_path)
        await manager.initialize()
        try:
            image = tmp_path / "x.png"
            image.write_bytes(b"img")
            audio = tmp_path / "x.mp3"
            audio.write_bytes(b"aud")
            await manager.save_from_local_path(str(image), category="recent", move=False)
            await manager.save_from_local_path(str(audio), category="recent", move=False)

            only_images = await manager.list_recent_in_category("recent", kind="image", limit=10)
            all_items = await manager.list_recent_in_category("recent", limit=10)

            assert len(only_images) == 1
            assert only_images[0].kind == "image"
            assert len(all_items) == 2
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_update_media_and_move_media_raise_when_missing_or_file_lost(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = _build_manager(tmp_path)
        await manager.initialize()
        try:
            with pytest.raises(ValueError, match="媒体不存在"):
                await manager.update_media(123456, description="x")
            with pytest.raises(ValueError, match="媒体不存在"):
                await manager.move_media(123456, "x")

            source = tmp_path / "lost.jpg"
            source.write_bytes(b"lost")
            record = await manager.save_from_local_path(str(source), category="lost", move=False)
            Path(record.abs_path).unlink(missing_ok=True)
            with pytest.raises(FileNotFoundError, match="媒体文件已不存在"):
                await manager.move_media(record.id, "newcat")
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_prune_empty_categories_respects_protected_set(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = _build_manager(tmp_path)
        await manager.initialize()
        try:
            await manager.create_category("keepme")
            await manager.create_category("dropme")
            result = await manager.prune_empty_categories(protected={"default", "keepme"})

            assert "keepme" not in result["removed"]
            assert "dropme" in result["removed"]
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_ensure_scanned_counts_skipped_for_disallowed_kind(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = _build_manager_with_options(tmp_path, allowed_kinds={"image"})
        await manager.initialize()
        try:
            folder = manager.media_root / "scan_kinds"
            folder.mkdir(parents=True, exist_ok=True)
            image = folder / "ok.png"
            image.write_bytes(b"img")
            audio = folder / "skip.mp3"
            audio.write_bytes(b"aud")

            result = await manager.ensure_scanned()
            listed = await manager.list_media(category="scan_kinds", page=1, page_size=10)

            assert result["indexed"] == 1
            assert result["skipped"] == 1
            assert listed["total"] == 1
            assert listed["items"][0]["kind"] == "image"
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_save_from_local_path_rolls_back_file_on_index_failure(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = _build_manager(tmp_path)
        await manager.initialize()
        try:
            source = tmp_path / "rollback.jpg"
            source.write_bytes(b"rollback")

            async def fake_insert_record(*args, **kwargs):
                _ = (args, kwargs)
                raise RuntimeError("db-fail")

            manager._insert_record = fake_insert_record  # type: ignore[method-assign]

            with pytest.raises(RuntimeError, match="db-fail"):
                await manager.save_from_local_path(
                    str(source),
                    category="rollback",
                    move=True,
                )

            assert source.exists() is True
            rollback_dir = manager.media_root / "rollback"
            assert list(rollback_dir.glob("*")) == []
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_move_media_rolls_back_file_when_index_update_fails(
    tmp_path: Path, monkeypatch
) -> None:
    async def scenario() -> None:
        manager = _build_manager(tmp_path)
        await manager.initialize()
        try:
            source = tmp_path / "move_fail.jpg"
            source.write_bytes(b"move-fail")
            record = await manager.save_from_local_path(
                str(source), category="src", move=False
            )
            original_path = Path(record.abs_path)
            conn = await manager._ensure_conn()
            original_execute = conn.execute

            async def fail_execute(sql: str, parameters=()):
                normalized_sql = " ".join(sql.split())
                if normalized_sql.startswith(
                    "UPDATE media SET category = ?, filename = ?, rel_path = ?, updated_at = ?"
                ):
                    raise RuntimeError("move-db-fail")
                return await original_execute(sql, parameters)

            monkeypatch.setattr(conn, "execute", fail_execute)

            with pytest.raises(RuntimeError, match="move-db-fail"):
                await manager.move_media(record.id, "dst")

            refreshed = await manager.get_by_id(record.id)
            assert refreshed is not None
            assert refreshed.category == "src"
            assert Path(refreshed.abs_path) == original_path
            assert original_path.exists() is True
            assert (manager.media_root / "dst" / original_path.name).exists() is False
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_rename_category_rolls_back_when_index_update_fails(
    tmp_path: Path, monkeypatch
) -> None:
    async def scenario() -> None:
        manager = _build_manager(tmp_path)
        await manager.initialize()
        try:
            source = tmp_path / "rename_fail.jpg"
            source.write_bytes(b"rename-fail")
            record = await manager.save_from_local_path(
                str(source), category="oldcat", move=False
            )
            conn = await manager._ensure_conn()
            original_execute = conn.execute

            async def fail_execute(sql: str, parameters=()):
                normalized_sql = " ".join(sql.split())
                if normalized_sql.startswith(
                    "UPDATE media SET category = ?, rel_path = ?, updated_at = ?"
                ):
                    raise RuntimeError("rename-db-fail")
                return await original_execute(sql, parameters)

            monkeypatch.setattr(conn, "execute", fail_execute)

            with pytest.raises(RuntimeError, match="rename-db-fail"):
                await manager.rename_category("oldcat", "newcat")

            refreshed = await manager.get_by_id(record.id)
            assert refreshed is not None
            assert refreshed.category == "oldcat"
            assert refreshed.rel_path.startswith("oldcat/")
            assert Path(refreshed.abs_path).exists() is True
            assert (manager.media_root / "oldcat").exists() is True
            assert (manager.media_root / "newcat").exists() is False
            assert "newcat" not in manager.category_manager.list_categories()
        finally:
            await manager.close()

    asyncio.run(scenario())
