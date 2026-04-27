"""ClipIndexStore + ClipIndexWorker 单元测试。

不依赖 onnxruntime；编码函数由测试自行 mock，只验证存储 + 检索 + 增量扫描的语义。
"""

from __future__ import annotations

import asyncio
import math
from pathlib import Path

import pytest

from astrbot_plugin_media_portal.core.intelligence.clip.index import (
    ClipIndexStore,
    deserialize_vector,
    serialize_vector,
)
from astrbot_plugin_media_portal.core.intelligence.clip.worker import ClipIndexWorker

pytestmark = pytest.mark.asyncio


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


async def test_serialize_roundtrip() -> None:
    vec = [0.1, -0.2, 0.3, 0.4]
    blob = serialize_vector(vec)
    assert deserialize_vector(blob) == pytest.approx(vec)


async def test_index_store_upsert_and_search(tmp_path: Path) -> None:
    store = ClipIndexStore(db_path=tmp_path / "clip.db", dim=3)
    await store.initialize()

    v1 = _normalize([1.0, 0.0, 0.0])
    v2 = _normalize([0.0, 1.0, 0.0])
    v3 = _normalize([1.0, 1.0, 0.0])
    await store.upsert(1, "sha-1", v1)
    await store.upsert(2, "sha-2", v2)
    await store.upsert(3, "sha-3", v3)

    assert await store.count() == 3

    # 查询接近 v1 的方向
    query = _normalize([0.9, 0.1, 0.0])
    results = await store.search(query, top_k=2)
    assert results[0][0] == 1
    assert results[0][1] > results[1][1]

    # upsert 覆盖
    await store.upsert(1, "sha-1b", _normalize([0.0, 0.0, 1.0]))
    new_results = await store.search(_normalize([0.0, 0.0, 1.0]), top_k=1)
    assert new_results[0][0] == 1

    await store.delete(2)
    assert 2 not in await store.list_media_ids()

    await store.set_meta("last_scan_at", "1700000000")
    assert await store.get_meta("last_scan_at") == "1700000000"

    await store.close()


async def test_index_store_dim_mismatch(tmp_path: Path) -> None:
    store = ClipIndexStore(db_path=tmp_path / "clip.db", dim=4)
    await store.initialize()
    with pytest.raises(ValueError):
        await store.upsert(1, "x", [0.1, 0.2, 0.3])
    await store.close()


async def test_worker_full_scan_indexes_only_missing(tmp_path: Path) -> None:
    store = ClipIndexStore(db_path=tmp_path / "clip.db", dim=2)
    await store.initialize()
    # 提前已索引 media_id=1，避免 worker 重新计算。
    await store.upsert(1, "sha-1", _normalize([1.0, 0.0]))

    encoded: list[int] = []

    async def encoder(path: str) -> list[float]:
        encoded.append(int(path))
        return _normalize([1.0, float(int(path))])

    async def iter_records():
        return [
            (1, "sha-1", "1"),
            (2, "sha-2", "2"),
            (3, "sha-3", "3"),
        ]

    worker = ClipIndexWorker(
        store=store,
        iter_image_records=iter_records,
        encode_image=encoder,
        model_version="test-clip",
    )
    stats = await worker.run_full_scan()
    assert stats.indexed == 2
    assert stats.failed == 0
    # encoder 应只被两条新记录调用
    assert sorted(encoded) == [2, 3]
    assert await store.count() == 3

    await store.close()


async def test_worker_handles_encoding_failures(tmp_path: Path) -> None:
    store = ClipIndexStore(db_path=tmp_path / "clip.db", dim=2)
    await store.initialize()

    async def encoder(path: str) -> list[float]:
        if path == "bad":
            raise RuntimeError("boom")
        return _normalize([0.5, 0.5])

    async def iter_records():
        return [
            (10, "ok", "good"),
            (11, "ng", "bad"),
        ]

    worker = ClipIndexWorker(
        store=store,
        iter_image_records=iter_records,
        encode_image=encoder,
        model_version="test-clip",
        max_retries=0,
    )
    stats = await worker.run_full_scan()
    assert stats.indexed == 1
    assert stats.failed == 1
    assert 11 in stats.failed_media_ids
    assert "boom" in stats.last_error

    # 第二次再跑应当跳过失败项，不再重试。
    stats2 = await worker.run_full_scan()
    assert stats2.indexed == 0
    await store.close()


async def test_worker_cleanup_orphans(tmp_path: Path) -> None:
    store = ClipIndexStore(db_path=tmp_path / "clip.db", dim=2)
    await store.initialize()
    for media_id in (1, 2, 3, 4):
        await store.upsert(media_id, f"sha-{media_id}", _normalize([1.0, 0.0]))

    async def encoder(path: str) -> list[float]:
        return _normalize([1.0, 0.0])

    async def iter_records():
        return [(1, "sha-1", "1"), (3, "sha-3", "3")]

    worker = ClipIndexWorker(
        store=store, iter_image_records=iter_records, encode_image=encoder
    )
    removed = await worker.cleanup_orphans({1, 3})
    assert removed == 2
    assert await store.list_media_ids() == {1, 3}
    await store.close()
