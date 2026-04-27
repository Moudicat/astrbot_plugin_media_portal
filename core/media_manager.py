"""媒体索引与文件管理。"""

from __future__ import annotations

import asyncio
import json
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

import aiosqlite

from astrbot.api import logger

from .category_manager import CategoryManager
from .derivatives import DerivativesManager
from .downloader import MediaDownloader
from .utils import (
    detect_mime_and_kind,
    ensure_dir,
    file_sha256,
    format_size,
    is_kind_allowed,
    now_ts,
    probe_audio_duration,
    probe_video_duration_via_ffprobe,
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
    duration: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["size_human"] = format_size(self.size)
        return payload


@dataclass(slots=True)
class TrashRecord:
    id: int
    original_media_id: int
    category: str
    filename: str
    original_rel_path: str
    trash_rel_path: str
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
    deleted_at: float
    duration: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["size_human"] = format_size(self.size)
        return payload


class DuplicateMediaError(ValueError):
    def __init__(self, record: MediaRecord):
        super().__init__("检测到 SHA256 重复文件。")
        self.record = record


class MediaManager:
    DEFAULT_TRASH_RETENTION_DAYS = 30

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
        self.trash_root = ensure_dir(self.plugin_data_dir / "trash")
        self._conn: aiosqlite.Connection | None = None
        self._db_lock = asyncio.Lock()
        # 串行化所有会同时修改磁盘与索引的写操作，避免事务与文件变更交叉。
        self._write_lock = asyncio.Lock()
        self.derivatives = DerivativesManager(
            media_root=self.media_root,
            plugin_data_dir=self.plugin_data_dir,
        )
        # FTS5 能力探测结果；``_fts_enabled=False`` 时搜索会回退到 LIKE。
        self._fts_enabled: bool = False
        self._fts_tokenizer: str = ""
        # 后台衍生任务（预生成缩略图 / 波形等），跟踪起来方便 close() 时统一清理。
        self._derivative_tasks: set[asyncio.Task] = set()
        # 媒体落地后通知钩子：(record, kind: 'created'|'updated'|'restored') -> awaitable | None。
        # 主要给 IntelligenceManager 用：上传成功后异步触发 CLIP / Face 增量索引。
        self._post_save_callbacks: list[
            Callable[[MediaRecord, str], Awaitable[None] | None]
        ] = []

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
                    updated_at REAL NOT NULL,
                    duration REAL NOT NULL DEFAULT 0
                )
                """
            )
            await self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS media_trash (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_media_id INTEGER NOT NULL DEFAULT 0,
                    category TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    original_rel_path TEXT NOT NULL,
                    trash_rel_path TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    mime TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    source_url TEXT DEFAULT '',
                    sender_id TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    deleted_at REAL NOT NULL,
                    duration REAL NOT NULL DEFAULT 0
                )
                """
            )
            await self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS media_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            await self._conn.execute(
                """
                INSERT OR IGNORE INTO media_settings(key, value, updated_at)
                VALUES (?, ?, ?)
                """,
                (
                    "trash_retention_days",
                    str(self.DEFAULT_TRASH_RETENTION_DAYS),
                    now_ts(),
                ),
            )
            # 老库升级：duration 列不存在时补齐；SQLite 没有 IF NOT EXISTS，
            # 靠捕获 "duplicate column name" 识别已经迁移过。
            try:
                await self._conn.execute(
                    "ALTER TABLE media ADD COLUMN duration REAL NOT NULL DEFAULT 0"
                )
            except Exception as exc:
                if "duplicate column" not in str(exc).lower():
                    logger.debug("ALTER TABLE add duration skipped: %s", exc)
            await self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_category_created ON media(category, created_at DESC)"
            )
            await self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_sha256 ON media(sha256)"
            )
            await self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_kind ON media(kind)"
            )
            await self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_trash_deleted_at ON media_trash(deleted_at)"
            )
            await self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_trash_sha256 ON media_trash(sha256)"
            )
            await self._conn.commit()
            await self._setup_fts5(self._conn)

    async def close(self) -> None:
        pending = [task for task in self._derivative_tasks if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            try:
                await asyncio.gather(*pending, return_exceptions=True)
            except Exception:
                pass
        self._derivative_tasks.clear()
        async with self._db_lock:
            if self._conn:
                await self._conn.close()
            self._conn = None
        self._fts_enabled = False
        self._fts_tokenizer = ""

    # ------------------ FTS5 ------------------

    async def _probe_fts5_tokenizer(self, conn: aiosqlite.Connection) -> str:
        """探测 FTS5 可用性与可用的分词器。

        - 优先 ``trigram``（SQLite 3.34+，对 CJK 子串匹配更友好）；
        - 回退到 ``unicode61``；
        - 再不行返回空串，表示 FTS5 完全不可用。
        """
        for tokenizer in ("trigram", "unicode61"):
            try:
                await conn.execute(
                    f"CREATE VIRTUAL TABLE __fts_probe USING fts5(x, tokenize='{tokenizer}')"
                )
                await conn.execute("DROP TABLE __fts_probe")
                return tokenizer
            except Exception:
                try:
                    await conn.execute("DROP TABLE IF EXISTS __fts_probe")
                except Exception:
                    pass
                continue
        return ""

    async def _fts_table_exists(self, conn: aiosqlite.Connection) -> bool:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='media_fts'"
        )
        row = await cursor.fetchone()
        return bool(row)

    async def _setup_fts5(self, conn: aiosqlite.Connection) -> None:
        tokenizer = await self._probe_fts5_tokenizer(conn)
        if not tokenizer:
            logger.info("SQLite FTS5 不可用，媒体搜索将回退到 LIKE 模式。")
            self._fts_enabled = False
            self._fts_tokenizer = ""
            return
        try:
            if not await self._fts_table_exists(conn):
                await conn.execute(
                    f"""
                    CREATE VIRTUAL TABLE media_fts USING fts5(
                        filename, description, tags, category,
                        content='media',
                        content_rowid='id',
                        tokenize='{tokenizer}'
                    )
                    """
                )
                await conn.execute(
                    """
                    INSERT INTO media_fts(rowid, filename, description, tags, category)
                    SELECT id, filename, description, tags, category FROM media
                    """
                )
            await conn.executescript(
                """
                CREATE TRIGGER IF NOT EXISTS media_ai_fts AFTER INSERT ON media BEGIN
                    INSERT INTO media_fts(rowid, filename, description, tags, category)
                    VALUES (new.id, new.filename, new.description, new.tags, new.category);
                END;
                CREATE TRIGGER IF NOT EXISTS media_ad_fts AFTER DELETE ON media BEGIN
                    INSERT INTO media_fts(media_fts, rowid, filename, description, tags, category)
                    VALUES ('delete', old.id, old.filename, old.description, old.tags, old.category);
                END;
                CREATE TRIGGER IF NOT EXISTS media_au_fts AFTER UPDATE ON media BEGIN
                    INSERT INTO media_fts(media_fts, rowid, filename, description, tags, category)
                    VALUES ('delete', old.id, old.filename, old.description, old.tags, old.category);
                    INSERT INTO media_fts(rowid, filename, description, tags, category)
                    VALUES (new.id, new.filename, new.description, new.tags, new.category);
                END;
                """
            )
            await conn.commit()
        except Exception as exc:
            logger.warning("FTS5 初始化失败，回退到 LIKE: %s", exc)
            self._fts_enabled = False
            self._fts_tokenizer = ""
            return
        self._fts_enabled = True
        self._fts_tokenizer = tokenizer

    # ------------------ 衍生资源（缩略图/海报/波形） ------------------

    def _schedule_derivatives(self, record: MediaRecord) -> None:
        """把单条记录的衍生资源生成派发到后台；异常不回传。"""
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is None:
            # 没有事件循环可用（极少见），同步退化执行，保证最少生成一次。
            try:
                self.derivatives.generate_all_sync(record.rel_path, record.kind)
            except Exception as exc:
                logger.debug("同步生成衍生资源失败 %s: %s", record.rel_path, exc)
            self._dispatch_post_save_sync(record, "created")
            return
        task = running.create_task(
            self.derivatives.generate_all(record.rel_path, record.kind)
        )
        self._derivative_tasks.add(task)

        def _on_done(done_task: asyncio.Task) -> None:
            self._derivative_tasks.discard(done_task)
            try:
                done_task.result()
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.debug("衍生资源后台任务失败: %s", exc)

        task.add_done_callback(_on_done)
        self._dispatch_post_save_async(record, "created")

    def register_post_save_callback(
        self,
        callback: Callable[[MediaRecord, str], Awaitable[None] | None],
    ) -> None:
        """注册媒体落地后的回调；同一回调多次注册只保留一份。"""
        if callback not in self._post_save_callbacks:
            self._post_save_callbacks.append(callback)

    def _dispatch_post_save_sync(self, record: MediaRecord, action: str) -> None:
        for cb in tuple(self._post_save_callbacks):
            try:
                ret = cb(record, action)
                if asyncio.iscoroutine(ret):
                    ret.close()
            except Exception as exc:
                logger.debug("post_save 同步回调异常: %s", exc)

    def _dispatch_post_save_async(self, record: MediaRecord, action: str) -> None:
        if not self._post_save_callbacks:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._dispatch_post_save_sync(record, action)
            return
        for cb in tuple(self._post_save_callbacks):
            try:
                ret = cb(record, action)
            except Exception as exc:
                logger.debug("post_save 同步回调异常: %s", exc)
                continue
            if asyncio.iscoroutine(ret):
                cb_task = loop.create_task(ret)
                self._derivative_tasks.add(cb_task)
                cb_task.add_done_callback(self._derivative_tasks.discard)

    async def rebuild_fts_index(self) -> bool:
        """强制重建 FTS 索引内容（当手动外部写入数据库或怀疑索引漂移时使用）。"""
        if not self._fts_enabled:
            return False
        conn = await self._ensure_conn()
        async with self._write_lock:
            try:
                await conn.execute(
                    "INSERT INTO media_fts(media_fts) VALUES ('rebuild')"
                )
                await conn.commit()
                return True
            except Exception as exc:
                logger.warning("重建 FTS5 索引失败: %s", exc)
                return False

    def _fts_build_match(self, query: str) -> str | None:
        """把用户输入转成 FTS5 MATCH 表达式；不可用时返回 ``None``。

        - trigram 分词下，子串 >= 3 字符才能命中，短于 3 字符交给 LIKE 兜底。
        - unicode61 按空白拆 token，每个 token 追加 ``*`` 做前缀匹配；纯中文字符串
          经 unicode61 会被视为单个连续 token，此时我们也降级 LIKE，保证搜得到。
        """
        text = str(query or "").strip()
        if not text:
            return None
        if self._fts_tokenizer == "trigram":
            # 去除多余空白，统一做一次整体短语匹配；多 token 时依然拼成 AND。
            tokens = [tok for tok in text.split() if tok]
            if not tokens:
                return None
            if any(len(tok) < 3 for tok in tokens):
                return None
            return " ".join('"' + tok.replace('"', '""') + '"' for tok in tokens)
        if self._fts_tokenizer == "unicode61":
            tokens = [tok for tok in text.split() if tok]
            if not tokens:
                return None
            # 只允许 ASCII token 走 FTS，中文 / 其它表意文字回退到 LIKE，
            # 避免 unicode61 把整段中文当成单个 token 导致无法命中。
            if any(not tok.isascii() for tok in tokens):
                return None
            parts: list[str] = []
            for tok in tokens:
                safe = tok.replace('"', '""')
                parts.append('"' + safe + '"' + ("*" if len(tok) > 1 else ""))
            return " ".join(parts)
        return None

    async def _ensure_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            await self.initialize()
        if self._conn is None:  # pragma: no cover - 防御 initialize 异常静默失败
            raise RuntimeError("媒体索引数据库尚未初始化。")
        return self._conn

    @staticmethod
    def _escape_like(text: str) -> str:
        """转义 LIKE 中的特殊字符，配合 ``ESCAPE '\\\\'`` 使用。

        避免用户输入的 ``%`` / ``_`` 被当作通配符，或反斜杠误解释。
        """
        return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

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

    @staticmethod
    def _row_get(row: aiosqlite.Row, key: str, default: Any = None) -> Any:
        """aiosqlite.Row 对于不存在的列会抛 IndexError，这里做一次容错。

        主要是为了兼容"索引版本升级前已加载的 Row"这种极少见边界。
        """
        try:
            return row[key]
        except (IndexError, KeyError):
            return default

    def _row_to_record(self, row: aiosqlite.Row) -> MediaRecord:
        tags = self._parse_tags(row["tags"])
        abs_path = str((self.media_root / row["rel_path"]).resolve())
        duration_raw = self._row_get(row, "duration", 0)
        try:
            duration_value = float(duration_raw) if duration_raw is not None else 0.0
        except (TypeError, ValueError):
            duration_value = 0.0
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
            duration=duration_value,
        )

    def _trash_row_to_record(self, row: aiosqlite.Row) -> TrashRecord:
        tags = self._parse_tags(row["tags"])
        trash_rel_path = str(row["trash_rel_path"] or "")
        abs_path = (
            str((self.trash_root / trash_rel_path).resolve())
            if trash_rel_path
            else ""
        )
        duration_raw = self._row_get(row, "duration", 0)
        try:
            duration_value = float(duration_raw) if duration_raw is not None else 0.0
        except (TypeError, ValueError):
            duration_value = 0.0
        return TrashRecord(
            id=int(row["id"]),
            original_media_id=int(row["original_media_id"] or 0),
            category=str(row["category"]),
            filename=str(row["filename"]),
            original_rel_path=str(row["original_rel_path"]),
            trash_rel_path=trash_rel_path,
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
            deleted_at=float(row["deleted_at"]),
            duration=duration_value,
        )

    async def get_trash_retention_days(self) -> int:
        conn = await self._ensure_conn()
        cursor = await conn.execute(
            "SELECT value FROM media_settings WHERE key = 'trash_retention_days'"
        )
        row = await cursor.fetchone()
        value = self.DEFAULT_TRASH_RETENTION_DAYS
        if row:
            try:
                value = int(str(row["value"]).strip() or self.DEFAULT_TRASH_RETENTION_DAYS)
            except (TypeError, ValueError):
                value = self.DEFAULT_TRASH_RETENTION_DAYS
        return max(1, min(3650, value))

    async def set_trash_retention_days(self, days: int) -> int:
        normalized = max(1, min(3650, int(days)))
        conn = await self._ensure_conn()
        async with self._write_lock:
            await conn.execute(
                """
                INSERT INTO media_settings(key, value, updated_at)
                VALUES('trash_retention_days', ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (str(normalized), now_ts()),
            )
            await conn.commit()
        return normalized

    def _next_trash_path(self, record: MediaRecord) -> Path:
        day_bucket = time.strftime("%Y%m%d")
        safe_name = sanitize_filename(record.filename, fallback=f"media_{record.id}")
        parent = ensure_dir(self.trash_root / day_bucket)
        return unique_path(parent / f"{record.id}_{safe_name}")

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
        duration: float = 0.0,
        conn: aiosqlite.Connection | None = None,
        commit: bool = True,
    ) -> MediaRecord:
        if conn is None:
            conn = await self._ensure_conn()
        created_at = now_ts()
        tags_json = json.dumps(tags or [], ensure_ascii=False)
        try:
            duration_value = float(duration or 0.0)
        except (TypeError, ValueError):
            duration_value = 0.0
        if duration_value < 0:
            duration_value = 0.0
        cursor = await conn.execute(
            """
            INSERT INTO media (
                category, filename, rel_path, kind, mime, size, sha256,
                source_url, sender_id, description, tags, created_at, updated_at, duration
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                duration_value,
            ),
        )
        if commit:
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
            duration=duration_value,
        )

    async def _insert_trash_record(
        self,
        record: MediaRecord,
        *,
        trash_rel_path: str,
        conn: aiosqlite.Connection | None = None,
        commit: bool = True,
    ) -> TrashRecord:
        if conn is None:
            conn = await self._ensure_conn()
        tags_json = json.dumps(record.tags or [], ensure_ascii=False)
        deleted_at = now_ts()
        cursor = await conn.execute(
            """
            INSERT INTO media_trash (
                original_media_id, category, filename, original_rel_path, trash_rel_path,
                kind, mime, size, sha256, source_url, sender_id, description,
                tags, created_at, updated_at, deleted_at, duration
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(record.id),
                record.category,
                record.filename,
                record.rel_path,
                trash_rel_path,
                record.kind,
                record.mime,
                int(record.size),
                record.sha256,
                record.source_url,
                record.sender_id,
                record.description,
                tags_json,
                float(record.created_at),
                float(record.updated_at),
                deleted_at,
                float(record.duration or 0.0),
            ),
        )
        if commit:
            await conn.commit()
        trash_id = int(cursor.lastrowid)
        return TrashRecord(
            id=trash_id,
            original_media_id=int(record.id),
            category=record.category,
            filename=record.filename,
            original_rel_path=record.rel_path,
            trash_rel_path=trash_rel_path,
            abs_path=str((self.trash_root / trash_rel_path).resolve()) if trash_rel_path else "",
            kind=record.kind,
            mime=record.mime,
            size=record.size,
            sha256=record.sha256,
            source_url=record.source_url,
            sender_id=record.sender_id,
            description=record.description,
            tags=record.tags or [],
            created_at=record.created_at,
            updated_at=record.updated_at,
            deleted_at=deleted_at,
            duration=record.duration,
        )

    async def get_by_id(self, media_id: int) -> MediaRecord | None:
        conn = await self._ensure_conn()
        cursor = await conn.execute("SELECT * FROM media WHERE id = ?", (int(media_id),))
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_record(row)

    async def list_image_records_minimal(self) -> list[tuple[int, str, str]]:
        """供智能能力（CLIP / 人脸）拉取所有图片记录的极简视图。

        返回 ``[(media_id, sha256, abs_path)]``，避免一次性反序列化完整 ``MediaRecord``。
        """
        conn = await self._ensure_conn()
        cursor = await conn.execute(
            "SELECT id, sha256, rel_path FROM media WHERE kind = 'image'"
        )
        rows = await cursor.fetchall()
        return [
            (
                int(row["id"]),
                str(row["sha256"] or ""),
                str((self.media_root / row["rel_path"]).resolve()),
            )
            for row in rows
        ]

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

    def _build_query_where(
        self, query: str
    ) -> tuple[list[str], list[Any], bool]:
        """把搜索关键词转成 WHERE 子句片段。

        返回 ``(conditions, params, use_fts)``：
        - ``use_fts=True`` 代表走 FTS5 的 MATCH（需要与 media_fts 表 JOIN）；
        - 否则退回到 LIKE 四列模糊匹配。
        """
        text = query.strip()
        if not text:
            return [], [], False
        fts_match: str | None = None
        if self._fts_enabled:
            fts_match = self._fts_build_match(text)
        if fts_match is not None:
            return (["media_fts MATCH ?"], [fts_match], True)
        wildcard = f"%{self._escape_like(text)}%"
        cond = (
            "(media.filename LIKE ? ESCAPE '\\' OR media.description LIKE ? ESCAPE '\\' "
            "OR media.tags LIKE ? ESCAPE '\\' OR media.category LIKE ? ESCAPE '\\')"
        )
        return [cond], [wildcard] * 4, False

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
            where_parts.append("media.category = ?")
            params.append(slugify_category(category))
        if kind:
            where_parts.append("media.kind = ?")
            params.append(kind.lower())

        query_conditions, query_params, use_fts = self._build_query_where(query)
        where_parts.extend(query_conditions)
        params.extend(query_params)

        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        if use_fts:
            from_sql = "FROM media JOIN media_fts ON media.id = media_fts.rowid"
            order_sql = "ORDER BY media_fts.rank, media.created_at DESC"
        else:
            from_sql = "FROM media"
            order_sql = "ORDER BY media.created_at DESC"

        cursor_total = await conn.execute(
            f"SELECT COUNT(*) AS total {from_sql} {where_sql}",
            tuple(params),
        )
        total_row = await cursor_total.fetchone()
        total = int(total_row["total"]) if total_row else 0

        cursor = await conn.execute(
            f"""
            SELECT media.* {from_sql}
            {where_sql}
            {order_sql}
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

        where_parts: list[str] = []
        params: list[Any] = []
        query_conditions, query_params, use_fts = self._build_query_where(q)
        where_parts.extend(query_conditions)
        params.extend(query_params)
        if category:
            where_parts.append("media.category = ?")
            params.append(slugify_category(category))
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        if use_fts:
            from_sql = "FROM media JOIN media_fts ON media.id = media_fts.rowid"
            order_sql = "ORDER BY media_fts.rank, media.created_at DESC"
        else:
            from_sql = "FROM media"
            order_sql = "ORDER BY media.created_at DESC"

        cursor = await conn.execute(
            f"""
            SELECT media.* {from_sql}
            {where_sql}
            {order_sql}
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

    @staticmethod
    async def _begin_write_transaction(conn: aiosqlite.Connection) -> None:
        await conn.execute("BEGIN IMMEDIATE")

    @staticmethod
    def _probe_duration_for_kind(path: Path, kind: str) -> float:
        """读取音频/视频时长。

        - audio / video 先走 mutagen（覆盖 mp3、flac、ogg、m4a、mp4/m4v/mov 等）
        - video 读不到时再尝试 ``ffprobe`` 兜底（覆盖 mkv/webm/avi/flv 等），
          ``ffprobe`` 未安装则静默跳过
        - 任一失败统一返回 ``0.0``，不影响主流程
        """
        if kind not in {"audio", "video"}:
            return 0.0
        value: float | None = None
        try:
            value = probe_audio_duration(path)
        except Exception:
            value = None
        if (value is None or value <= 0) and kind == "video":
            try:
                value = probe_video_duration_via_ffprobe(path)
            except Exception:
                value = None
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _cleanup_temp_path(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass

    @staticmethod
    def _rollback_saved_target(target: Path, source: Path, *, should_move: bool) -> None:
        if not target.exists():
            return
        if should_move:
            if source.exists():
                logger.warning(
                    "回滚媒体文件失败：源路径已存在，保留目标文件 %s -> %s",
                    target,
                    source,
                )
                return
            shutil.move(str(target), str(source))
            return
        target.unlink(missing_ok=True)

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
        duplicate_policy: str = "reuse",
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
        should_move = self.default_move_local if move is None else bool(move)
        policy = str(duplicate_policy or "reuse").strip().lower()
        if policy not in {"reuse", "force", "error"}:
            policy = "reuse"

        async with self._write_lock:
            if policy != "force":
                duplicated = await self._get_by_sha256(source_hash)
                if duplicated:
                    if policy == "error":
                        raise DuplicateMediaError(duplicated)
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
            committed = False
            try:
                if should_move:
                    shutil.move(str(source), str(temp_target))
                else:
                    shutil.copy2(source, temp_target)
                temp_target.replace(target)

                rel_path = relative_posix(target, self.media_root)
                duration_value = self._probe_duration_for_kind(target, kind)
                conn = await self._ensure_conn()
                await self._begin_write_transaction(conn)
                try:
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
                        duration=duration_value,
                        conn=conn,
                        commit=False,
                    )
                    await conn.commit()
                    committed = True
                except Exception:
                    await conn.rollback()
                    raise
            except Exception:
                self._cleanup_temp_path(temp_target)
                if not committed:
                    try:
                        self._rollback_saved_target(
                            target, source, should_move=should_move
                        )
                    except Exception as rollback_exc:
                        logger.warning("回滚媒体文件失败: %s", rollback_exc)
                raise

        # 写入成功后再派发衍生任务（解锁 _write_lock 才触发，避免阻塞后续写）
        self._schedule_derivatives(saved)
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
        duplicate_policy: str = "reuse",
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
                duplicate_policy=duplicate_policy,
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
        filename: str | None = None,
    ) -> MediaRecord:
        record = await self.get_by_id(media_id)
        if not record:
            raise ValueError("媒体不存在。")

        if category and slugify_category(category) != record.category:
            record = await self.move_media(media_id, category)

        # 改名：在持有写锁的事务内把磁盘文件重命名，并同步 filename/rel_path。
        # 放到 category 处理之后，才能在"新分类目录"里重命名。
        if filename is not None:
            await self._rename_media_file(media_id, filename)

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
            async with self._write_lock:
                fields.append("updated_at = ?")
                params.append(now_ts())
                params.append(int(media_id))
                await conn.execute(
                    f"UPDATE media SET {', '.join(fields)} WHERE id = ?",
                    tuple(params),
                )
                await conn.commit()
        refreshed = await self.get_by_id(media_id)
        if refreshed is None:
            raise RuntimeError("更新后的记录意外丢失。")
        return refreshed

    async def _rename_media_file(self, media_id: int, new_filename: str) -> None:
        """在同一分类目录内重命名媒体文件，同步更新 ``filename`` / ``rel_path``。

        约定："不传 filename" 已经在上层通过 ``filename is None`` 过滤，所以这里
        只会在调用方确实想改名时才被触发。若 ``new_filename`` 为空串或全为空白，
        视为"没有给出有效新名字"，直接跳过（不做任何修改，也不抛错）；只有
        清洗后变成空值的非法字符组合（例如 "..."），才会抛错提醒。
        """
        raw_text = str(new_filename or "")
        if not raw_text.strip():
            return
        cleaned = sanitize_filename(raw_text, fallback="")
        if not cleaned:
            raise ValueError("filename 无效：清洗后为空，请使用常规字符。")

        async with self._write_lock:
            current = await self.get_by_id(media_id)
            if current is None:
                raise ValueError("媒体不存在。")

            # 原文件名可能带后缀，新名没带时沿用旧后缀。
            origin_suffix = Path(current.filename).suffix
            if not Path(cleaned).suffix and origin_suffix:
                cleaned = f"{cleaned}{origin_suffix}"

            if cleaned == current.filename:
                return

            source = Path(current.abs_path)
            if not source.exists():
                raise FileNotFoundError("媒体文件已不存在。")

            target_dir = source.parent
            target_path = unique_path(target_dir / cleaned)
            previous_rel = current.rel_path

            conn = await self._ensure_conn()
            try:
                shutil.move(str(source), str(target_path))
                new_rel = relative_posix(target_path, self.media_root)
                await self._begin_write_transaction(conn)
                try:
                    await conn.execute(
                        """
                        UPDATE media
                        SET filename = ?, rel_path = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (target_path.name, new_rel, now_ts(), int(media_id)),
                    )
                    await conn.commit()
                except Exception:
                    await conn.rollback()
                    raise
            except Exception:
                try:
                    if target_path.exists() and not source.exists():
                        shutil.move(str(target_path), str(source))
                except Exception as rollback_exc:
                    logger.warning("回滚媒体改名失败: %s", rollback_exc)
                raise

        try:
            self.derivatives.purge_for(previous_rel)
        except Exception as exc:
            logger.debug("清理改名前衍生资源失败 %s: %s", previous_rel, exc)
        refreshed_after_rename = await self.get_by_id(media_id)
        if refreshed_after_rename is not None:
            self._schedule_derivatives(refreshed_after_rename)

    async def delete_media(self, media_id: int) -> bool:
        async with self._write_lock:
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
            purge_rel = record.rel_path
        try:
            self.derivatives.purge_for(purge_rel)
        except Exception as exc:
            logger.debug("清理衍生资源失败 %s: %s", purge_rel, exc)
        return True

    async def _get_trash_by_id(self, trash_id: int) -> TrashRecord | None:
        conn = await self._ensure_conn()
        cursor = await conn.execute(
            "SELECT * FROM media_trash WHERE id = ?",
            (int(trash_id),),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return self._trash_row_to_record(row)

    async def trash_media(self, media_id: int) -> TrashRecord | None:
        async with self._write_lock:
            record = await self.get_by_id(media_id)
            if not record:
                return None
            source = Path(record.abs_path)
            moved = False
            target = self._next_trash_path(record)
            trash_rel_path = ""
            if source.exists() and source.is_file():
                ensure_dir(target.parent)
                shutil.move(str(source), str(target))
                trash_rel_path = relative_posix(target, self.trash_root)
                moved = True

            conn = await self._ensure_conn()
            await self._begin_write_transaction(conn)
            try:
                trashed = await self._insert_trash_record(
                    record,
                    trash_rel_path=trash_rel_path,
                    conn=conn,
                    commit=False,
                )
                await conn.execute("DELETE FROM media WHERE id = ?", (int(media_id),))
                await conn.commit()
            except Exception:
                await conn.rollback()
                if moved and target.exists() and not source.exists():
                    try:
                        ensure_dir(source.parent)
                        shutil.move(str(target), str(source))
                    except Exception as rollback_exc:
                        logger.warning("回滚回收站移动失败: %s", rollback_exc)
                raise
            purge_rel = record.rel_path
        try:
            self.derivatives.purge_for(purge_rel)
        except Exception as exc:
            logger.debug("清理回收前衍生资源失败 %s: %s", purge_rel, exc)
        return trashed

    async def list_trash(
        self,
        *,
        category: str = "",
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
        q = query.strip()
        if q:
            wildcard = f"%{self._escape_like(q)}%"
            where_parts.append(
                "(filename LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\' OR sha256 LIKE ? ESCAPE '\\')"
            )
            params.extend([wildcard, wildcard, wildcard])
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        cursor_total = await conn.execute(
            f"SELECT COUNT(*) AS total FROM media_trash {where_sql}",
            tuple(params),
        )
        row_total = await cursor_total.fetchone()
        total = int(row_total["total"]) if row_total else 0
        cursor = await conn.execute(
            f"""
            SELECT * FROM media_trash
            {where_sql}
            ORDER BY deleted_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params + [page_size, offset]),
        )
        rows = await cursor.fetchall()
        items = [self._trash_row_to_record(row).to_dict() for row in rows]
        total_pages = (total + page_size - 1) // page_size if total else 0
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    async def restore_from_trash(
        self,
        trash_id: int,
        *,
        category: str = "",
        filename: str = "",
    ) -> MediaRecord:
        async with self._write_lock:
            trashed = await self._get_trash_by_id(trash_id)
            if not trashed:
                raise ValueError("回收站记录不存在。")
            if not trashed.trash_rel_path:
                raise FileNotFoundError("回收站源文件路径缺失，无法恢复。")
            source = (self.trash_root / trashed.trash_rel_path).resolve()
            if not source.exists() or not source.is_file():
                raise FileNotFoundError("回收站文件已不存在。")
            normalized_category, target = await self._build_target_path(
                category or trashed.category,
                filename_hint=filename or trashed.filename,
                source_path=source,
            )
            conn = await self._ensure_conn()
            moved = False
            try:
                shutil.move(str(source), str(target))
                moved = True
                rel_path = relative_posix(target, self.media_root)
                await self._begin_write_transaction(conn)
                try:
                    restored = await self._insert_record(
                        category=normalized_category,
                        filename=target.name,
                        rel_path=rel_path,
                        kind=trashed.kind,
                        mime=trashed.mime,
                        size=target.stat().st_size,
                        sha256=trashed.sha256,
                        source_url=trashed.source_url,
                        sender_id=trashed.sender_id,
                        description=trashed.description,
                        tags=trashed.tags,
                        duration=trashed.duration,
                        conn=conn,
                        commit=False,
                    )
                    await conn.execute(
                        "DELETE FROM media_trash WHERE id = ?",
                        (int(trash_id),),
                    )
                    await conn.commit()
                except Exception:
                    await conn.rollback()
                    raise
            except Exception:
                if moved and target.exists() and not source.exists():
                    try:
                        ensure_dir(source.parent)
                        shutil.move(str(target), str(source))
                    except Exception as rollback_exc:
                        logger.warning("回滚回收站恢复失败: %s", rollback_exc)
                raise
        self._schedule_derivatives(restored)
        return restored

    async def purge_trash(self, trash_id: int) -> bool:
        async with self._write_lock:
            trashed = await self._get_trash_by_id(trash_id)
            if not trashed:
                return False
            if trashed.trash_rel_path:
                target = (self.trash_root / trashed.trash_rel_path).resolve()
                if target.exists() and target.is_file():
                    try:
                        target.unlink(missing_ok=True)
                    except Exception as exc:
                        logger.warning("删除回收站文件失败: %s", exc)
            conn = await self._ensure_conn()
            await conn.execute("DELETE FROM media_trash WHERE id = ?", (int(trash_id),))
            await conn.commit()
        return True

    async def purge_expired_trash(self, *, retention_days: int | None = None) -> dict[str, int]:
        days = (
            await self.get_trash_retention_days()
            if retention_days is None
            else max(1, min(3650, int(retention_days)))
        )
        cutoff = now_ts() - float(days) * 86400.0
        async with self._write_lock:
            conn = await self._ensure_conn()
            cursor = await conn.execute(
                "SELECT id, trash_rel_path FROM media_trash WHERE deleted_at <= ?",
                (cutoff,),
            )
            rows = await cursor.fetchall()
            purged = 0
            for row in rows:
                trash_rel = str(row["trash_rel_path"] or "")
                if trash_rel:
                    target = (self.trash_root / trash_rel).resolve()
                    if target.exists() and target.is_file():
                        try:
                            target.unlink(missing_ok=True)
                        except Exception:
                            pass
                await conn.execute(
                    "DELETE FROM media_trash WHERE id = ?",
                    (int(row["id"]),),
                )
                purged += 1
            if purged:
                await conn.commit()
        return {"purged": purged}

    async def get_trash_stats(self) -> dict[str, Any]:
        conn = await self._ensure_conn()
        retention_days = await self.get_trash_retention_days()
        cutoff = now_ts() - float(retention_days) * 86400.0
        cursor_total = await conn.execute(
            "SELECT COUNT(*) AS total_count, COALESCE(SUM(size), 0) AS total_size FROM media_trash"
        )
        total_row = await cursor_total.fetchone()
        total_count = int(total_row["total_count"]) if total_row else 0
        total_size = int(total_row["total_size"]) if total_row else 0
        cursor_expired = await conn.execute(
            "SELECT COUNT(*) AS cnt FROM media_trash WHERE deleted_at <= ?",
            (cutoff,),
        )
        expired_row = await cursor_expired.fetchone()
        expired_count = int(expired_row["cnt"]) if expired_row else 0
        return {
            "total_count": total_count,
            "total_size": total_size,
            "total_size_human": format_size(total_size),
            "expired_count": expired_count,
            "retention_days": retention_days,
        }

    async def move_media(self, media_id: int, new_category: str) -> MediaRecord:
        async with self._write_lock:
            record = await self.get_by_id(media_id)
            if not record:
                raise ValueError("媒体不存在。")
            previous_rel = record.rel_path
            source = Path(record.abs_path)
            if not source.exists():
                raise FileNotFoundError("媒体文件已不存在。")

            normalized_category = self.category_manager.ensure_category(new_category)
            target_dir = ensure_dir(self.media_root / normalized_category)
            target_path = unique_path(target_dir / source.name)
            conn = await self._ensure_conn()

            try:
                shutil.move(str(source), str(target_path))
                new_rel_path = relative_posix(target_path, self.media_root)
                await self._begin_write_transaction(conn)
                try:
                    await conn.execute(
                        """
                        UPDATE media
                        SET category = ?, filename = ?, rel_path = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            normalized_category,
                            target_path.name,
                            new_rel_path,
                            now_ts(),
                            int(media_id),
                        ),
                    )
                    await conn.commit()
                except Exception:
                    await conn.rollback()
                    raise
            except Exception:
                try:
                    if target_path.exists() and not source.exists():
                        shutil.move(str(target_path), str(source))
                except Exception as rollback_exc:
                    logger.warning("回滚媒体移动失败: %s", rollback_exc)
                raise

            refreshed = await self.get_by_id(media_id)
            if refreshed is None:
                raise RuntimeError("移动后的记录意外丢失。")

        # 旧位置的缩略图/海报/波形失效，清理后让新分类按需再生成
        try:
            self.derivatives.purge_for(previous_rel)
        except Exception as exc:
            logger.debug("清理旧分类衍生资源失败 %s: %s", previous_rel, exc)
        self._schedule_derivatives(refreshed)
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

        async with self._write_lock:
            old_dir = self.media_root / old_normalized
            new_dir = self.media_root / new_normalized
            if not old_dir.exists():
                return False, "原分类不存在。"
            if new_dir.exists():
                return False, "目标分类已存在。"

            metadata_renamed = False
            try:
                old_dir.rename(new_dir)
                renamed, _target = self.category_manager.rename_category(
                    old_normalized, new_normalized
                )
                if not renamed:
                    raise ValueError("分类元数据重命名失败。")
                metadata_renamed = True

                conn = await self._ensure_conn()
                await self._begin_write_transaction(conn)
                try:
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
                except Exception:
                    await conn.rollback()
                    raise
                try:
                    self.derivatives.purge_for_category(old_normalized)
                except Exception as exc:
                    logger.debug("清理旧分类衍生资源失败 %s: %s", old_normalized, exc)
                return True, new_normalized
            except ValueError as exc:
                try:
                    if new_dir.exists() and not old_dir.exists():
                        new_dir.rename(old_dir)
                except Exception as rollback_exc:
                    logger.warning("回滚分类目录失败: %s", rollback_exc)
                return False, str(exc)
            except Exception:
                if metadata_renamed:
                    reverted, _target = self.category_manager.rename_category(
                        new_normalized, old_normalized
                    )
                    if not reverted:
                        logger.warning(
                            "回滚分类元数据失败: %s -> %s",
                            new_normalized,
                            old_normalized,
                        )
                try:
                    if new_dir.exists() and not old_dir.exists():
                        new_dir.rename(old_dir)
                except Exception as rollback_exc:
                    logger.warning("回滚分类目录失败: %s", rollback_exc)
                raise

    async def delete_category(self, category: str, *, remove_files: bool = True) -> dict[str, Any]:
        normalized = slugify_category(category)
        conn = await self._ensure_conn()
        cursor = await conn.execute(
            "SELECT id FROM media WHERE category = ?",
            (normalized,),
        )
        rows = await cursor.fetchall()
        deleted_rows = 0
        deleted_files = 0

        if remove_files:
            for row in rows:
                trashed = await self.trash_media(int(row["id"]))
                if not trashed:
                    continue
                deleted_rows += 1
                if trashed.trash_rel_path:
                    deleted_files += 1
        else:
            async with self._write_lock:
                conn = await self._ensure_conn()
                cursor = await conn.execute(
                    "SELECT id FROM media WHERE category = ?",
                    (normalized,),
                )
                keep_rows = await cursor.fetchall()
                await conn.execute("DELETE FROM media WHERE category = ?", (normalized,))
                await conn.commit()
                deleted_rows = len(keep_rows)

        try:
            self.derivatives.purge_for_category(normalized)
        except Exception as exc:
            logger.debug("清理分类衍生资源失败 %s: %s", normalized, exc)

        category_dir = self.media_root / normalized
        if category_dir.exists():
            try:
                # 软删除后通常目录为空；若存在额外文件则保留，避免误删用户数据。
                category_dir.rmdir()
            except OSError:
                pass
            except Exception as exc:
                logger.warning("删除分类目录失败: %s", exc)
        self.category_manager.delete_category(normalized)
        return {
            "category": normalized,
            "deleted_files": deleted_files,
            "deleted_rows": deleted_rows,
        }

    async def ensure_scanned(self) -> dict[str, int]:
        """扫描媒体目录并修复索引，同步清理孤儿分类元数据。

        - 新发现的 audio/video 文件入库时顺带探测时长
        - 对 ``duration <= 0`` 的旧 audio/video 记录做一次性懒补录
        """
        async with self._write_lock:
            self.category_manager.sync_with_filesystem()
            conn = await self._ensure_conn()
            cursor = await conn.execute(
                "SELECT id, rel_path, kind, duration FROM media"
            )
            rows = await cursor.fetchall()
            db_rel_to_id: dict[str, int] = {}
            rows_need_duration: list[tuple[int, str, str]] = []
            for row in rows:
                rel_value = str(row["rel_path"])
                db_rel_to_id[rel_value] = int(row["id"])
                kind_value = str(row["kind"] or "").lower()
                if kind_value in {"audio", "video"}:
                    try:
                        dur_value = float(row["duration"] or 0)
                    except (TypeError, ValueError):
                        dur_value = 0.0
                    if dur_value <= 0:
                        rows_need_duration.append((int(row["id"]), rel_value, kind_value))

            fs_rel_paths: set[str] = set()
            indexed = 0
            skipped = 0
            duration_filled = 0
            scheduled_scan: list[MediaRecord] = []
            try:
                category_dirs = list(self.media_root.iterdir())
            except OSError as exc:
                logger.warning("扫描根目录失败: %s", exc)
                category_dirs = []
            for category_dir in category_dirs:
                try:
                    if not category_dir.is_dir():
                        continue
                except OSError:
                    continue
                category = slugify_category(category_dir.name)
                self.category_manager.ensure_category(category)
                try:
                    file_iter = list(category_dir.iterdir())
                except OSError as exc:
                    logger.warning("扫描分类目录失败 %s: %s", category_dir, exc)
                    continue
                for file_path in file_iter:
                    try:
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
                        duration_value = self._probe_duration_for_kind(file_path, kind)
                        scanned_record = await self._insert_record(
                            category=category,
                            filename=file_path.name,
                            rel_path=rel,
                            kind=kind,
                            mime=mime,
                            size=file_path.stat().st_size,
                            sha256=sha256,
                            description="",
                            tags=[],
                            duration=duration_value,
                        )
                        indexed += 1
                        if kind in {"image", "video", "audio"}:
                            scheduled_scan.append(scanned_record)
                    except OSError as exc:
                        logger.warning("扫描文件失败 %s: %s", file_path, exc)
                        skipped += 1

            # 懒补录旧记录的时长：文件仍在磁盘时才做；探测失败静默跳过。
            for media_id, rel, kind_value in rows_need_duration:
                if rel not in fs_rel_paths:
                    continue
                file_path = self.media_root / rel
                duration_value = self._probe_duration_for_kind(file_path, kind_value)
                if duration_value <= 0:
                    continue
                await conn.execute(
                    "UPDATE media SET duration = ? WHERE id = ?",
                    (duration_value, media_id),
                )
                duration_filled += 1
            if duration_filled:
                await conn.commit()

            stale = [rel for rel in db_rel_to_id.keys() if rel not in fs_rel_paths]
            removed = 0
            for rel in stale:
                await conn.execute("DELETE FROM media WHERE rel_path = ?", (rel,))
                removed += 1
            if removed:
                await conn.commit()
            pruned_categories = self.category_manager.prune_missing_folders()
            for rel in stale:
                try:
                    self.derivatives.purge_for(rel)
                except Exception:
                    pass
        # _write_lock 释放后再安排后台生成；避免长时间占用写锁
        for record in scheduled_scan:
            self._schedule_derivatives(record)
        return {
            "indexed": indexed,
            "removed": removed,
            "skipped": skipped,
            "pruned_categories": len(pruned_categories),
            "duration_filled": duration_filled,
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

    async def list_duplicate_groups(
        self,
        *,
        mode: str = "exact",
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        _ = mode
        conn = await self._ensure_conn()
        normalized_mode = "exact"
        page = max(1, int(page))
        page_size = max(1, min(100, int(page_size)))
        offset = (page - 1) * page_size

        groups: list[dict[str, Any]] = []
        total = 0

        cursor_total = await conn.execute(
            "SELECT COUNT(*) AS total FROM (SELECT sha256 FROM media GROUP BY sha256 HAVING COUNT(*) > 1)"
        )
        row_total = await cursor_total.fetchone()
        total = int(row_total["total"]) if row_total else 0

        cursor_groups = await conn.execute(
            """
            SELECT
                sha256,
                COUNT(*) AS cnt,
                MAX(created_at) AS latest
            FROM media
            GROUP BY sha256
            HAVING COUNT(*) > 1
            ORDER BY cnt DESC, latest DESC
            LIMIT ? OFFSET ?
            """,
            (page_size, offset),
        )
        group_rows = await cursor_groups.fetchall()
        for row in group_rows:
            sha = str(row["sha256"])
            cursor_items = await conn.execute(
                "SELECT * FROM media WHERE sha256 = ? ORDER BY created_at DESC, id DESC",
                (sha,),
            )
            item_rows = await cursor_items.fetchall()
            items = [self._row_to_record(item).to_dict() for item in item_rows]
            groups.append(
                {
                    "group_key": f"sha:{sha}",
                    "reason": "sha256",
                    "confidence": "exact",
                    "count": int(row["cnt"]),
                    "items": items,
                }
            )

        total_pages = (total + page_size - 1) // page_size if total else 0
        return {
            "items": groups,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "mode": normalized_mode,
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
