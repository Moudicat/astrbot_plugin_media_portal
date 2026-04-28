"""人脸 / 角色（person）SQLite 持久化。

设计要点：
- 与 CLIP 类似，使用独立的 ``intelligence/face_index.db``，便于「重建索引」时单独清空；
- ``face_records`` 存每个检测到的人脸；``face_persons`` 表示一组面部所属的角色；
- 角色集中维护质心向量，方便在线分配 / 合并 / 拆分；
- 嵌入向量复用 :func:`core.intelligence.clip.index._pack_vector` 的 magic 头部。
"""

from __future__ import annotations

import asyncio
import json
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import aiosqlite


_VECTOR_MAGIC = b"f32"


def _pack_vector(vec: list[float]) -> bytes:
    payload = struct.pack(f"<{len(vec)}f", *vec)
    return _VECTOR_MAGIC + struct.pack("<I", len(vec)) + payload


def _unpack_vector(blob: bytes) -> list[float]:
    if not blob.startswith(_VECTOR_MAGIC):
        raise ValueError("face 向量 blob 头部异常")
    dim = struct.unpack_from("<I", blob, len(_VECTOR_MAGIC))[0]
    body = blob[len(_VECTOR_MAGIC) + 4 :]
    if len(body) != dim * 4:
        raise ValueError(f"face 向量长度异常 dim={dim} body={len(body)}")
    return list(struct.unpack(f"<{dim}f", body))


@dataclass(slots=True)
class FaceRecord:
    """单个面部检测结果（DB 行的内存对应）。"""

    id: int
    media_id: int
    sha256: str
    person_id: int | None
    bbox: tuple[float, float, float, float]
    kps: list[tuple[float, float]]
    det_score: float
    embedding: list[float]
    thumb_path: str
    model_version: str
    created_at: float
    blur_var: float = 0.0
    """112×112 对齐人脸的 Laplacian 方差（清晰度），0 表示历史数据未计算。"""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "media_id": self.media_id,
            "sha256": self.sha256,
            "person_id": self.person_id,
            "bbox": list(self.bbox),
            "kps": [list(p) for p in self.kps],
            "det_score": self.det_score,
            "blur_var": self.blur_var,
            "thumb_path": self.thumb_path,
            "model_version": self.model_version,
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class PersonRecord:
    """角色（人物簇）信息。"""

    id: int
    name: str
    sample_face_id: int | None
    face_count: int
    centroid: list[float] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "sample_face_id": self.sample_face_id,
            "face_count": self.face_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class FaceIndexStore:
    """人脸索引持久化。

    线程安全：所有写操作通过 :class:`asyncio.Lock` 串行化；读操作仅持有连接，无显式锁。
    """

    SCHEMA_VERSION = 2

    def __init__(self, db_path: Path, *, dim: int = 512) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._dim = int(dim)
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    @property
    def dim(self) -> int:
        return self._dim

    async def initialize(self) -> None:
        async with self._lock:
            if self._conn is not None:
                return
            self._conn = await aiosqlite.connect(self._db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode = WAL")
            await self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS face_persons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL DEFAULT '',
                    sample_face_id INTEGER,
                    face_count INTEGER NOT NULL DEFAULT 0,
                    centroid BLOB,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            await self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS face_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    media_id INTEGER NOT NULL,
                    sha256 TEXT NOT NULL DEFAULT '',
                    person_id INTEGER,
                    bbox TEXT NOT NULL DEFAULT '[]',
                    kps TEXT NOT NULL DEFAULT '[]',
                    det_score REAL NOT NULL DEFAULT 0,
                    blur_var REAL NOT NULL DEFAULT 0,
                    embedding BLOB NOT NULL,
                    thumb_path TEXT NOT NULL DEFAULT '',
                    model_version TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    FOREIGN KEY(person_id) REFERENCES face_persons(id) ON DELETE SET NULL
                )
                """
            )
            await self._migrate_blur_var_column_unlocked()
            await self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS face_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            await self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS face_scans (
                    media_id INTEGER PRIMARY KEY,
                    scanned_at REAL NOT NULL,
                    face_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            await self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_face_records_media ON face_records(media_id)"
            )
            await self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_face_records_person ON face_records(person_id)"
            )
            await self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_face_records_sha ON face_records(sha256)"
            )
            await self._conn.commit()
            await self._set_meta_unlocked("schema_version", str(self.SCHEMA_VERSION))

    async def close(self) -> None:
        async with self._lock:
            if self._conn is not None:
                await self._conn.close()
                self._conn = None

    async def _migrate_blur_var_column_unlocked(self) -> None:
        """对历史 schema=1 的库追加 ``blur_var`` 列。"""
        assert self._conn is not None
        cursor = await self._conn.execute("PRAGMA table_info(face_records)")
        rows = await cursor.fetchall()
        columns = {str(row["name"]) for row in rows}
        if "blur_var" not in columns:
            await self._conn.execute(
                "ALTER TABLE face_records ADD COLUMN blur_var REAL NOT NULL DEFAULT 0"
            )
            await self._conn.commit()

    # ----- person 管理 -----

    async def list_persons(self) -> list[PersonRecord]:
        async with self._lock:
            assert self._conn is not None
            cursor = await self._conn.execute(
                "SELECT id, name, sample_face_id, face_count, centroid, created_at, updated_at "
                "FROM face_persons ORDER BY face_count DESC, id ASC"
            )
            rows = await cursor.fetchall()
            return [self._row_to_person(row) for row in rows]

    async def get_person(self, person_id: int) -> PersonRecord | None:
        async with self._lock:
            assert self._conn is not None
            cursor = await self._conn.execute(
                "SELECT id, name, sample_face_id, face_count, centroid, created_at, updated_at "
                "FROM face_persons WHERE id = ?",
                (int(person_id),),
            )
            row = await cursor.fetchone()
            return self._row_to_person(row) if row else None

    async def create_person(
        self,
        *,
        name: str = "",
        centroid: list[float] | None = None,
        sample_face_id: int | None = None,
    ) -> int:
        async with self._lock:
            return await self._create_person_unlocked(
                name=name, centroid=centroid, sample_face_id=sample_face_id
            )

    async def _create_person_unlocked(
        self,
        *,
        name: str = "",
        centroid: list[float] | None = None,
        sample_face_id: int | None = None,
    ) -> int:
        assert self._conn is not None
        now = time.time()
        cursor = await self._conn.execute(
            """
            INSERT INTO face_persons(name, sample_face_id, face_count, centroid, created_at, updated_at)
            VALUES (?, ?, 0, ?, ?, ?)
            """,
            (
                str(name or ""),
                sample_face_id,
                _pack_vector(centroid) if centroid else None,
                now,
                now,
            ),
        )
        await self._conn.commit()
        return int(cursor.lastrowid or 0)

    async def update_person(
        self,
        person_id: int,
        *,
        name: str | None = None,
        sample_face_id: int | None = None,
    ) -> None:
        sets: list[str] = []
        args: list[Any] = []
        if name is not None:
            sets.append("name = ?")
            args.append(str(name))
        if sample_face_id is not None:
            sets.append("sample_face_id = ?")
            args.append(int(sample_face_id))
        if not sets:
            return
        sets.append("updated_at = ?")
        args.append(time.time())
        args.append(int(person_id))
        async with self._lock:
            assert self._conn is not None
            await self._conn.execute(
                f"UPDATE face_persons SET {', '.join(sets)} WHERE id = ?", args
            )
            await self._conn.commit()

    async def update_person_centroid(
        self, person_id: int, centroid: list[float], *, face_count: int | None = None
    ) -> None:
        async with self._lock:
            await self._update_centroid_unlocked(
                person_id, centroid, face_count=face_count
            )

    async def _update_centroid_unlocked(
        self, person_id: int, centroid: list[float], *, face_count: int | None = None
    ) -> None:
        assert self._conn is not None
        now = time.time()
        if face_count is None:
            await self._conn.execute(
                "UPDATE face_persons SET centroid = ?, updated_at = ? WHERE id = ?",
                (_pack_vector(centroid), now, int(person_id)),
            )
        else:
            await self._conn.execute(
                "UPDATE face_persons SET centroid = ?, face_count = ?, updated_at = ? WHERE id = ?",
                (_pack_vector(centroid), int(face_count), now, int(person_id)),
            )
        await self._conn.commit()

    async def delete_person(self, person_id: int, *, reassign_to: int | None = None) -> None:
        async with self._lock:
            assert self._conn is not None
            if reassign_to is None:
                await self._conn.execute(
                    "UPDATE face_records SET person_id = NULL WHERE person_id = ?",
                    (int(person_id),),
                )
            else:
                await self._conn.execute(
                    "UPDATE face_records SET person_id = ? WHERE person_id = ?",
                    (int(reassign_to), int(person_id)),
                )
            await self._conn.execute(
                "DELETE FROM face_persons WHERE id = ?", (int(person_id),)
            )
            await self._conn.commit()

    async def increment_face_count(self, person_id: int, delta: int = 1) -> None:
        async with self._lock:
            assert self._conn is not None
            await self._conn.execute(
                "UPDATE face_persons SET face_count = MAX(0, face_count + ?), updated_at = ? "
                "WHERE id = ?",
                (int(delta), time.time(), int(person_id)),
            )
            await self._conn.commit()

    async def recount_persons(self) -> None:
        """根据 ``face_records.person_id`` 重新统计 ``face_count``。"""
        async with self._lock:
            assert self._conn is not None
            await self._conn.execute(
                """
                UPDATE face_persons SET face_count = (
                    SELECT COUNT(1) FROM face_records WHERE person_id = face_persons.id
                ),
                updated_at = ?
                """,
                (time.time(),),
            )
            await self._conn.commit()

    # ----- face 记录 -----

    async def add_face(
        self,
        *,
        media_id: int,
        sha256: str,
        bbox: tuple[float, float, float, float],
        kps: list[tuple[float, float]],
        det_score: float,
        embedding: list[float],
        person_id: int | None = None,
        thumb_path: str = "",
        model_version: str = "",
        blur_var: float = 0.0,
    ) -> int:
        if len(embedding) != self._dim:
            raise ValueError(
                f"face 向量维度不匹配: 期望 {self._dim}, 实际 {len(embedding)}"
            )
        async with self._lock:
            assert self._conn is not None
            now = time.time()
            cursor = await self._conn.execute(
                """
                INSERT INTO face_records(
                    media_id, sha256, person_id, bbox, kps, det_score, blur_var,
                    embedding, thumb_path, model_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(media_id),
                    str(sha256 or ""),
                    int(person_id) if person_id is not None else None,
                    json.dumps(list(bbox)),
                    json.dumps([list(p) for p in kps]),
                    float(det_score),
                    float(blur_var or 0.0),
                    _pack_vector(embedding),
                    str(thumb_path or ""),
                    str(model_version or ""),
                    now,
                ),
            )
            await self._conn.commit()
            return int(cursor.lastrowid or 0)

    async def set_face_thumb(self, face_id: int, thumb_path: str) -> None:
        async with self._lock:
            assert self._conn is not None
            await self._conn.execute(
                "UPDATE face_records SET thumb_path = ? WHERE id = ?",
                (str(thumb_path or ""), int(face_id)),
            )
            await self._conn.commit()

    async def reassign_face(self, face_id: int, person_id: int | None) -> None:
        async with self._lock:
            assert self._conn is not None
            await self._conn.execute(
                "UPDATE face_records SET person_id = ? WHERE id = ?",
                (int(person_id) if person_id is not None else None, int(face_id)),
            )
            await self._conn.commit()

    async def reassign_faces(
        self, face_ids: Iterable[int], person_id: int | None
    ) -> int:
        ids = [int(f) for f in face_ids]
        if not ids:
            return 0
        async with self._lock:
            assert self._conn is not None
            placeholders = ",".join("?" * len(ids))
            cursor = await self._conn.execute(
                f"UPDATE face_records SET person_id = ? WHERE id IN ({placeholders})",
                [int(person_id) if person_id is not None else None, *ids],
            )
            await self._conn.commit()
            return cursor.rowcount or 0

    async def list_faces_by_person(
        self, person_id: int, *, limit: int = 200, offset: int = 0
    ) -> list[FaceRecord]:
        async with self._lock:
            assert self._conn is not None
            cursor = await self._conn.execute(
                "SELECT * FROM face_records WHERE person_id = ? "
                "ORDER BY det_score DESC, id ASC LIMIT ? OFFSET ?",
                (int(person_id), int(limit), int(offset)),
            )
            rows = await cursor.fetchall()
            return [self._row_to_face(row) for row in rows]

    async def list_faces_by_media(self, media_id: int) -> list[FaceRecord]:
        async with self._lock:
            assert self._conn is not None
            cursor = await self._conn.execute(
                "SELECT * FROM face_records WHERE media_id = ? "
                "ORDER BY det_score DESC, id ASC",
                (int(media_id),),
            )
            rows = await cursor.fetchall()
            return [self._row_to_face(row) for row in rows]

    async def get_face(self, face_id: int) -> FaceRecord | None:
        async with self._lock:
            assert self._conn is not None
            cursor = await self._conn.execute(
                "SELECT * FROM face_records WHERE id = ?", (int(face_id),)
            )
            row = await cursor.fetchone()
            return self._row_to_face(row) if row else None

    async def list_faces_unassigned(self, *, limit: int = 500) -> list[FaceRecord]:
        async with self._lock:
            assert self._conn is not None
            cursor = await self._conn.execute(
                "SELECT * FROM face_records WHERE person_id IS NULL "
                "ORDER BY id ASC LIMIT ?",
                (int(limit),),
            )
            rows = await cursor.fetchall()
            return [self._row_to_face(row) for row in rows]

    async def list_indexed_media_ids(self) -> set[int]:
        """返回所有已经被扫描过的 media_id（无论是否检测到人脸）。"""
        async with self._lock:
            assert self._conn is not None
            cursor = await self._conn.execute("SELECT media_id FROM face_scans")
            rows = await cursor.fetchall()
            return {int(row["media_id"]) for row in rows}

    async def list_face_thumb_targets(
        self,
    ) -> list[tuple[int, int, tuple[float, float, float, float]]]:
        """返回 ``[(face_id, media_id, bbox)]``，用于批量重建缩略图。"""
        async with self._lock:
            assert self._conn is not None
            cursor = await self._conn.execute(
                "SELECT id, media_id, bbox FROM face_records ORDER BY id ASC"
            )
            rows = await cursor.fetchall()
            out: list[tuple[int, int, tuple[float, float, float, float]]] = []
            for row in rows:
                try:
                    bbox_arr = json.loads(row["bbox"]) if row["bbox"] else []
                except (TypeError, ValueError):
                    bbox_arr = []
                if not isinstance(bbox_arr, list) or len(bbox_arr) < 4:
                    continue
                bbox = (
                    float(bbox_arr[0]),
                    float(bbox_arr[1]),
                    float(bbox_arr[2]),
                    float(bbox_arr[3]),
                )
                out.append((int(row["id"]), int(row["media_id"]), bbox))
            return out

    async def list_orphan_face_records(
        self, valid_media_ids: Iterable[int]
    ) -> list[int]:
        """返回所有 media_id 不在 ``valid_media_ids`` 中的 face_id。"""
        valid = {int(mid) for mid in valid_media_ids}
        async with self._lock:
            assert self._conn is not None
            cursor = await self._conn.execute(
                "SELECT id, media_id FROM face_records"
            )
            rows = await cursor.fetchall()
            return [
                int(row["id"]) for row in rows if int(row["media_id"]) not in valid
            ]

    async def mark_scanned(self, media_id: int, face_count: int) -> None:
        async with self._lock:
            assert self._conn is not None
            await self._conn.execute(
                """
                INSERT INTO face_scans(media_id, scanned_at, face_count)
                VALUES (?, ?, ?)
                ON CONFLICT(media_id) DO UPDATE SET
                    scanned_at = excluded.scanned_at,
                    face_count = excluded.face_count
                """,
                (int(media_id), time.time(), int(face_count)),
            )
            await self._conn.commit()

    async def forget_scan(self, media_id: int) -> None:
        async with self._lock:
            assert self._conn is not None
            await self._conn.execute(
                "DELETE FROM face_scans WHERE media_id = ?", (int(media_id),)
            )
            await self._conn.commit()

    async def list_all_embeddings(self) -> list[tuple[int, int | None, list[float]]]:
        """供 DBSCAN 使用，返回 ``[(face_id, person_id, embedding)]``。"""
        async with self._lock:
            assert self._conn is not None
            cursor = await self._conn.execute(
                "SELECT id, person_id, embedding FROM face_records"
            )
            rows = await cursor.fetchall()
            out: list[tuple[int, int | None, list[float]]] = []
            for row in rows:
                try:
                    vec = _unpack_vector(row["embedding"])
                except ValueError:
                    continue
                out.append(
                    (
                        int(row["id"]),
                        int(row["person_id"]) if row["person_id"] is not None else None,
                        vec,
                    )
                )
            return out

    async def prune_low_quality_faces(
        self,
        *,
        min_det_score: float = 0.0,
        min_face_size: float = 0.0,
        min_blur_var: float = 0.0,
        ignore_blur_var_zero: bool = True,
    ) -> list[int]:
        """根据阈值删除已有低质量人脸记录，返回被删除的 ``face_id`` 列表。

        - ``min_det_score`` / ``min_face_size``：直接基于 DB 字段判定；
        - ``min_blur_var``：仅当存量记录已经计算过清晰度时（blur_var > 0）参与判定；
          ``ignore_blur_var_zero=True``（默认）会跳过历史未计算的记录，避免误删。
        """
        async with self._lock:
            assert self._conn is not None
            cursor = await self._conn.execute(
                "SELECT id, bbox, det_score, blur_var FROM face_records"
            )
            rows = await cursor.fetchall()

        to_delete: list[int] = []
        for row in rows:
            score = float(row["det_score"] or 0.0)
            blur = float(row["blur_var"] or 0.0)
            try:
                bbox_arr = json.loads(row["bbox"]) if row["bbox"] else []
            except (TypeError, ValueError):
                bbox_arr = []
            if isinstance(bbox_arr, list) and len(bbox_arr) >= 4:
                width = max(0.0, float(bbox_arr[2]) - float(bbox_arr[0]))
                height = max(0.0, float(bbox_arr[3]) - float(bbox_arr[1]))
                short_side = min(width, height)
            else:
                short_side = 0.0

            drop = False
            if min_det_score > 0 and score < min_det_score:
                drop = True
            elif min_face_size > 0 and short_side < min_face_size:
                drop = True
            elif min_blur_var > 0 and blur > 0 and blur < min_blur_var:
                drop = True
            elif (
                min_blur_var > 0
                and not ignore_blur_var_zero
                and blur < min_blur_var
            ):
                drop = True
            if drop:
                to_delete.append(int(row["id"]))

        if not to_delete:
            return []

        async with self._lock:
            assert self._conn is not None
            placeholders = ",".join("?" * len(to_delete))
            await self._conn.execute(
                f"DELETE FROM face_records WHERE id IN ({placeholders})",
                to_delete,
            )
            await self._conn.commit()
        return to_delete

    async def delete_faces_for_media(self, media_id: int) -> int:
        async with self._lock:
            assert self._conn is not None
            cursor = await self._conn.execute(
                "DELETE FROM face_records WHERE media_id = ?", (int(media_id),)
            )
            await self._conn.execute(
                "DELETE FROM face_scans WHERE media_id = ?", (int(media_id),)
            )
            await self._conn.commit()
            return cursor.rowcount or 0

    async def count_faces(self) -> int:
        async with self._lock:
            assert self._conn is not None
            cursor = await self._conn.execute("SELECT COUNT(1) AS c FROM face_records")
            row = await cursor.fetchone()
            return int(row["c"]) if row else 0

    async def count_persons(self) -> int:
        async with self._lock:
            assert self._conn is not None
            cursor = await self._conn.execute("SELECT COUNT(1) AS c FROM face_persons")
            row = await cursor.fetchone()
            return int(row["c"]) if row else 0

    async def clear_all(self) -> dict[str, int]:
        """清空 ``face_records`` / ``face_persons`` / ``face_scans`` 三张表。

        返回 ``{"face_count": 被清理人脸数, "person_count": 被清理角色数}``，
        便于上层做日志/反馈。
        """
        async with self._lock:
            assert self._conn is not None
            cursor = await self._conn.execute(
                "SELECT COUNT(1) AS c FROM face_records"
            )
            row = await cursor.fetchone()
            face_count = int(row["c"]) if row else 0
            cursor = await self._conn.execute(
                "SELECT COUNT(1) AS c FROM face_persons"
            )
            row = await cursor.fetchone()
            person_count = int(row["c"]) if row else 0
            await self._conn.execute("DELETE FROM face_records")
            await self._conn.execute("DELETE FROM face_persons")
            await self._conn.execute("DELETE FROM face_scans")
            await self._conn.commit()
        return {"face_count": face_count, "person_count": person_count}

    # ----- meta -----

    async def set_meta(self, key: str, value: str) -> None:
        async with self._lock:
            await self._set_meta_unlocked(key, value)

    async def _set_meta_unlocked(self, key: str, value: str) -> None:
        assert self._conn is not None
        await self._conn.execute(
            """
            INSERT INTO face_meta(key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (key, value, time.time()),
        )
        await self._conn.commit()

    async def get_meta(self, key: str) -> str | None:
        async with self._lock:
            assert self._conn is not None
            cursor = await self._conn.execute(
                "SELECT value FROM face_meta WHERE key = ?", (key,)
            )
            row = await cursor.fetchone()
            return str(row["value"]) if row else None

    # ----- 行解析 -----

    @staticmethod
    def _row_to_face(row: aiosqlite.Row) -> FaceRecord:
        bbox_arr = json.loads(row["bbox"]) if row["bbox"] else [0.0, 0.0, 0.0, 0.0]
        kps_arr = json.loads(row["kps"]) if row["kps"] else []
        bbox: tuple[float, float, float, float]
        if isinstance(bbox_arr, list) and len(bbox_arr) >= 4:
            bbox = (
                float(bbox_arr[0]),
                float(bbox_arr[1]),
                float(bbox_arr[2]),
                float(bbox_arr[3]),
            )
        else:
            bbox = (0.0, 0.0, 0.0, 0.0)
        kps_list: list[tuple[float, float]] = []
        if isinstance(kps_arr, list):
            for p in kps_arr:
                if isinstance(p, list) and len(p) >= 2:
                    kps_list.append((float(p[0]), float(p[1])))
        try:
            embedding = _unpack_vector(row["embedding"])
        except ValueError:
            embedding = []
        try:
            blur_var = float(row["blur_var"] or 0.0)
        except (KeyError, IndexError, TypeError, ValueError):
            blur_var = 0.0
        return FaceRecord(
            id=int(row["id"]),
            media_id=int(row["media_id"]),
            sha256=str(row["sha256"] or ""),
            person_id=int(row["person_id"]) if row["person_id"] is not None else None,
            bbox=bbox,
            kps=kps_list,
            det_score=float(row["det_score"] or 0.0),
            embedding=embedding,
            thumb_path=str(row["thumb_path"] or ""),
            model_version=str(row["model_version"] or ""),
            created_at=float(row["created_at"] or 0.0),
            blur_var=blur_var,
        )

    @staticmethod
    def _row_to_person(row: aiosqlite.Row) -> PersonRecord:
        try:
            centroid = (
                _unpack_vector(row["centroid"]) if row["centroid"] is not None else []
            )
        except ValueError:
            centroid = []
        return PersonRecord(
            id=int(row["id"]),
            name=str(row["name"] or ""),
            sample_face_id=(
                int(row["sample_face_id"]) if row["sample_face_id"] is not None else None
            ),
            face_count=int(row["face_count"] or 0),
            centroid=centroid,
            created_at=float(row["created_at"] or 0.0),
            updated_at=float(row["updated_at"] or 0.0),
        )


def serialize_vector(vec: list[float]) -> bytes:
    return _pack_vector(vec)


def deserialize_vector(blob: bytes) -> list[float]:
    return _unpack_vector(blob)
