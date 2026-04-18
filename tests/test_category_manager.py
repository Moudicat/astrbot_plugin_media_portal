from __future__ import annotations

from pathlib import Path

from core.category_manager import CategoryManager


def test_category_manager_initializes_default_and_syncs_folders(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    (media_root / "cats").mkdir(parents=True)
    (media_root / "video clips").mkdir(parents=True)
    categories_file = tmp_path / "categories.json"

    manager = CategoryManager(categories_file=categories_file, media_root=media_root)
    categories = manager.list_categories()

    assert "default" in categories
    assert "cats" in categories
    assert "video_clips" in categories
    assert manager.get_description("default") == "默认分类"
    assert categories_file.exists()


def test_category_manager_loads_invalid_json_gracefully(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True)
    categories_file = tmp_path / "categories.json"
    categories_file.write_text("{ not-valid-json ", encoding="utf-8")

    manager = CategoryManager(categories_file=categories_file, media_root=media_root)

    assert "default" in manager.list_categories()
    assert manager.ensure_category("notes") == "notes"


def test_category_manager_rename_and_prune_missing_folder(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    categories_file = tmp_path / "categories.json"
    manager = CategoryManager(categories_file=categories_file, media_root=media_root)

    manager.ensure_category("图库", description="图片资源")
    renamed, new_name = manager.rename_category("图库", "gallery")
    removed = manager.prune_missing_folders()

    assert renamed is True
    assert new_name == "gallery"
    assert "gallery" in removed
    assert "default" not in removed


def test_category_manager_export_with_counts_merges_sources(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    categories_file = tmp_path / "categories.json"
    manager = CategoryManager(categories_file=categories_file, media_root=media_root)
    manager.ensure_category("photos", description="摄影")

    exported = manager.export_with_counts(
        {
            "photos": {"count": 2, "size": 2048},
            "orphans": {"count": 1, "size": 10},
        }
    )
    by_category = {item["category"]: item for item in exported}

    assert by_category["photos"]["description"] == "摄影"
    assert by_category["photos"]["count"] == 2
    assert by_category["photos"]["size_human"] == "2.0KB"
    assert by_category["orphans"]["count"] == 1
    assert "default" in by_category


def test_category_manager_set_and_delete_description(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    categories_file = tmp_path / "categories.json"
    manager = CategoryManager(categories_file=categories_file, media_root=media_root)

    assert manager.set_description("notes", "  note desc  ") is True
    assert manager.get_description("notes") == "note desc"
    assert manager.delete_category("notes") is True
    assert manager.delete_category("notes") is False


def test_category_manager_rename_conflict(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    categories_file = tmp_path / "categories.json"
    manager = CategoryManager(categories_file=categories_file, media_root=media_root)
    manager.ensure_category("a")
    manager.ensure_category("b")

    ok, name = manager.rename_category("a", "b")
    assert ok is False
    assert name == "b"
