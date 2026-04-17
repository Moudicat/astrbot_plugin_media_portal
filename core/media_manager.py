"""媒体索引与文件管理。"""

from __future__ import annotations

import asyncio
import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import aiosqlite

from astrbot.api import logger

from .category_manager import CategoryManager
from .downloader import MediaDownloader
from .utils import (
    detect_mime_and_kind,
    ensure_dir,
    file_sha256,
    format_size,
    is_kind_allowed,
    now_ts,
    relative_posix,
    sanitize_filename,
    slugify_category,
    unique_path,
)


@dataclass(slots=True)
class MediaRecord:
    id: int
    category: str
    filename: str
    rel_path: str
    abs_path: str
    kind: str
    mime: str
    size: int
    sha256: str
    source_url: str
    sender_id: str
    description: str
    tags: list[str]
    created_at: float
    updated_at: float

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["size_human"] = format_size(self.size)
        return payload


class MediaManager:
    def __init__(
        self,
        media_root: Path,
        plugin_data_dir: Path,
        category_manager: CategoryManager,
        downloader: MediaDownloader,
        allowed_kinds: set[str],
        max_file_size_mb: int = 50,
        default_move_local: bool = True,
    ):
        self.media_root = ensure_dir(media_root.resolve())
        self.plugin_data_dir = ensure_dir(plugin_data_dir.resolve())
        self.category_manager = category_manager
        self.downloader = downloader
        self.allowed_kinds = {kind.lower() for kind in allowed_kinds}
        self.max_file_size = max_file_size_mb * 1024 * 1024
        self.default_move_local = default_move_local
        self.db_path = self.plugin_data_dir / "index.db"
        self._conn: aiosqlite.Connection | None = None
        self._db_lock = asyncio.Lock()

    async def initialize(self) -> None:
        async with self._db_lock:
            if self._conn:
                return
            self._conn = await aiosqlite.connect(self.db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS media (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    rel_path TEXT NOT NULL UNIQUE,
                    kind TEXT NOT NULL,
                    mime TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    source_url TEXT DEFAULT '',
                    sender_id TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            await self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_category_created ON media(category, created_at DESC)"
            )
            await self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_sha256 ON media(sha256)"
            )
            await self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_kind ON media(kind)"
            )
            await self._conn.commit()

    async def close(self) -> None:
        async with self._db_lock:
            if self._conn:
                await self._conn.close()
            self._conn = None

    async def _ensure_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            await self.initialize()
        assert self._conn is not None
        return self._conn

    @staticmethod
    def _parse_tags(tags: Any) -> list[str]:
        if tags is None:
            return []
        if isinstance(tags, str):
            raw = tags.strip()
            if not raw:
                return []
            if raw.startswith("["):
                try:
                    data = json.loads(raw)
                    if isinstance(data, list):
                        return [str(item).strip() for item in data if str(item).strip()]
                except Exception:
                    pass
            return [item.strip() for item in raw.replace("，", ",").split(",") if item.strip()]
        if isinstance(tags, (list, tuple, set)):
            return [str(item).strip() for item in tags if str(item).strip()]
        return []

    def _row_to_record(self, row: aiosqlite.Row) -> MediaRecord:
        tags = self._parse_tags(row["tags"])
        abs_path = str((self.media_root / row["rel_path"]).resolve())
        return MediaRecord(
            id=int(row["id"]),
            category=str(row["category"]),
            filename=str(row["filename"]),
            rel_path=str(row["rel_path"]),
            abs_path=abs_path,
            kind=str(row["kind"]),
            mime=str(row["mime"]),
            size=int(row["size"]),
            sha256=str(row["sha256"]),
            source_url=str(row["source_url"] or ""),
            sender_id=str(row["sender_id"] or ""),
            description=str(row["description"] or ""),
            tags=tags,
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
        )

    async def _insert_record(
        self,
        *,
        category: str,
        filename: str,
        rel_path: str,
        kind: str,
        mime: str,
        size: int,
        sha256: str,
        source_url: str = "",
        sender_id: str = "",
        description: str = "",
        tags: list[str] | None = None,
    ) -> MediaRecord:
        conn = await self._ensure_conn()
        created_at = now_ts()
        tags_json = json.dumps(tags or [], ensure_ascii=False)
        cursor = await conn.execute(
            """
            INSERT INTO media (
                category, filename, rel_path, kind, mime, size, sha256,
                source_url, sender_id, description, tags, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                category,
                filename,
                rel_path,
                kind,
                mime,
                size,
                sha256,
                source_url,
                sender_id,
                description,
                tags_json,
                created_at,
                created_at,
            ),
        )
        await conn.commit()
        media_id = int(cursor.lastrowid)
        return MediaRecord(
            id=media_id,
            category=category,
            filename=filename,
            rel_path=rel_path,
            abs_path=str((self.media_root / rel_path).resolve()),
            kind=kind,
            mime=mime,
            size=size,
            sha256=sha256,
            source_url=source_url,
            sender_id=sender_id,
            description=description,
            tags=tags or [],
            created_at=created_at,
            updated_at=created_at,
        )

    async def get_by_id(self, media_id: int) -> MediaRecord | None:
        conn = await self._ensure_conn()
        cursor = await conn.execute("SELECT * FROM media WHERE id = ?", (int(media_id),))
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_record(row)

    async def _get_by_sha256(self, sha256: str) -> MediaRecord | None:
        conn = await self._ensure_conn()
        cursor = await conn.execute(
            "SELECT * FROM media WHERE sha256 = ? ORDER BY created_at DESC LIMIT 1",
            (sha256,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_record(row)

    async def list_media(
        self,
        *,
        category: str = "",
        kind: str = "",
        query: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        conn = await self._ensure_conn()
        page = max(1, int(page))
        page_size = max(1, min(200, int(page_size)))
        offset = (page - 1) * page_size

        where_parts: list[str] = []
        params: list[Any] = []

        if category:
            where_parts.append("category = ?")
            params.append(slugify_category(category))
        if kind:
            where_parts.append("kind = ?")
            params.append(kind.lower())
        if query.strip():
            where_parts.append(
                "(filename LIKE ? OR description LIKE ? OR tags LIKE ? OR category LIKE ?)"
            )
            wildcard = f"%{query.strip()}%"
            params.extend([wildcard, wildcard, wildcard, wildcard])

        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        cursor_total = await conn.execute(
            f"SELECT COUNT(*) AS total FROM media {where_sql}",
            tuple(params),
        )
        total_row = await cursor_total.fetchone()
        total = int(total_row["total"]) if total_row else 0

        cursor = await conn.execute(
            f"""
            SELECT * FROM media
            {where_sql}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params + [page_size, offset]),
        )
        rows = await cursor.fetchall()
        items = [self._row_to_record(row).to_dict() for row in rows]
        total_pages = (total + page_size - 1) // page_size if total else 0
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    async def search_media(
        self,
        query: str,
        *,
        limit: int = 5,
        category: str = "",
    ) -> list[MediaRecord]:
        conn = await self._ensure_conn()
        q = query.strip()
        if not q:
            return []
        limit = max(1, min(50, int(limit)))
        params: list[Any] = []
        where_parts = [
            "(filename LIKE ? OR description LIKE ? OR tags LIKE ? OR category LIKE ?)"
        ]
        wildcard = f"%{q}%"
        params.extend([wildcard, wildcard, wildcard, wildcard])
        if category:
            where_parts.append("category = ?")
            params.append(slugify_category(category))
        where_sql = f"WHERE {' AND '.join(where_parts)}"
        cursor = await conn.execute(
            f"""
            SELECT * FROM media
            {where_sql}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            tuple(params + [limit]),
        )
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    async def list_recent_in_category(
        self, category: str, *, limit: int = 20, kind: str = ""
    ) -> list[MediaRecord]:
        normalized = slugify_category(category)
        conn = await self._ensure_conn()
        limit = max(1, min(100, int(limit)))
        if kind:
            cursor = await conn.execute(
                """
                SELECT * FROM media
                WHERE category = ? AND kind = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (normalized, kind.lower(), limit),
            )
        else:
            cursor = await conn.execute(
                """
                SELECT * FROM media
                WHERE category = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (normalized, limit),
            )
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    async def _build_target_path(
        self, category: str, filename_hint: str, source_path: Path
    ) -> tuple[str, Path]:
        normalized = self.category_manager.ensure_category(category)
        target_dir = ensure_dir(self.media_root / normalized)
        candidate = sanitize_filename(filename_hint, fallback=source_path.name) or source_path.name
        if not Path(candidate).suffix and source_path.suffix:
            candidate = f"{candidate}{source_path.suffix.lower()}"
        target = unique_path(target_dir / candidate)
        return normalized, target

    async def save_from_local_path(
        self,
        src_path: str,
        *,
        category: str = "default",
        description: str = "",
        filename: str = "",
        move: bool | None = None,
        source_url: str = "",
        sender_id: str = "",
        tags: list[str] | None = None,
    ) -> MediaRecord:
        source = Path(src_path).expanduser().resolve()
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(f"本地文件不存在: {src_path}")
        if source.stat().st_size > self.max_file_size:
            raise ValueError("文件过大，超过配置限制。")

        mime, kind = detect_mime_and_kind(source)
        if not is_kind_allowed(kind, self.allowed_kinds):
            raise ValueError(f"文件类型不受支持: {kind}")

        source_hash = file_sha256(source)
        duplicated = await self._get_by_sha256(source_hash)
        should_move = self.default_move_local if move is None else bool(move)
        if duplicated:
            if should_move:
                try:
                    duplicated_path = Path(duplicated.abs_path).resolve()
                    if source != duplicated_path:
                        source.unlink(missing_ok=True)
                except Exception:
                    pass
            return duplicated

        normalized_category, target = await self._build_target_path(
            category,
            filename_hint=filename or source.name,
            source_path=source,
        )

        temp_target = target.with_suffix(f"{target.suffix}.part")
        if temp_target.exists():
            temp_target.unlink(missing_ok=True)
        if should_move:
            shutil.move(str(source), str(temp_target))
        else:
            shutil.copy2(source, temp_target)
        temp_target.replace(target)

        rel_path = relative_posix(target, self.media_root)
        saved = await self._insert_record(
            category=normalized_category,
            filename=target.name,
            rel_path=rel_path,
            kind=kind,
            mime=mime,
            size=target.stat().st_size,
            sha256=source_hash,
            source_url=source_url,
            sender_id=sender_id,
            description=description.strip(),
            tags=self._parse_tags(tags),
        )
        return saved

    async def save_from_url(
        self,
        url: str,
        *,
        category: str = "default",
        description: str = "",
        filename: str = "",
        sender_id: str = "",
        tags: list[str] | None = None,
    ) -> MediaRecord:
        downloaded = await self.downloader.download_to_temp(url, filename_hint=filename)
        try:
            return await self.save_from_local_path(
                str(downloaded.path),
                category=category,
                description=description,
                filename=filename or downloaded.filename,
                move=True,
                source_url=url,
                sender_id=sender_id,
                tags=tags,
            )
        finally:
            try:
                downloaded.path.unlink(missing_ok=True)
            except Exception:
                pass

    async def save_from_event(
        self,
        event: Any,
        *,
        category: str = "default",
        description: str = "",
        move: bool | None = None,
        sender_id: str = "",
    ) -> dict[str, Any]:
        sources = await self.downloader.extract_sources_from_event(event)
        if not sources:
            return {"saved": [], "errors": ["未在消息中找到可保存的媒体。"]}

        saved: list[MediaRecord] = []
        errors: list[str] = []
        for source in sources:
            try:
                if source.source_type == "url":
                    record = await self.save_from_url(
                        source.value,
                        category=category,
                        description=description,
                        filename=source.filename_hint,
                        sender_id=sender_id,
                    )
                else:
                    record = await self.save_from_local_path(
                        source.value,
                        category=category,
                        description=description,
                        filename=source.filename_hint,
                        move=move,
                        sender_id=sender_id,
                    )
                saved.append(record)
            except Exception as exc:
                errors.append(f"{source.value}: {exc}")
        return {"saved": saved, "errors": errors}

    async def update_media(
        self,
        media_id: int,
        *,
        description: str | None = None,
        tags: list[str] | None = None,
        category: str | None = None,
    ) -> MediaRecord:
        record = await self.get_by_id(media_id)
        if not record:
            raise ValueError("媒体不存在。")

        if category and slugify_category(category) != record.category:
            record = await self.move_media(media_id, category)

        conn = await self._ensure_conn()
        fields: list[str] = []
        params: list[Any] = []
        if description is not None:
            fields.append("description = ?")
            params.append(description.strip())
        if tags is not None:
            fields.append("tags = ?")
            params.append(json.dumps(self._parse_tags(tags), ensure_ascii=False))
        if fields:
            fields.append("updated_at = ?")
            params.append(now_ts())
            params.append(int(media_id))
            await conn.execute(
                f"UPDATE media SET {', '.join(fields)} WHERE id = ?",
                tuple(params),
            )
            await conn.commit()
        refreshed = await self.get_by_id(media_id)
        assert refreshed is not None
        return refreshed

    async def delete_media(self, media_id: int) -> bool:
        record = await self.get_by_id(media_id)
        if not record:
            return False
        file_path = Path(record.abs_path)
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception as exc:
                logger.warning("删除媒体文件失败: %s", exc)
        conn = await self._ensure_conn()
        await conn.execute("DELETE FROM media WHERE id = ?", (int(media_id),))
        await conn.commit()
        return True

    async def move_media(self, media_id: int, new_category: str) -> MediaRecord:
        record = await self.get_by_id(media_id)
        if not record:
            raise ValueError("媒体不存在。")
        source = Path(record.abs_path)
        if not source.exists():
            raise FileNotFoundError("媒体文件已不存在。")

        normalized_category = self.category_manager.ensure_category(new_category)
        target_dir = ensure_dir(self.media_root / normalized_category)
        target_path = unique_path(target_dir / source.name)
        source.rename(target_path)

        new_rel_path = relative_posix(target_path, self.media_root)
        conn = await self._ensure_conn()
        await conn.execute(
            """
            UPDATE media
            SET category = ?, filename = ?, rel_path = ?, updated_at = ?
            WHERE id = ?
            """,
            (normalized_category, target_path.name, new_rel_path, now_ts(), int(media_id)),
        )
        await conn.commit()
        refreshed = await self.get_by_id(media_id)
        assert refreshed is not None
        return refreshed

    async def create_category(self, category: str, description: str = "") -> str:
        normalized = self.category_manager.ensure_category(category, description=description)
        if description:
            self.category_manager.set_description(normalized, description)
        return normalized

    async def rename_category(self, old_name: str, new_name: str) -> tuple[bool, str]:
        old_normalized = slugify_category(old_name)
        new_normalized = slugify_category(new_name)
        if old_normalized == new_normalized:
            return True, new_normalized

        old_dir = self.media_root / old_normalized
        new_dir = self.media_root / new_normalized
        if not old_dir.exists():
            return False, "原分类不存在。"
        if new_dir.exists():
            return False, "目标分类已存在。"

        old_dir.rename(new_dir)
        renamed, _target = self.category_manager.rename_category(old_normalized, new_normalized)
        if not renamed:
            return False, "分类元数据重命名失败。"

        conn = await self._ensure_conn()
        cursor = await conn.execute(
            "SELECT id, filename FROM media WHERE category = ?",
            (old_normalized,),
        )
        rows = await cursor.fetchall()
        for row in rows:
            media_id = int(row["id"])
            filename = str(row["filename"])
            rel_path = f"{new_normalized}/{filename}"
            await conn.execute(
                """
                UPDATE media
                SET category = ?, rel_path = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_normalized, rel_path, now_ts(), media_id),
            )
        await conn.commit()
        return True, new_normalized

    async def delete_category(self, category: str, *, remove_files: bool = True) -> dict[str, Any]:
        normalized = slugify_category(category)
        conn = await self._ensure_conn()
        cursor = await conn.execute(
            "SELECT id, rel_path FROM media WHERE category = ?",
            (normalized,),
        )
        rows = await cursor.fetchall()
        deleted_files = 0
        if remove_files:
            for row in rows:
                rel = str(row["rel_path"])
                file_path = (self.media_root / rel).resolve()
                if file_path.exists() and file_path.is_file():
                    try:
                        file_path.unlink()
                        deleted_files += 1
                    except Exception:
                        pass
        await conn.execute("DELETE FROM media WHERE category = ?", (normalized,))
        await conn.commit()

        category_dir = self.media_root / normalized
        if category_dir.exists():
            try:
                shutil.rmtree(category_dir)
            except Exception as exc:
                logger.warning("删除分类目录失败: %s", exc)
        self.category_manager.delete_category(normalized)
        return {"category": normalized, "deleted_files": deleted_files, "deleted_rows": len(rows)}

    async def ensure_scanned(self) -> dict[str, int]:
        """扫描媒体目录并修复索引，同步清理孤儿分类元数据。"""
        self.category_manager.sync_with_filesystem()
        conn = await self._ensure_conn()
        cursor = await conn.execute("SELECT id, rel_path FROM media")
        rows = await cursor.fetchall()
        db_rel_to_id = {str(row["rel_path"]): int(row["id"]) for row in rows}

        fs_rel_paths: set[str] = set()
        indexed = 0
        skipped = 0
        for category_dir in self.media_root.iterdir():
            if not category_dir.is_dir():
                continue
            category = slugify_category(category_dir.name)
            self.category_manager.ensure_category(category)
            for file_path in category_dir.iterdir():
                if not file_path.is_file():
                    continue
                rel = relative_posix(file_path, self.media_root)
                fs_rel_paths.add(rel)
                if rel in db_rel_to_id:
                    continue
                mime, kind = detect_mime_and_kind(file_path)
                if not is_kind_allowed(kind, self.allowed_kinds):
                    skipped += 1
                    continue
                sha256 = file_sha256(file_path)
                await self._insert_record(
                    category=category,
                    filename=file_path.name,
                    rel_path=rel,
                    kind=kind,
                    mime=mime,
                    size=file_path.stat().st_size,
                    sha256=sha256,
                    description="",
                    tags=[],
                )
                indexed += 1

        stale = [rel for rel in db_rel_to_id.keys() if rel not in fs_rel_paths]
        removed = 0
        for rel in stale:
            await conn.execute("DELETE FROM media WHERE rel_path = ?", (rel,))
            removed += 1
        if removed:
            await conn.commit()
        pruned_categories = self.category_manager.prune_missing_folders()
        return {
            "indexed": indexed,
            "removed": removed,
            "skipped": skipped,
            "pruned_categories": len(pruned_categories),
        }

    async def prune_empty_categories(
        self, *, protected: set[str] | None = None
    ) -> dict[str, Any]:
        """移除所有 0 媒体、0 文件的空分类（以及文件夹已缺失的孤儿元数据）。

        - 默认保护 ``default``，不会被清理。
        - 对仍有媒体记录或文件夹非空的分类 **一律不触碰**，确保数据安全。
        """
        keep = {"default"} if protected is None else set(protected)
        conn = await self._ensure_conn()
        cursor = await conn.execute(
            "SELECT category, COUNT(*) AS cnt FROM media GROUP BY category"
        )
        cat_rows = await cursor.fetchall()
        live_counts = {str(row["category"]): int(row["cnt"]) for row in cat_rows}

        removed: list[str] = []
        folder_cleaned: list[str] = []

        for cat in self.category_manager.list_categories():
            if cat in keep:
                continue
            db_count = live_counts.get(cat, 0)
            folder = self.media_root / cat
            folder_missing = not folder.exists()
            folder_empty = folder_missing or (
                folder.is_dir() and not any(folder.iterdir())
            )
            if db_count > 0 or not folder_empty:
                continue
            if folder.exists():
                try:
                    folder.rmdir()
                    folder_cleaned.append(cat)
                except Exception as exc:
                    logger.warning("清理空分类目录失败 %s: %s", cat, exc)
                    continue
            if self.category_manager.delete_category(cat):
                removed.append(cat)

        return {
            "removed": removed,
            "removed_count": len(removed),
            "folder_cleaned": folder_cleaned,
        }

    async def get_stats(self) -> dict[str, Any]:
        conn = await self._ensure_conn()
        cursor_total = await conn.execute(
            "SELECT COUNT(*) AS total_count, COALESCE(SUM(size), 0) AS total_size FROM media"
        )
        total_row = await cursor_total.fetchone()
        total_count = int(total_row["total_count"]) if total_row else 0
        total_size = int(total_row["total_size"]) if total_row else 0

        cursor_kind = await conn.execute(
            "SELECT kind, COUNT(*) AS count FROM media GROUP BY kind"
        )
        kind_rows = await cursor_kind.fetchall()
        by_kind = {str(row["kind"]): int(row["count"]) for row in kind_rows}

        cursor_cat = await conn.execute(
            "SELECT category, COUNT(*) AS count, COALESCE(SUM(size), 0) AS size FROM media GROUP BY category"
        )
        cat_rows = await cursor_cat.fetchall()
        cat_counts = {
            str(row["category"]): {"count": int(row["count"]), "size": int(row["size"])}
            for row in cat_rows
        }
        categories = self.category_manager.export_with_counts(cat_counts)
        return {
            "total_count": total_count,
            "total_size": total_size,
            "total_size_human": format_size(total_size),
            "by_kind": by_kind,
            "categories": categories,
        }
