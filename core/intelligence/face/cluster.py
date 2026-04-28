"""人脸聚类服务（在线增量分配 + 周期性 DBSCAN 重聚类）。

策略：
- 在线分配：新检测到的人脸与所有现存角色的质心做余弦比较，最大相似度
  超过阈值 :data:`DEFAULT_ASSIGN_THRESHOLD` 时归入对应角色，否则新建角色；
- 周期 / 手动 DBSCAN：把所有人脸嵌入聚类到合理的簇内，超大簇拆分、
  小簇合并，达到「相似人脸合并」的目标；
- 合并 / 拆分 / 重命名：由 service 层封装在 :class:`FaceClusterer.merge_persons`
  / :meth:`split_persons` / :meth:`rename_person` 提供 UI 调用。

为了让单元测试不依赖 ``scikit-learn`` / ``numpy``，类内部所有矩阵运算都被
封装到 :meth:`_run_dbscan`，调用方在测试时可 monkeypatch 该方法返回伪结果。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Iterable

from .index import FaceIndexStore, PersonRecord


logger = logging.getLogger(__name__)


DEFAULT_ASSIGN_THRESHOLD = 0.5
"""ArcFace 余弦相似度 ≥ 该阈值认为同一人，可按需调到 0.45~0.6。"""

DEFAULT_DBSCAN_EPS = 0.5
"""DBSCAN 余弦距离 eps（注意：``1 - cosine_similarity``）。"""

DEFAULT_DBSCAN_MIN_SAMPLES = 2


@dataclass(slots=True)
class AssignmentResult:
    """单次在线分配的结果。"""

    person_id: int
    score: float
    created: bool


@dataclass(slots=True)
class ReclusterReport:
    persons_before: int
    persons_after: int
    merged: int
    created: int
    moved_faces: int


class FaceClusterer:
    """人脸聚类服务。

    Args:
        store: 持久化层。
        assign_threshold: 在线分配阈值（余弦相似度）。
    """

    def __init__(
        self,
        store: FaceIndexStore,
        *,
        assign_threshold: float = DEFAULT_ASSIGN_THRESHOLD,
    ) -> None:
        self._store = store
        self._assign_threshold = float(assign_threshold)
        self._lock = asyncio.Lock()

    @property
    def assign_threshold(self) -> float:
        return self._assign_threshold

    def update_threshold(self, value: float) -> None:
        self._assign_threshold = float(value)

    # ----- 在线分配 -----

    async def assign_face(
        self,
        embedding: list[float],
        *,
        face_id: int | None = None,
    ) -> AssignmentResult:
        """根据现有 person 质心找到最佳归属，必要时新建。

        ``face_id`` 仅在新建 person 时被用作 ``sample_face_id``。
        """
        async with self._lock:
            persons = await self._store.list_persons()
            best_id: int | None = None
            best_score = -1.0
            for person in persons:
                if not person.centroid:
                    continue
                score = _cosine(embedding, person.centroid)
                if score > best_score:
                    best_score = score
                    best_id = person.id

            if best_id is not None and best_score >= self._assign_threshold:
                # 增量更新质心：centroid' = (centroid * n + emb) / (n + 1)
                target = next(p for p in persons if p.id == best_id)
                new_centroid = _running_mean(target.centroid, target.face_count, embedding)
                await self._store.update_person_centroid(
                    best_id, new_centroid, face_count=target.face_count + 1
                )
                return AssignmentResult(
                    person_id=best_id, score=best_score, created=False
                )

            new_id = await self._store.create_person(
                centroid=list(embedding),
                sample_face_id=face_id,
            )
            await self._store.increment_face_count(new_id, 1)
            return AssignmentResult(person_id=new_id, score=1.0, created=True)

    # ----- 合并 / 拆分 / 重命名 -----

    async def merge_persons(self, src_ids: Iterable[int], target_id: int) -> int:
        """把多个角色合并到 ``target_id``，返回受影响的 face 数量。"""
        sources = [int(v) for v in src_ids if int(v) != int(target_id)]
        if not sources:
            return 0
        moved_total = 0
        async with self._lock:
            for src in sources:
                faces = await self._store.list_faces_by_person(src, limit=10**9)
                if faces:
                    moved = await self._store.reassign_faces(
                        [f.id for f in faces], int(target_id)
                    )
                    moved_total += moved
                await self._store.delete_person(src, reassign_to=int(target_id))
            await self._refresh_centroid_unlocked(int(target_id))
            await self._store.recount_persons()
        return moved_total

    async def split_persons(
        self, source_id: int, face_ids: Iterable[int], *, new_name: str = ""
    ) -> int | None:
        """把 ``face_ids`` 从 ``source_id`` 中分离成新角色，返回新 person id。"""
        ids = [int(v) for v in face_ids]
        if not ids:
            return None
        async with self._lock:
            new_id = await self._store.create_person(name=new_name)
            await self._store.reassign_faces(ids, new_id)
            await self._refresh_centroid_unlocked(new_id)
            await self._refresh_centroid_unlocked(int(source_id))
            await self._store.recount_persons()
            return new_id

    async def rename_person(
        self, person_id: int, name: str, *, sample_face_id: int | None = None
    ) -> None:
        await self._store.update_person(
            int(person_id), name=name, sample_face_id=sample_face_id
        )

    # ----- DBSCAN 重聚类 -----

    async def recluster_dbscan(
        self,
        *,
        eps: float = DEFAULT_DBSCAN_EPS,
        min_samples: int = DEFAULT_DBSCAN_MIN_SAMPLES,
    ) -> ReclusterReport:
        embeddings = await self._store.list_all_embeddings()
        if not embeddings:
            return ReclusterReport(0, 0, 0, 0, 0)

        labels = self._run_dbscan(
            [emb for _, _, emb in embeddings], eps=eps, min_samples=min_samples
        )

        async with self._lock:
            persons_before = await self._store.count_persons()
            created = 0
            moved = 0
            cluster_to_person: dict[int, int] = {}
            for (face_id, _, embedding), label in zip(embeddings, labels):
                if label < 0:
                    # 噪声：分到独立角色
                    new_pid = await self._store.create_person(centroid=list(embedding))
                    await self._store.reassign_face(face_id, new_pid)
                    created += 1
                    moved += 1
                    continue
                pid = cluster_to_person.get(label)
                if pid is None:
                    pid = await self._store.create_person(
                        centroid=list(embedding), sample_face_id=face_id
                    )
                    cluster_to_person[label] = pid
                    created += 1
                await self._store.reassign_face(face_id, pid)
                moved += 1

            # 删除不再有 face 的旧 person
            for old_person in await self._store.list_persons():
                if old_person.face_count == 0 and old_person.id not in cluster_to_person.values():
                    # 重新计数后再决定，先跳过；下面 recount 后统一清理
                    pass
            await self._store.recount_persons()
            for person in await self._store.list_persons():
                if person.face_count == 0:
                    await self._store.delete_person(person.id)
                    continue
                await self._refresh_centroid_unlocked(person.id)
            persons_after = await self._store.count_persons()

        return ReclusterReport(
            persons_before=persons_before,
            persons_after=persons_after,
            merged=max(0, persons_before - persons_after),
            created=created,
            moved_faces=moved,
        )

    def _run_dbscan(
        self,
        embeddings: list[list[float]],
        *,
        eps: float,
        min_samples: int,
    ) -> list[int]:
        """调用 sklearn DBSCAN；可被测试 monkeypatch。"""
        try:
            import numpy as np
            from sklearn.cluster import DBSCAN
        except ImportError as exc:  # pragma: no cover
            logger.warning("sklearn 缺失，跳过 DBSCAN 重聚类: %s", exc)
            return [-1] * len(embeddings)

        if not embeddings:
            return []
        arr = np.asarray(embeddings, dtype=np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        arr = arr / norms
        clusterer = DBSCAN(eps=float(eps), min_samples=int(min_samples), metric="cosine")
        labels = clusterer.fit_predict(arr)
        return [int(v) for v in labels]

    # ----- 工具方法 -----

    async def _refresh_centroid_unlocked(self, person_id: int) -> None:
        faces = await self._store.list_faces_by_person(int(person_id), limit=10**9)
        if not faces:
            await self._store.delete_person(int(person_id))
            return
        dim = len(faces[0].embedding)
        if dim == 0:
            return
        sums = [0.0] * dim
        valid = 0
        for face in faces:
            if len(face.embedding) != dim:
                continue
            for i, v in enumerate(face.embedding):
                sums[i] += v
            valid += 1
        if valid == 0:
            return
        centroid = [v / valid for v in sums]
        normed = _l2(centroid)
        await self._store.update_person_centroid(
            int(person_id), normed, face_count=valid
        )

    async def find_persons_for_query(
        self, embedding: list[float], *, top_k: int = 5
    ) -> list[tuple[PersonRecord, float]]:
        persons = await self._store.list_persons()
        scored: list[tuple[PersonRecord, float]] = []
        for person in persons:
            if not person.centroid:
                continue
            scored.append((person, _cosine(embedding, person.centroid)))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[: max(1, int(top_k))]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))


def _running_mean(centroid: list[float], n: int, new_vec: list[float]) -> list[float]:
    if not centroid:
        return _l2(list(new_vec))
    if len(centroid) != len(new_vec):
        return centroid
    n_safe = max(1, int(n))
    merged = [
        (c * n_safe + v) / (n_safe + 1) for c, v in zip(centroid, new_vec)
    ]
    return _l2(merged)


def _l2(vec: list[float]) -> list[float]:
    norm = 0.0
    for v in vec:
        norm += v * v
    norm = norm ** 0.5
    if norm <= 0:
        return list(vec)
    return [v / norm for v in vec]
