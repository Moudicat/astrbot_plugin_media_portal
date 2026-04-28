"""FaceIndexWorker 单元测试（mocked engine）。"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from astrbot_plugin_media_portal.core.intelligence.face.cluster import FaceClusterer
from astrbot_plugin_media_portal.core.intelligence.face.engine import FaceDetection
from astrbot_plugin_media_portal.core.intelligence.face.index import FaceIndexStore
from astrbot_plugin_media_portal.core.intelligence.face.worker import FaceIndexWorker

pytestmark = pytest.mark.asyncio


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm if norm else 0.0 for v in vec]


class _FakeEngine:
    def __init__(self, mapping: dict[str, list[FaceDetection]]) -> None:
        self._mapping = mapping
        self.calls: list[str] = []

    async def detect(self, source):
        self.calls.append(str(source))
        return list(self._mapping.get(str(source), []))


async def test_worker_indexes_and_clusters(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = FaceIndexStore(db_path=tmp_path / "face.db", dim=3)
    await store.initialize()
    clusterer = FaceClusterer(store, assign_threshold=0.6)

    detections = {
        "/img/1.jpg": [
            FaceDetection(
                bbox=(0.0, 0.0, 50.0, 50.0),
                kps=[(1.0, 1.0)] * 5,
                det_score=0.99,
                embedding=_normalize([1.0, 0.0, 0.0]),
            )
        ],
        "/img/2.jpg": [
            FaceDetection(
                bbox=(10.0, 10.0, 60.0, 60.0),
                kps=[(2.0, 2.0)] * 5,
                det_score=0.95,
                embedding=_normalize([0.95, 0.05, 0.0]),
            ),
            FaceDetection(
                bbox=(70.0, 70.0, 100.0, 100.0),
                kps=[(3.0, 3.0)] * 5,
                det_score=0.9,
                embedding=_normalize([0.0, 1.0, 0.0]),
            ),
        ],
        "/img/3.jpg": [],  # no faces detected
    }

    engine = _FakeEngine(detections)

    async def iter_records():
        return [
            (1, "sha-1", "/img/1.jpg"),
            (2, "sha-2", "/img/2.jpg"),
            (3, "sha-3", "/img/3.jpg"),
        ]

    monkeypatch.setattr(
        "astrbot_plugin_media_portal.core.intelligence.face.worker._crop_and_save_thumb",
        lambda *args, **kwargs: None,
    )

    worker = FaceIndexWorker(
        store=store,
        engine=engine,  # type: ignore[arg-type]
        clusterer=clusterer,
        iter_image_records=iter_records,
        thumb_dir=tmp_path / "thumbs",
        model_version="test-face",
        max_retries=0,
    )

    stats = await worker.run_full_scan()
    assert stats.media_processed == 3
    assert stats.faces_indexed == 3
    assert await store.count_faces() == 3
    persons = await store.list_persons()
    assert len(persons) == 2  # 两个独立角色

    indexed = await store.list_indexed_media_ids()
    assert indexed == {1, 2, 3}

    # 第二次扫描：所有媒体已被记录，应跳过
    stats2 = await worker.run_full_scan()
    assert stats2.media_processed == 0
    assert stats2.faces_indexed == 0

    await store.close()


async def test_worker_marks_failed(tmp_path: Path) -> None:
    store = FaceIndexStore(db_path=tmp_path / "face.db", dim=3)
    await store.initialize()
    clusterer = FaceClusterer(store)

    class _FailingEngine:
        async def detect(self, source):
            raise RuntimeError("boom")

    async def iter_records():
        return [(1, "sha-1", "/img/x.jpg")]

    worker = FaceIndexWorker(
        store=store,
        engine=_FailingEngine(),  # type: ignore[arg-type]
        clusterer=clusterer,
        iter_image_records=iter_records,
        thumb_dir=tmp_path / "thumbs",
        max_retries=0,
    )
    stats = await worker.run_full_scan()
    assert stats.failed == 1
    assert "boom" in stats.last_error
    assert 1 in stats.failed_media_ids

    # 二次执行不再重试同一个失败 media_id
    stats2 = await worker.run_full_scan()
    assert stats2.failed == 0
    await store.close()


async def test_worker_filters_low_quality(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """超过阈值的人脸入库，糊脸 / 小脸 / 低分被丢弃并计入 faces_filtered。"""
    store = FaceIndexStore(db_path=tmp_path / "face.db", dim=3)
    await store.initialize()
    clusterer = FaceClusterer(store, assign_threshold=0.6)

    detections = {
        "/img/mix.jpg": [
            FaceDetection(  # 高质量，应入库
                bbox=(0.0, 0.0, 120.0, 120.0),
                kps=[(1.0, 1.0)] * 5,
                det_score=0.95,
                embedding=_normalize([1.0, 0.0, 0.0]),
                blur_var=200.0,
            ),
            FaceDetection(  # 边长不够
                bbox=(0.0, 0.0, 30.0, 30.0),
                kps=[(2.0, 2.0)] * 5,
                det_score=0.95,
                embedding=_normalize([0.95, 0.05, 0.0]),
                blur_var=200.0,
            ),
            FaceDetection(  # 检测分数不够
                bbox=(0.0, 0.0, 120.0, 120.0),
                kps=[(3.0, 3.0)] * 5,
                det_score=0.4,
                embedding=_normalize([0.0, 1.0, 0.0]),
                blur_var=200.0,
            ),
            FaceDetection(  # Laplacian 方差不够
                bbox=(0.0, 0.0, 120.0, 120.0),
                kps=[(4.0, 4.0)] * 5,
                det_score=0.95,
                embedding=_normalize([0.0, 0.0, 1.0]),
                blur_var=10.0,
            ),
        ]
    }
    engine = _FakeEngine(detections)

    async def iter_records():
        return [(1, "sha-1", "/img/mix.jpg")]

    monkeypatch.setattr(
        "astrbot_plugin_media_portal.core.intelligence.face.worker._crop_and_save_thumb",
        lambda *args, **kwargs: None,
    )

    worker = FaceIndexWorker(
        store=store,
        engine=engine,  # type: ignore[arg-type]
        clusterer=clusterer,
        iter_image_records=iter_records,
        thumb_dir=tmp_path / "thumbs",
        model_version="test-face",
        max_retries=0,
        min_det_score=0.6,
        min_face_size=60,
        min_blur_var=60.0,
    )

    stats = await worker.run_full_scan()
    assert stats.faces_indexed == 1
    assert stats.faces_filtered == 3
    assert await store.count_faces() == 1

    # 落库的那张人脸应当带上原始 blur_var
    persons = await store.list_persons()
    assert len(persons) == 1
    faces = await store.list_faces_by_person(persons[0].id)
    assert faces[0].blur_var == pytest.approx(200.0)

    # 阈值热更新后再次扫描（同一 media 已 marked，跳过；这里清掉重扫）
    await store.forget_scan(1)
    worker.update_quality_thresholds(min_blur_var=0.0)
    stats2 = await worker.run_full_scan()
    # 仅放宽了 blur 阈值：原本糊脸通过；size/det_score 阈值未变，依旧过滤 2 张
    assert stats2.faces_indexed == 2
    assert stats2.faces_filtered == 2

    await store.close()


async def test_worker_cleanup_orphans(tmp_path: Path) -> None:
    store = FaceIndexStore(db_path=tmp_path / "face.db", dim=2)
    await store.initialize()
    clusterer = FaceClusterer(store)
    for i in range(1, 5):
        fid = await store.add_face(
            media_id=i,
            sha256=f"s{i}",
            bbox=(0, 0, 1, 1),
            kps=[],
            det_score=0.5,
            embedding=_normalize([1.0, float(i)]),
        )
        await store.mark_scanned(i, 1)
        result = await clusterer.assign_face(_normalize([1.0, float(i)]), face_id=fid)
        await store.reassign_face(fid, result.person_id)

    class _NoopEngine:
        async def detect(self, source):
            return []

    async def iter_records():
        return []

    worker = FaceIndexWorker(
        store=store,
        engine=_NoopEngine(),  # type: ignore[arg-type]
        clusterer=clusterer,
        iter_image_records=iter_records,
        thumb_dir=tmp_path / "thumbs",
    )
    removed = await worker.cleanup_orphans({1, 3})
    assert removed == 2
    assert await store.list_indexed_media_ids() == {1, 3}
    await store.close()
