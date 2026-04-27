"""CLIP 后台索引 Worker。

职责：
- 比对媒体库中的图片记录与 ClipIndexStore 已索引集合，对差集执行 ``encode_image``；
- 支持手动触发增量、删除、全量重建；
- 失败任务会写入 :data:`failed_media_ids`，避免在同一次扫描中无限重试；
- 完全协程化，使用 :class:`asyncio.Queue` + 单 worker 循环以避免对 ONNX 同时多实例调用。

为便于测试，Worker 不直接持有 :class:`MediaManager` 引用，而是通过两个回调函数：

- ``iter_image_records()``：返回 ``Iterable[tuple[int, str, str]]``，
  即 ``(media_id, sha256, abs_path)``；只需要图片记录。
- ``encode_image(path) -> list[float]``：通常绑定到 ``ClipEngine.encode_image``。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Iterable

from .index import ClipIndexStore


logger = logging.getLogger(__name__)


IterImageRecords = Callable[[], Awaitable[Iterable[tuple[int, str, str]]]]
EncodeImage = Callable[[str], Awaitable[list[float]]]


@dataclass(slots=True)
class WorkerStats:
    indexed: int = 0
    skipped: int = 0
    failed: int = 0
    last_run_at: float = 0.0
    last_error: str = ""
    failed_media_ids: set[int] = field(default_factory=set)


class ClipIndexWorker:
    def __init__(
        self,
        store: ClipIndexStore,
        *,
        iter_image_records: IterImageRecords,
        encode_image: EncodeImage,
        model_version: str = "",
        batch_size: int = 8,
        max_retries: int = 1,
    ) -> None:
        self._store = store
        self._iter_records = iter_image_records
        self._encode_image = encode_image
        self._model_version = model_version
        self._batch_size = max(1, int(batch_size))
        self._max_retries = max(0, int(max_retries))
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._stats = WorkerStats()
        self._running_lock = asyncio.Lock()

    @property
    def stats(self) -> WorkerStats:
        return self._stats

    async def run_full_scan(self) -> WorkerStats:
        """同步执行一次全量扫描；调用方需自行串行化（已通过 ``_running_lock`` 保护）。"""
        async with self._running_lock:
            self._stats = WorkerStats()
            try:
                records = list(await self._iter_records())
            except Exception as exc:
                logger.exception("CLIP worker 拉取媒体记录失败")
                self._stats.last_error = str(exc)
                return self._stats

            already_indexed = await self._store.list_media_ids()
            pending = [
                rec
                for rec in records
                if rec[0] not in already_indexed
                and rec[0] not in self._stats.failed_media_ids
            ]
            for media_id, sha256, abs_path in pending:
                if self._stop_event.is_set():
                    break
                ok = await self._encode_with_retry(media_id, sha256, abs_path)
                if ok:
                    self._stats.indexed += 1
                else:
                    self._stats.failed += 1
                # 让出事件循环，避免长任务阻塞
                await asyncio.sleep(0)

            self._stats.skipped = len(records) - len(pending) - self._stats.failed
            self._stats.last_run_at = time.time()
            return self._stats

    async def _encode_with_retry(
        self, media_id: int, sha256: str, abs_path: str
    ) -> bool:
        attempts = self._max_retries + 1
        last_exc: Exception | None = None
        for attempt in range(attempts):
            if self._stop_event.is_set():
                return False
            try:
                vector = await self._encode_image(abs_path)
                await self._store.upsert(
                    media_id, sha256, vector, model_version=self._model_version
                )
                return True
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "CLIP 编码失败 media_id=%s attempt=%s err=%s",
                    media_id,
                    attempt + 1,
                    exc,
                )
        if last_exc is not None:
            self._stats.last_error = str(last_exc)
        self._stats.failed_media_ids.add(media_id)
        return False

    def stop(self) -> None:
        self._stop_event.set()

    def reset_stop(self) -> None:
        self._stop_event = asyncio.Event()

    async def cleanup_orphans(self, valid_media_ids: Iterable[int]) -> int:
        """删除 ``valid_media_ids`` 范围之外的索引行（媒体被回收时调用）。"""
        valid = {int(mid) for mid in valid_media_ids}
        existing = await self._store.list_media_ids()
        to_remove = existing - valid
        if not to_remove:
            return 0
        return await self._store.delete_many(to_remove)
