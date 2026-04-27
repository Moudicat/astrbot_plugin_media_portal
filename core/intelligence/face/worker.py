"""人脸检测 / 嵌入后台 Worker。

职责：
- 拉取媒体库图片差集；
- 调用 :class:`FaceEngine.detect` 完成检测 + 嵌入；
- 通过 :class:`FaceClusterer` 把每个人脸在线分配到角色；
- 可选生成人脸缩略图（112×112，保存为 ``thumbs/<face_id>.jpg``）。

为了兼容缺少 ``Pillow`` / ``numpy`` 的环境，缩略图功能在 import 错误时静默跳过。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Iterable

from .cluster import FaceClusterer
from .engine import FaceDetection, FaceEngine
from .index import FaceIndexStore


logger = logging.getLogger(__name__)


IterImageRecords = Callable[[], Awaitable[Iterable[tuple[int, str, str]]]]


@dataclass(slots=True)
class FaceWorkerStats:
    media_processed: int = 0
    faces_indexed: int = 0
    skipped: int = 0
    failed: int = 0
    last_run_at: float = 0.0
    last_error: str = ""
    failed_media_ids: set[int] = field(default_factory=set)


class FaceIndexWorker:
    def __init__(
        self,
        store: FaceIndexStore,
        engine: FaceEngine,
        clusterer: FaceClusterer,
        *,
        iter_image_records: IterImageRecords,
        thumb_dir: Path,
        model_version: str = "",
        max_retries: int = 1,
    ) -> None:
        self._store = store
        self._engine = engine
        self._clusterer = clusterer
        self._iter_records = iter_image_records
        self._thumb_dir = Path(thumb_dir)
        self._thumb_dir.mkdir(parents=True, exist_ok=True)
        self._model_version = model_version
        self._max_retries = max(0, int(max_retries))
        self._failed_media_ids: set[int] = set()
        self._stats = FaceWorkerStats(failed_media_ids=self._failed_media_ids)
        self._stop_event = asyncio.Event()
        self._running_lock = asyncio.Lock()

    @property
    def stats(self) -> FaceWorkerStats:
        return self._stats

    async def run_full_scan(self) -> FaceWorkerStats:
        async with self._running_lock:
            self._stats = FaceWorkerStats(failed_media_ids=self._failed_media_ids)
            try:
                records = list(await self._iter_records())
            except Exception as exc:
                logger.exception("人脸 worker 拉取媒体记录失败")
                self._stats.last_error = str(exc)
                return self._stats

            indexed = await self._store.list_indexed_media_ids()
            pending = [
                rec
                for rec in records
                if rec[0] not in indexed
                and rec[0] not in self._failed_media_ids
            ]
            self._stats.skipped = len(records) - len(pending)
            for media_id, sha256, abs_path in pending:
                if self._stop_event.is_set():
                    break
                ok = await self._process_one(media_id, sha256, abs_path)
                if ok:
                    self._stats.media_processed += 1
                else:
                    self._stats.failed += 1
                await asyncio.sleep(0)
            self._stats.last_run_at = time.time()
            return self._stats

    async def _process_one(
        self, media_id: int, sha256: str, abs_path: str
    ) -> bool:
        attempts = self._max_retries + 1
        last_exc: Exception | None = None
        for attempt in range(attempts):
            if self._stop_event.is_set():
                return False
            try:
                detections = await self._engine.detect(abs_path)
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "人脸检测失败 media_id=%s attempt=%s err=%s",
                    media_id,
                    attempt + 1,
                    exc,
                )
                continue
            try:
                await self._store_detections(media_id, sha256, abs_path, detections)
                return True
            except Exception as exc:
                last_exc = exc
                logger.warning("人脸入库失败 media_id=%s err=%s", media_id, exc)
        if last_exc is not None:
            self._stats.last_error = str(last_exc)
        self._failed_media_ids.add(media_id)
        return False

    async def _store_detections(
        self,
        media_id: int,
        sha256: str,
        abs_path: str,
        detections: list[FaceDetection],
    ) -> None:
        valid: list[FaceDetection] = [d for d in detections if d.embedding]
        for det in valid:
            face_id = await self._store.add_face(
                media_id=media_id,
                sha256=sha256,
                bbox=det.bbox,
                kps=det.kps,
                det_score=det.det_score,
                embedding=det.embedding,
                model_version=self._model_version,
            )
            assignment = await self._clusterer.assign_face(
                det.embedding, face_id=face_id
            )
            await self._store.reassign_face(face_id, assignment.person_id)
            thumb_rel = await self._save_thumb(face_id, abs_path, det)
            if thumb_rel:
                await self._store.set_face_thumb(face_id, thumb_rel)
            self._stats.faces_indexed += 1
        await self._store.mark_scanned(media_id, len(valid))

    async def _save_thumb(
        self, face_id: int, abs_path: str, det: FaceDetection
    ) -> str:
        thumb_path = self._thumb_dir / f"{face_id}.jpg"
        try:
            await asyncio.to_thread(
                _crop_and_save_thumb, Path(abs_path), det.bbox, thumb_path
            )
            return str(thumb_path)
        except Exception as exc:  # pragma: no cover
            logger.warning("人脸缩略图保存失败 face_id=%s err=%s", face_id, exc)
            return ""

    def stop(self) -> None:
        self._stop_event.set()

    def reset_stop(self) -> None:
        self._stop_event = asyncio.Event()

    def reset_failed(self, *, media_ids: Iterable[int] | None = None) -> int:
        """清除「永久失败」名单，返回被清除的数量。

        :param media_ids: 仅清除指定 media_id；为 ``None`` 时清空全部。
        """
        if media_ids is None:
            count = len(self._failed_media_ids)
            self._failed_media_ids.clear()
            return count
        targets = {int(mid) for mid in media_ids}
        before = len(self._failed_media_ids)
        self._failed_media_ids -= targets
        return before - len(self._failed_media_ids)

    async def cleanup_orphans(self, valid_media_ids: Iterable[int]) -> int:
        valid = {int(mid) for mid in valid_media_ids}
        existing = await self._store.list_indexed_media_ids()
        removed = 0
        for media_id in existing - valid:
            removed += await self._store.delete_faces_for_media(media_id)
        return removed


def _crop_and_save_thumb(
    src_path: Path,
    bbox: tuple[float, float, float, float],
    target_path: Path,
    *,
    size: tuple[int, int] = (112, 112),
) -> None:
    try:
        from PIL import Image, ImageOps
    except ImportError:  # pragma: no cover
        return

    if not src_path.is_file():
        return
    img = Image.open(src_path)
    img = ImageOps.exif_transpose(img).convert("RGB")
    x1, y1, x2, y2 = bbox
    width, height = img.size
    x1 = max(0, int(x1))
    y1 = max(0, int(y1))
    x2 = min(width, int(x2))
    y2 = min(height, int(y2))
    if x2 - x1 < 4 or y2 - y1 < 4:
        return
    cropped = img.crop((x1, y1, x2, y2)).resize(size, Image.BICUBIC)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(target_path, format="JPEG", quality=85)
