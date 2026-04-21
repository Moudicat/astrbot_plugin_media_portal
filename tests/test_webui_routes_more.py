from __future__ import annotations

import hashlib
import shutil
import time
from pathlib import Path

from fastapi.testclient import TestClient

from astrbot_plugin_media_portal.core.media_manager import DuplicateMediaError, MediaRecord
from astrbot_plugin_media_portal.core.utils import (
    detect_mime_and_kind,
    guess_filename_from_url,
    slugify_category,
)
from astrbot_plugin_media_portal.webui.server import WebUIServer


class _DummyDownloader:
    def __init__(self, temp_dir: Path) -> None:
        self.temp_dir = temp_dir
        self.temp_dir.mkdir(parents=True, exist_ok=True)


class _CategoryStore:
    def __init__(self) -> None:
        self._descriptions: dict[str, str] = {"default": "默认分类"}

    def get_description(self, category: str) -> str:
        return self._descriptions.get(slugify_category(category), "")

    def set_description(self, category: str, description: str) -> bool:
        self._descriptions[slugify_category(category)] = str(description or "").strip()
        return True

    def delete_category(self, category: str) -> bool:
        return self._descriptions.pop(slugify_category(category), None) is not None


class _RouteMediaManager:
    def __init__(self, media_root: Path, plugin_data_dir: Path, category_store: _CategoryStore):
        self.media_root = media_root
        self.plugin_data_dir = plugin_data_dir
        self.category_store = category_store
        self.downloader = _DummyDownloader(plugin_data_dir / "temp")
        self.max_file_size = 6 * 1024 * 1024
        self._records: dict[int, MediaRecord] = {}
        self._trash_records: dict[int, dict[str, object]] = {}
        self._next_id = 1
        self._next_trash_id = 1
        self._trash_retention_days = 30
        self._categories: set[str] = {"default"}
        self.trash_root = self.plugin_data_dir / "trash"
        self.media_root.mkdir(parents=True, exist_ok=True)
        self.plugin_data_dir.mkdir(parents=True, exist_ok=True)
        self.trash_root.mkdir(parents=True, exist_ok=True)

    def _create_record(
        self,
        file_path: Path,
        category: str,
        description: str = "",
        *,
        sha256: str = "",
    ) -> MediaRecord:
        mime, kind = detect_mime_and_kind(file_path)
        rel_path = f"{category}/{file_path.name}"
        now = time.time()
        digest = sha256 or hashlib.sha256(file_path.read_bytes()).hexdigest()
        record = MediaRecord(
            id=self._next_id,
            category=category,
            filename=file_path.name,
            rel_path=rel_path,
            abs_path=str(file_path.resolve()),
            kind=kind,
            mime=mime,
            size=file_path.stat().st_size,
            sha256=digest,
            source_url="",
            sender_id="",
            description=description.strip(),
            tags=[],
            created_at=now,
            updated_at=now,
        )
        self._records[self._next_id] = record
        self._next_id += 1
        return record

    def _find_by_sha(self, sha256: str) -> MediaRecord | None:
        for record in self._records.values():
            if record.sha256 == sha256:
                return record
        return None

    def _trash_to_payload(self, item: dict[str, object]) -> dict[str, object]:
        payload = dict(item)
        payload["size_human"] = f"{int(payload.get('size') or 0)}B"
        return payload

    async def get_stats(self):
        by_kind: dict[str, int] = {}
        cat_stats: dict[str, dict[str, int]] = {}
        total_size = 0
        for record in self._records.values():
            by_kind[record.kind] = by_kind.get(record.kind, 0) + 1
            item = cat_stats.setdefault(record.category, {"count": 0, "size": 0})
            item["count"] += 1
            item["size"] += int(record.size)
            total_size += int(record.size)

        categories = sorted(self._categories | set(cat_stats.keys()))
        cat_payload = []
        for category in categories:
            item = cat_stats.get(category, {"count": 0, "size": 0})
            cat_payload.append(
                {
                    "category": category,
                    "description": self.category_store.get_description(category),
                    "count": item["count"],
                    "size": item["size"],
                    "size_human": f"{item['size']}B",
                }
            )
        return {
            "categories": cat_payload,
            "total_count": len(self._records),
            "total_size": total_size,
            "by_kind": by_kind,
        }

    async def create_category(self, category: str, description: str = "") -> str:
        normalized = slugify_category(category)
        self._categories.add(normalized)
        self.category_store.set_description(normalized, description)
        (self.media_root / normalized).mkdir(parents=True, exist_ok=True)
        return normalized

    async def rename_category(self, old_name: str, new_name: str):
        old = slugify_category(old_name)
        new = slugify_category(new_name)
        if old == new:
            return True, new
        if old not in self._categories:
            return False, "原分类不存在。"
        if new in self._categories:
            return False, "目标分类已存在。"

        old_dir = self.media_root / old
        new_dir = self.media_root / new
        if old_dir.exists():
            old_dir.rename(new_dir)
        self._categories.discard(old)
        self._categories.add(new)
        old_desc = self.category_store.get_description(old)
        self.category_store.delete_category(old)
        self.category_store.set_description(new, old_desc)

        for record in self._records.values():
            if record.category != old:
                continue
            record.category = new
            record.rel_path = f"{new}/{record.filename}"
            record.abs_path = str((new_dir / record.filename).resolve())
            record.updated_at = time.time()
        return True, new

    async def delete_category(self, category: str, remove_files: bool = True):
        normalized = slugify_category(category)
        target_ids = [rid for rid, rec in self._records.items() if rec.category == normalized]
        deleted_files = 0
        for rid in target_ids:
            record = self._records.pop(rid)
            file_path = Path(record.abs_path)
            if remove_files and file_path.exists():
                file_path.unlink(missing_ok=True)
                deleted_files += 1
        category_dir = self.media_root / normalized
        if remove_files and category_dir.exists():
            shutil.rmtree(category_dir)
        self._categories.discard(normalized)
        self.category_store.delete_category(normalized)
        return {
            "category": normalized,
            "deleted_files": deleted_files,
            "deleted_rows": len(target_ids),
        }

    async def prune_empty_categories(self):
        removed: list[str] = []
        for category in list(self._categories):
            if category == "default":
                continue
            has_records = any(rec.category == category for rec in self._records.values())
            folder = self.media_root / category
            folder_empty = (not folder.exists()) or (
                folder.is_dir() and not any(folder.iterdir())
            )
            if has_records or not folder_empty:
                continue
            self._categories.discard(category)
            self.category_store.delete_category(category)
            removed.append(category)
        return {"removed": removed, "removed_count": len(removed), "folder_cleaned": removed}

    async def list_media(
        self, *, category: str = "", kind: str = "", query: str = "", page: int = 1, page_size: int = 20
    ):
        items = list(self._records.values())
        if category:
            normalized = slugify_category(category)
            items = [item for item in items if item.category == normalized]
        if kind:
            items = [item for item in items if item.kind == kind]
        if query:
            key = query.lower()
            items = [
                item
                for item in items
                if key in item.filename.lower() or key in item.description.lower()
            ]
        total = len(items)
        start = max(0, (int(page) - 1) * int(page_size))
        end = start + int(page_size)
        paged = items[start:end]
        return {
            "items": [item.to_dict() for item in paged],
            "total": total,
            "page": int(page),
            "page_size": int(page_size),
            "total_pages": (total + int(page_size) - 1) // int(page_size) if total else 0,
        }

    async def get_by_id(self, media_id: int):
        return self._records.get(int(media_id))

    async def update_media(
        self,
        media_id: int,
        *,
        description=None,
        tags=None,
        category=None,
        filename=None,
    ):
        record = self._records.get(int(media_id))
        if not record:
            raise ValueError("媒体不存在")
        if category:
            new_category = slugify_category(category)
            if new_category != record.category:
                self._categories.add(new_category)
                (self.media_root / new_category).mkdir(parents=True, exist_ok=True)
                old_path = Path(record.abs_path)
                new_path = self.media_root / new_category / record.filename
                if old_path.exists():
                    old_path.rename(new_path)
                record.category = new_category
                record.rel_path = f"{new_category}/{record.filename}"
                record.abs_path = str(new_path.resolve())
        if filename is not None:
            cleaned = str(filename).strip()
            if not cleaned:
                raise ValueError("filename 不能为空")
            if "." not in cleaned:
                cleaned = f"{cleaned}{Path(record.filename).suffix}"
            if cleaned != record.filename:
                old_path = Path(record.abs_path)
                new_path = old_path.parent / cleaned
                if old_path.exists():
                    old_path.rename(new_path)
                record.filename = cleaned
                record.rel_path = f"{record.category}/{cleaned}"
                record.abs_path = str(new_path.resolve())
        if description is not None:
            record.description = str(description).strip()
        if tags is not None:
            record.tags = [str(item).strip() for item in tags if str(item).strip()]
        record.updated_at = time.time()
        return record

    async def delete_media(self, media_id: int):
        record = self._records.pop(int(media_id), None)
        if not record:
            return False
        Path(record.abs_path).unlink(missing_ok=True)
        return True

    async def trash_media(self, media_id: int):
        record = self._records.pop(int(media_id), None)
        if not record:
            return None
        source = Path(record.abs_path)
        trash_rel_path = ""
        if source.exists() and source.is_file():
            target = self.trash_root / f"{self._next_trash_id}_{source.name}"
            shutil.move(str(source), str(target))
            trash_rel_path = target.name
        deleted_at = time.time()
        trash_id = self._next_trash_id
        self._next_trash_id += 1
        self._trash_records[trash_id] = {
            "id": trash_id,
            "original_media_id": record.id,
            "category": record.category,
            "filename": record.filename,
            "original_rel_path": record.rel_path,
            "trash_rel_path": trash_rel_path,
            "kind": record.kind,
            "mime": record.mime,
            "size": int(record.size),
            "sha256": record.sha256,
            "source_url": record.source_url,
            "sender_id": record.sender_id,
            "description": record.description,
            "tags": list(record.tags),
            "created_at": float(record.created_at),
            "updated_at": float(record.updated_at),
            "deleted_at": deleted_at,
        }
        return type("_Trashed", (), {"id": trash_id})()

    async def list_trash(
        self,
        *,
        category: str = "",
        query: str = "",
        page: int = 1,
        page_size: int = 20,
    ):
        items = list(self._trash_records.values())
        if category:
            normalized = slugify_category(category)
            items = [item for item in items if str(item["category"]) == normalized]
        key = query.strip().lower()
        if key:
            items = [
                item
                for item in items
                if key in str(item["filename"]).lower()
                or key in str(item["description"]).lower()
                or key in str(item["sha256"]).lower()
            ]
        items.sort(key=lambda item: float(item.get("deleted_at") or 0), reverse=True)
        total = len(items)
        safe_page = max(1, int(page))
        safe_page_size = max(1, int(page_size))
        start = (safe_page - 1) * safe_page_size
        end = start + safe_page_size
        paged = items[start:end]
        return {
            "items": [self._trash_to_payload(item) for item in paged],
            "total": total,
            "page": safe_page,
            "page_size": safe_page_size,
            "total_pages": (total + safe_page_size - 1) // safe_page_size if total else 0,
        }

    async def get_trash_stats(self):
        total_size = sum(int(item.get("size") or 0) for item in self._trash_records.values())
        now = time.time()
        threshold = now - self._trash_retention_days * 86400
        expired = sum(
            1
            for item in self._trash_records.values()
            if float(item.get("deleted_at") or 0) <= threshold
        )
        return {
            "total_count": len(self._trash_records),
            "total_size": total_size,
            "total_size_human": f"{total_size}B",
            "expired_count": expired,
            "retention_days": self._trash_retention_days,
        }

    async def restore_from_trash(
        self,
        trash_id: int,
        *,
        category: str = "",
        filename: str = "",
    ):
        item = self._trash_records.pop(int(trash_id), None)
        if not item:
            raise ValueError("回收站记录不存在")
        normalized = slugify_category(category or str(item["category"]))
        self._categories.add(normalized)
        target_dir = self.media_root / normalized
        target_dir.mkdir(parents=True, exist_ok=True)
        target_name = Path(filename.strip() or str(item["filename"])).name
        target = target_dir / target_name
        if target.exists():
            target = target_dir / f"{target.stem}_{int(time.time())}{target.suffix}"
        trash_rel = str(item.get("trash_rel_path") or "")
        if trash_rel:
            source = self.trash_root / trash_rel
            if source.exists():
                shutil.move(str(source), str(target))
            else:
                target.write_bytes(b"restored")
        else:
            target.write_bytes(b"restored")
        return self._create_record(
            target,
            normalized,
            description=str(item.get("description") or ""),
            sha256=str(item.get("sha256") or ""),
        )

    async def purge_trash(self, trash_id: int):
        item = self._trash_records.pop(int(trash_id), None)
        if not item:
            return False
        trash_rel = str(item.get("trash_rel_path") or "")
        if trash_rel:
            (self.trash_root / trash_rel).unlink(missing_ok=True)
        return True

    async def purge_expired_trash(self, retention_days: int = 30):
        now = time.time()
        threshold = now - max(1, int(retention_days)) * 86400
        purged = 0
        for trash_id, item in list(self._trash_records.items()):
            if float(item.get("deleted_at") or 0) > threshold:
                continue
            if await self.purge_trash(trash_id):
                purged += 1
        return {"purged": purged}

    async def get_trash_retention_days(self):
        return self._trash_retention_days

    async def set_trash_retention_days(self, days: int):
        self._trash_retention_days = max(1, int(days))
        return self._trash_retention_days

    async def list_duplicate_groups(self, *, mode: str = "exact", page: int = 1, page_size: int = 20):
        grouped: dict[str, list[MediaRecord]] = {}
        for record in self._records.values():
            grouped.setdefault(record.sha256, []).append(record)
        groups = [
            {
                "group_key": f"sha:{key}",
                "reason": "sha256",
                "confidence": "exact",
                "count": len(records),
                "items": [item.to_dict() for item in records],
            }
            for key, records in grouped.items()
            if len(records) > 1
        ]
        total = len(groups)
        safe_page = max(1, int(page))
        safe_page_size = max(1, int(page_size))
        start = (safe_page - 1) * safe_page_size
        end = start + safe_page_size
        return {
            "items": groups[start:end],
            "total": total,
            "page": safe_page,
            "page_size": safe_page_size,
            "total_pages": (total + safe_page_size - 1) // safe_page_size if total else 0,
            "mode": "exact",
        }

    async def save_from_local_path(
        self,
        src_path: str,
        *,
        category: str = "default",
        description: str = "",
        filename: str = "",
        move: bool | None = None,
        duplicate_policy: str = "error",
        **_kwargs,
    ):
        source = Path(src_path).resolve()
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(f"本地文件不存在: {src_path}")
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        policy = str(duplicate_policy or "error")
        if policy != "force":
            existing = self._find_by_sha(source_hash)
            if existing:
                if policy == "error":
                    raise DuplicateMediaError(existing)
                return existing
        normalized = slugify_category(category)
        self._categories.add(normalized)
        target_dir = self.media_root / normalized
        target_dir.mkdir(parents=True, exist_ok=True)
        target_name = filename or source.name
        target = target_dir / Path(target_name).name
        if move is False:
            shutil.copy2(source, target)
        else:
            shutil.move(str(source), str(target))
        return self._create_record(target, normalized, description=description, sha256=source_hash)

    async def save_from_url(
        self,
        url: str,
        *,
        category: str = "default",
        description: str = "",
        filename: str = "",
        duplicate_policy: str = "error",
    ):
        temp_name = filename.strip() or guess_filename_from_url(url, default="remote")
        temp_file = self.downloader.temp_dir / temp_name
        temp_file.write_bytes(b"downloaded")
        return await self.save_from_local_path(
            str(temp_file),
            category=category,
            description=description,
            filename=temp_name,
            move=True,
            duplicate_policy=duplicate_policy,
        )


def _build_server(tmp_path: Path) -> WebUIServer:
    media_root = (tmp_path / "media").resolve()
    plugin_data_dir = (tmp_path / "plugin_data").resolve()
    data_root = (tmp_path / "astrbot_data").resolve()
    media_root.mkdir(parents=True, exist_ok=True)
    plugin_data_dir.mkdir(parents=True, exist_ok=True)
    data_root.mkdir(parents=True, exist_ok=True)

    category_store = _CategoryStore()
    media_manager = _RouteMediaManager(media_root, plugin_data_dir, category_store)
    return WebUIServer(
        media_manager=media_manager,
        category_manager=category_store,
        config={
            "enabled": True,
            "host": "127.0.0.1",
            "port": 7003,
            "access_password": "secret",
            "session_timeout": 3600,
            "public_base_url": "",
            "expose_astrbot_data": True,
            "allowed_origins": [],
            "readonly_token_ttl": 3600,
            "share_url_ttl": 3600,
            "data_token_ttl": 3600,
        },
        data_root=data_root,
    )


def _auth_header(client: TestClient) -> dict[str, str]:
    login = client.post("/api/login", json={"password": "secret"})
    assert login.status_code == 200
    token = login.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_category_and_media_crud_endpoints(tmp_path: Path) -> None:
    server = _build_server(tmp_path)
    client = TestClient(server.app)
    headers = _auth_header(client)

    created = client.post(
        "/api/categories",
        headers=headers,
        json={"category": "图库", "description": "图片集合"},
    )
    assert created.status_code == 200
    assert created.json()["category"] == "图库"

    patched = client.patch(
        "/api/categories/%E5%9B%BE%E5%BA%93",
        headers=headers,
        json={"new_name": "图库_新", "description": "新描述"},
    )
    assert patched.status_code == 200
    assert patched.json()["category"] == "图库_新"

    upload = client.post(
        "/api/media/upload",
        headers=headers,
        data={"category": "图库_新", "description": "来自上传"},
        files=[("files", ("cat.png", b"image-binary", "image/png"))],
    )
    assert upload.status_code == 200
    saved_items = upload.json()["saved"]
    assert len(saved_items) == 1
    media_id = int(saved_items[0]["id"])

    listed = client.get("/api/media?category=%E5%9B%BE%E5%BA%93_%E6%96%B0", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    detail = client.get(f"/api/media/{media_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["public_url"]

    updated = client.patch(
        f"/api/media/{media_id}",
        headers=headers,
        json={"description": "更新后", "tags": ["tag1"], "category": "归档"},
    )
    assert updated.status_code == 200
    assert updated.json()["category"] == "归档"
    assert updated.json()["description"] == "更新后"

    deleted = client.delete(f"/api/media/{media_id}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.delete(f"/api/media/{media_id}", headers=headers).status_code == 404


def test_save_url_upload_validation_and_prune(tmp_path: Path) -> None:
    server = _build_server(tmp_path)
    client = TestClient(server.app)
    headers = _auth_header(client)

    assert client.post("/api/media/save-url", headers=headers, json={}).status_code == 400
    saved = client.post(
        "/api/media/save-url",
        headers=headers,
        json={"url": "https://example.com/demo.png", "category": "remote"},
    )
    assert saved.status_code == 200
    payload = saved.json()
    assert payload["category"] == "remote"
    assert payload["public_url"]

    assert (
        client.post("/api/media/upload", headers=headers, data={"category": "remote"}).status_code
        == 400
    )

    deleted = client.delete("/api/categories/remote", headers=headers)
    assert deleted.status_code == 200

    pruned = client.post("/api/categories/prune", headers=headers)
    assert pruned.status_code == 200
    assert "removed_count" in pruned.json()


def test_trash_duplicates_and_settings_endpoints(tmp_path: Path) -> None:
    server = _build_server(tmp_path)
    client = TestClient(server.app)
    headers = _auth_header(client)

    uploaded = client.post(
        "/api/media/upload",
        headers=headers,
        data={"category": "dup", "description": "first"},
        files=[("files", ("same.png", b"same-bytes", "image/png"))],
    )
    assert uploaded.status_code == 200
    first_id = int(uploaded.json()["saved"][0]["id"])

    duplicated = client.post(
        "/api/media/upload",
        headers=headers,
        data={"category": "dup", "description": "dup-hit"},
        files=[("files", ("same.png", b"same-bytes", "image/png"))],
    )
    assert duplicated.status_code == 200
    dup_payload = duplicated.json()
    assert len(dup_payload["duplicates"]) == 1
    assert dup_payload["duplicates"][0]["code"] == "duplicate_sha256"

    forced = client.post(
        "/api/media/upload",
        headers=headers,
        data={"category": "dup", "description": "dup-force", "duplicate_policy": "force"},
        files=[("files", ("same-copy.png", b"same-bytes", "image/png"))],
    )
    assert forced.status_code == 200
    assert len(forced.json()["saved"]) == 1

    exact_groups = client.get("/api/media/duplicates?mode=exact", headers=headers)
    assert exact_groups.status_code == 200
    assert exact_groups.json()["total"] >= 1

    deleted = client.delete(f"/api/media/{first_id}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["soft_deleted"] is True
    trash_id = int(deleted.json()["trash_id"])

    trash_list = client.get("/api/trash", headers=headers)
    assert trash_list.status_code == 200
    assert trash_list.json()["total"] >= 1
    assert "remaining_days" in trash_list.json()["items"][0]

    trash_stats = client.get("/api/trash/stats", headers=headers)
    assert trash_stats.status_code == 200
    assert trash_stats.json()["total_count"] >= 1

    settings_before = client.get("/api/settings/trash", headers=headers)
    assert settings_before.status_code == 200
    assert settings_before.json()["trash_retention_days"] >= 1

    settings_after = client.patch(
        "/api/settings/trash",
        headers=headers,
        json={"trash_retention_days": 7},
    )
    assert settings_after.status_code == 200
    assert settings_after.json()["trash_retention_days"] == 7

    purged_expired = client.post("/api/trash/purge-expired", headers=headers)
    assert purged_expired.status_code == 200
    assert "purged" in purged_expired.json()

    restored = client.post(f"/api/trash/{trash_id}/restore", headers=headers, json={})
    assert restored.status_code == 200
    restored_id = int(restored.json()["id"])

    deleted_again = client.delete(f"/api/media/{restored_id}", headers=headers)
    assert deleted_again.status_code == 200
    trash_id_2 = int(deleted_again.json()["trash_id"])

    purged = client.delete(f"/api/trash/{trash_id_2}", headers=headers)
    assert purged.status_code == 200
    assert purged.json()["deleted"] is True

    first_save_url = client.post(
        "/api/media/save-url",
        headers=headers,
        json={"url": "https://example.com/sample.png", "category": "urlcat"},
    )
    assert first_save_url.status_code == 200

    duplicate_save_url = client.post(
        "/api/media/save-url",
        headers=headers,
        json={"url": "https://example.com/sample2.png", "category": "urlcat"},
    )
    assert duplicate_save_url.status_code == 409
    assert duplicate_save_url.json()["detail"]["code"] == "duplicate_sha256"

    forced_save_url = client.post(
        "/api/media/save-url",
        headers=headers,
        json={
            "url": "https://example.com/sample3.png",
            "category": "urlcat",
            "duplicate_policy": "force",
        },
    )
    assert forced_save_url.status_code == 200
