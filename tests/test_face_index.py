"""FaceIndexStore + FaceClusterer 单元测试。

不依赖 insightface / sklearn / numpy；DBSCAN 通过 monkeypatch 注入伪分类结果。
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from astrbot_plugin_media_portal.core.intelligence.face.cluster import FaceClusterer
from astrbot_plugin_media_portal.core.intelligence.face.index import (
    FaceIndexStore,
    deserialize_vector,
    serialize_vector,
)

pytestmark = pytest.mark.asyncio


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return list(vec)
    return [v / norm for v in vec]


async def test_face_vector_roundtrip() -> None:
    vec = [0.1, -0.2, 0.7]
    blob = serialize_vector(vec)
    assert deserialize_vector(blob) == pytest.approx(vec)


async def test_face_store_basic_crud(tmp_path: Path) -> None:
    store = FaceIndexStore(db_path=tmp_path / "face.db", dim=3)
    await store.initialize()

    pid = await store.create_person(name="alice", centroid=_normalize([1.0, 0.0, 0.0]))
    assert pid > 0

    fid = await store.add_face(
        media_id=10,
        sha256="sha-10",
        bbox=(0.0, 0.0, 100.0, 100.0),
        kps=[(1.0, 2.0)] * 5,
        det_score=0.9,
        embedding=_normalize([1.0, 0.0, 0.0]),
        person_id=pid,
        thumb_path="/tmp/face.jpg",
        model_version="test",
    )
    assert fid > 0

    face = await store.get_face(fid)
    assert face is not None
    assert face.media_id == 10
    assert face.det_score == pytest.approx(0.9)
    assert face.embedding == pytest.approx(_normalize([1.0, 0.0, 0.0]))
    assert face.thumb_path == "/tmp/face.jpg"

    await store.set_face_thumb(fid, "/tmp/new.jpg")
    face2 = await store.get_face(fid)
    assert face2 is not None and face2.thumb_path == "/tmp/new.jpg"

    persons = await store.list_persons()
    assert len(persons) == 1 and persons[0].name == "alice"

    await store.mark_scanned(10, 1)
    indexed = await store.list_indexed_media_ids()
    assert indexed == {10}

    deleted = await store.delete_faces_for_media(10)
    assert deleted == 1
    assert await store.list_indexed_media_ids() == set()

    await store.close()


async def test_face_store_dim_check(tmp_path: Path) -> None:
    store = FaceIndexStore(db_path=tmp_path / "face.db", dim=4)
    await store.initialize()
    with pytest.raises(ValueError):
        await store.add_face(
            media_id=1,
            sha256="x",
            bbox=(0.0, 0.0, 1.0, 1.0),
            kps=[],
            det_score=0.5,
            embedding=[1.0, 0.0, 0.0],
        )
    await store.close()


async def test_assign_creates_and_groups(tmp_path: Path) -> None:
    store = FaceIndexStore(db_path=tmp_path / "face.db", dim=3)
    await store.initialize()
    clusterer = FaceClusterer(store, assign_threshold=0.6)

    a1 = _normalize([1.0, 0.0, 0.0])
    a2 = _normalize([0.95, 0.05, 0.0])
    b1 = _normalize([0.0, 1.0, 0.0])

    fa1 = await store.add_face(
        media_id=1,
        sha256="s1",
        bbox=(0, 0, 10, 10),
        kps=[],
        det_score=0.99,
        embedding=a1,
    )
    res1 = await clusterer.assign_face(a1, face_id=fa1)
    await store.reassign_face(fa1, res1.person_id)
    assert res1.created is True

    fa2 = await store.add_face(
        media_id=2,
        sha256="s2",
        bbox=(0, 0, 10, 10),
        kps=[],
        det_score=0.95,
        embedding=a2,
    )
    res2 = await clusterer.assign_face(a2, face_id=fa2)
    await store.reassign_face(fa2, res2.person_id)
    assert res2.created is False
    assert res2.person_id == res1.person_id

    fb1 = await store.add_face(
        media_id=3,
        sha256="s3",
        bbox=(0, 0, 10, 10),
        kps=[],
        det_score=0.95,
        embedding=b1,
    )
    res3 = await clusterer.assign_face(b1, face_id=fb1)
    await store.reassign_face(fb1, res3.person_id)
    assert res3.created is True
    assert res3.person_id != res1.person_id

    persons = await store.list_persons()
    assert len(persons) == 2
    assert sum(p.face_count for p in persons) == 3

    await store.close()


async def test_merge_persons(tmp_path: Path) -> None:
    store = FaceIndexStore(db_path=tmp_path / "face.db", dim=3)
    await store.initialize()
    clusterer = FaceClusterer(store, assign_threshold=0.99)

    embeddings = [
        _normalize([1.0, 0.0, 0.0]),
        _normalize([0.0, 1.0, 0.0]),
        _normalize([0.0, 0.0, 1.0]),
    ]
    person_ids: list[int] = []
    face_ids: list[int] = []
    for i, emb in enumerate(embeddings):
        fid = await store.add_face(
            media_id=i + 1,
            sha256=f"s{i}",
            bbox=(0, 0, 1, 1),
            kps=[],
            det_score=0.9,
            embedding=emb,
        )
        face_ids.append(fid)
        result = await clusterer.assign_face(emb, face_id=fid)
        await store.reassign_face(fid, result.person_id)
        person_ids.append(result.person_id)

    assert len(set(person_ids)) == 3

    moved = await clusterer.merge_persons([person_ids[1], person_ids[2]], person_ids[0])
    assert moved == 2

    persons = await store.list_persons()
    assert len(persons) == 1
    target = persons[0]
    assert target.face_count == 3

    faces_in_target = await store.list_faces_by_person(target.id)
    assert {f.id for f in faces_in_target} == set(face_ids)

    await store.close()


async def test_split_persons(tmp_path: Path) -> None:
    store = FaceIndexStore(db_path=tmp_path / "face.db", dim=3)
    await store.initialize()
    clusterer = FaceClusterer(store, assign_threshold=0.0)  # 强制并入

    similar = [
        _normalize([1.0, 0.0, 0.0]),
        _normalize([0.99, 0.01, 0.0]),
        _normalize([0.98, 0.02, 0.0]),
    ]
    face_ids: list[int] = []
    for i, emb in enumerate(similar):
        fid = await store.add_face(
            media_id=i + 1,
            sha256=f"s{i}",
            bbox=(0, 0, 1, 1),
            kps=[],
            det_score=0.9,
            embedding=emb,
        )
        face_ids.append(fid)
        res = await clusterer.assign_face(emb, face_id=fid)
        await store.reassign_face(fid, res.person_id)

    persons = await store.list_persons()
    assert len(persons) == 1
    src_id = persons[0].id

    new_id = await clusterer.split_persons(src_id, face_ids[:1], new_name="split")
    assert new_id is not None and new_id != src_id

    persons_after = await store.list_persons()
    assert len(persons_after) == 2
    counts = {p.id: p.face_count for p in persons_after}
    assert counts[src_id] == 2
    assert counts[new_id] == 1

    await store.close()


async def test_recluster_uses_dbscan_labels(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = FaceIndexStore(db_path=tmp_path / "face.db", dim=3)
    await store.initialize()
    clusterer = FaceClusterer(store, assign_threshold=0.0)

    embeddings = [
        _normalize([1.0, 0.0, 0.0]),
        _normalize([0.99, 0.0, 0.0]),
        _normalize([0.0, 1.0, 0.0]),
        _normalize([0.0, 0.99, 0.0]),
        _normalize([0.5, 0.5, 0.5]),
    ]
    for i, emb in enumerate(embeddings):
        fid = await store.add_face(
            media_id=i + 1,
            sha256=f"s{i}",
            bbox=(0, 0, 1, 1),
            kps=[],
            det_score=0.5,
            embedding=emb,
        )
        res = await clusterer.assign_face(emb, face_id=fid)
        await store.reassign_face(fid, res.person_id)

    fixed_labels = [0, 0, 1, 1, -1]

    def fake_dbscan(self, embeddings, *, eps, min_samples):
        assert len(embeddings) == 5
        return list(fixed_labels)

    monkeypatch.setattr(FaceClusterer, "_run_dbscan", fake_dbscan)

    report = await clusterer.recluster_dbscan()
    assert report.persons_after >= 3  # 两个簇 + 至少一个噪声生成的角色

    persons = await store.list_persons()
    cluster_counts = sorted(p.face_count for p in persons)
    # 噪声（label=-1）单独成簇 → face_count==1，两个真实簇 face_count==2
    assert cluster_counts == [1, 2, 2]

    await store.close()
