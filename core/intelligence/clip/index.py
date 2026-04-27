"""CLIP 嵌入持久化与近邻检索。

单独使用 ``intelligence/clip_index.db``（SQLite + 二进制向量），与 ``index.db`` 解耦，
便于在「重新索引 / 清空索引 / 关掉 CLIP」时安全地整体重建。

近邻检索优先调用 ``hnswlib``（如果安装且数据规模较大），否则回退到全量余弦计算。
对于个人媒体库（10k 量级以内）暴力余弦完全可接受，且不引入额外依赖。
"""

from __future__ import annotations

import asyncio
import json
import struct
import time
from pathlib import Path
from typing import Any, Iterable

import aiosqlite

from astrbot.api import logger


_VECTOR_DTYPE_PREFIX = b"f32"  # 头部 magic，便于以后扩展量化版


def _pack_vector(vec: list[float]) -> bytes:
    payload = struct.pack(f"<{len(vec)}f", *vec)
    return _VECTOR_DTYPE_PREFIX + struct.pack("<I", len(vec)) + payload


def _unpack_vector(blob: bytes) -> list[float]:
    if len(blob) < len(_VECTOR_DTYPE_PREFIX) + 4:
        raise ValueError("clip 向量 blob 过短")
    if not blob.startswith(_VECTOR_DTYPE_PREFIX):
        raise ValueError("clip 向量 blob 头部异常")
    dim = struct.unpack_from("<I", blob, len(_VECTOR_DTYPE_PREFIX))[0]
    body = blob[len(_VECTOR_DTYPE_PREFIX) + 4 :]
    if len(body) != dim * 4:
        raise ValueError(f"clip 向量长度异常: dim={dim} body={len(body)}")
    return list(struct.unpack(f"<{dim}f", body))


class ClipIndexStore:
    """CLIP 索引存储。

    Args:
        db_path: SQLite 文件路径，未存在会自动创建。
        dim: 期望向量维度（默认 512，对应 ViT-B/16）。
        hnsw_path: 可选的 HNSW 持久化路径；为 ``None`` 时关闭 HNSW，回退暴力检索。
    """

    SCHEMA_VERSION = 1

    def __init__(
        self,
        db_path: Path,
        *,
        dim: int = 512,
        hnsw_path: Path | None = None,
        hnsw_ef: int = 64,
        hnsw_m: int = 16,
        hnsw_ef_construction: int = 200,
    ) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._dim = int(dim)
        self._hnsw_path = Path(hnsw_path) if hnsw_path else None
        self._hnsw_ef = hnsw_ef
        self._hnsw_m = hnsw_m
        self._hnsw_ef_construction = hnsw_ef_construction

        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()
        self._index: Any = None  # hnswlib.Index 或 None
        self._index_dirty = False
        self._cached_vectors: dict[int, list[float]] | None = None

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
                CREATE TABLE IF NOT EXISTS clip_embeddings (
                    media_id INTEGER PRIMARY KEY,
                    sha256 TEXT NOT NULL DEFAULT '',
                    vector BLOB NOT NULL,
                    dim INTEGER NOT NULL,
                    model_version TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            await self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS clip_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            await self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_clip_emb_sha ON clip_embeddings(sha256)"
            )
            await self._conn.commit()
            await self._set_meta_unlocked("schema_version", str(self.SCHEMA_VERSION))

    async def close(self) -> None:
        async with self._lock:
            if self._conn is not None:
                await self._conn.close()
                self._conn = None
            self._save_index_locked()
            self._index = None
            self._cached_vectors = None

    async def upsert(
        self,
        media_id: int,
        sha256: str,
        vector: list[float],
        *,
        model_version: str = "",
    ) -> None:
        if len(vector) != self._dim:
            raise ValueError(
                f"clip 向量维度不匹配: 期望 {self._dim}, 实际 {len(vector)}"
            )
        async with self._lock:
            assert self._conn is not None
            blob = _pack_vector(vector)
            now = time.time()
            await self._conn.execute(
                """
                INSERT INTO clip_embeddings(media_id, sha256, vector, dim, model_version, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(media_id) DO UPDATE SET
                    sha256 = excluded.sha256,
                    vector = excluded.vector,
                    dim = excluded.dim,
                    model_version = excluded.model_version,
                    updated_at = excluded.updated_at
                """,
                (media_id, sha256, blob, self._dim, model_version, now, now),
            )
            await self._conn.commit()
            self._invalidate_cache_unlocked(media_id, vector)

    async def delete(self, media_id: int) -> None:
        async with self._lock:
            assert self._conn is not None
            await self._conn.execute(
                "DELETE FROM clip_embeddings WHERE media_id = ?", (media_id,)
            )
            await self._conn.commit()
            self._invalidate_cache_unlocked(media_id, None)

    async def delete_many(self, media_ids: Iterable[int]) -> int:
        ids = [int(m) for m in media_ids]
        if not ids:
            return 0
        async with self._lock:
            assert self._conn is not None
            placeholders = ",".join("?" * len(ids))
            cursor = await self._conn.execute(
                f"DELETE FROM clip_embeddings WHERE media_id IN ({placeholders})",
                ids,
            )
            await self._conn.commit()
            for mid in ids:
                self._invalidate_cache_unlocked(mid, None)
            return cursor.rowcount or 0

    async def list_media_ids(self) -> set[int]:
        async with self._lock:
            assert self._conn is not None
            cursor = await self._conn.execute(
                "SELECT media_id FROM clip_embeddings"
            )
            rows = await cursor.fetchall()
            return {int(row["media_id"]) for row in rows}

    async def count(self) -> int:
        async with self._lock:
            assert self._conn is not None
            cursor = await self._conn.execute(
                "SELECT COUNT(1) AS c FROM clip_embeddings"
            )
            row = await cursor.fetchone()
            return int(row["c"]) if row else 0

    async def get_vector(self, media_id: int) -> list[float] | None:
        async with self._lock:
            assert self._conn is not None
            cursor = await self._conn.execute(
                "SELECT vector FROM clip_embeddings WHERE media_id = ?", (media_id,)
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return _unpack_vector(row["vector"])

    async def get_meta(self, key: str) -> str | None:
        async with self._lock:
            assert self._conn is not None
            cursor = await self._conn.execute(
                "SELECT value FROM clip_meta WHERE key = ?", (key,)
            )
            row = await cursor.fetchone()
            return str(row["value"]) if row else None

    async def set_meta(self, key: str, value: str) -> None:
        async with self._lock:
            await self._set_meta_unlocked(key, value)

    async def _set_meta_unlocked(self, key: str, value: str) -> None:
        assert self._conn is not None
        await self._conn.execute(
            """
            INSERT INTO clip_meta(key, value, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (key, value, time.time()),
        )
        await self._conn.commit()

    async def search(
        self, query_vector: list[float], *, top_k: int = 20
    ) -> list[tuple[int, float]]:
        """返回 ``[(media_id, similarity)]``，按 ``similarity`` 降序。"""
        if len(query_vector) != self._dim:
            raise ValueError("查询向量维度不匹配")
        async with self._lock:
            await self._refresh_cache_unlocked()
            if not self._cached_vectors:
                return []
            # 暴力余弦：向量都已 L2 归一化，因此点积即余弦。
            scored = sorted(
                (
                    (mid, _dot(query_vector, vec))
                    for mid, vec in self._cached_vectors.items()
                ),
                key=lambda item: item[1],
                reverse=True,
            )
            return scored[: max(1, int(top_k))]

    # ----- 内部缓存 -----

    async def _refresh_cache_unlocked(self) -> None:
        if self._cached_vectors is not None:
            return
        assert self._conn is not None
        cursor = await self._conn.execute(
            "SELECT media_id, vector FROM clip_embeddings"
        )
        rows = await cursor.fetchall()
        cache: dict[int, list[float]] = {}
        for row in rows:
            try:
                cache[int(row["media_id"])] = _unpack_vector(row["vector"])
            except ValueError as exc:
                logger.warning("解析 clip 向量失败 media_id=%s: %s", row["media_id"], exc)
        self._cached_vectors = cache

    def _invalidate_cache_unlocked(
        self, media_id: int, new_vector: list[float] | None
    ) -> None:
        if self._cached_vectors is None:
            return
        if new_vector is None:
            self._cached_vectors.pop(media_id, None)
        else:
            self._cached_vectors[media_id] = list(new_vector)
        self._index_dirty = True

    def _save_index_locked(self) -> None:
        if self._index is None or self._hnsw_path is None or not self._index_dirty:
            return
        try:
            self._index.save_index(str(self._hnsw_path))
            self._index_dirty = False
        except Exception:  # pragma: no cover - hnswlib 异常路径
            logger.exception("保存 HNSW 索引失败")


def _dot(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))


def serialize_vector(vec: list[float]) -> bytes:
    """供测试 / 外部脚本使用。"""
    return _pack_vector(vec)


def deserialize_vector(blob: bytes) -> list[float]:
    return _unpack_vector(blob)


def export_meta_dict(meta_pairs: list[tuple[str, str]]) -> dict[str, Any]:
    """把 ``[(key, value)]`` 序列转成 JSON 友好的 dict（值优先 JSON parse）。"""
    out: dict[str, Any] = {}
    for key, value in meta_pairs:
        try:
            out[key] = json.loads(value)
        except (ValueError, TypeError):
            out[key] = value
    return out
