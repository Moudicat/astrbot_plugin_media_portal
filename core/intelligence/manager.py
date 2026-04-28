"""智能能力总控管理器。

职责：
- 持有所有 :class:`ModelSpec` 注册表；
- 暴露状态查询、下载、取消、删除接口；
- 控制并发下载数；
- 写出 ``.intelligence/state.json`` 用于错误信息持久化（让 UI 在重启后仍能展示上次失败原因）。

本模块**不**强依赖任何 ML SDK，CLIP / 人脸推理引擎将在后续 milestone 通过
:meth:`register_engine` 挂载，再通过 :meth:`get_engine` 取出。
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Protocol, runtime_checkable

from astrbot.api import logger

from .config_state import ModelStatus
from .downloader import DownloadEvent, ModelDownloader
from .models import ModelSpec
from .registry import CLIP_MODEL_KEY, DEFAULT_MODELS, FACE_MODEL_KEY


_STATE_FILENAME = "state.json"
_SETTINGS_FILENAME = "settings.json"

# 通过 ``find_missing`` 探测「已就绪但仍缺 pip 依赖」的结果缓存时长（秒）。
# 设得太短会让设置页频繁触发依赖检测；设得太长则用户手动 pip install 后看不到效果。
_MISSING_DEPS_TTL_SECONDS = 30.0


# 模型下载阶段，仅用于让前端展示更精准的进度文本。
DOWNLOAD_PHASE_IDLE = ""
DOWNLOAD_PHASE_CHECKING_DEPS = "checking_deps"
DOWNLOAD_PHASE_INSTALLING_DEPS = "installing_deps"
DOWNLOAD_PHASE_DOWNLOADING_FILES = "downloading_files"


@runtime_checkable
class DependencyInstaller(Protocol):
    """模型可选依赖安装钩子。

    - :meth:`find_missing` 同步返回当前缺失的 pip 规格列表（已安装的会被剔除）。
    - :meth:`install` 异步安装传入的规格集合（通常一次 pip 调用完成）。

    注入方式由插件入口 ``main.py`` 提供（接 AstrBot 内置 ``pip_installer``）；
    在测试 / 调试场景可以传入 ``None`` 或自定义 stub，避免实际触发 pip。
    """

    def find_missing(self, specs: tuple[str, ...]) -> list[str]:  # noqa: D401 - protocol
        ...

    async def install(self, specs: tuple[str, ...]) -> None:  # noqa: D401 - protocol
        ...


@dataclass(slots=True)
class _ModelRuntime:
    """每个模型在内存中的运行时状态。"""

    status: ModelStatus = ModelStatus.not_downloaded
    phase: str = DOWNLOAD_PHASE_IDLE
    progress_bytes: int = 0
    total_bytes: int | None = None
    progress_files: int = 0
    total_files: int = 0
    current_file: str = ""
    last_error: str = ""
    last_event_at: float = 0.0
    task: asyncio.Task[Any] | None = None
    deps_total: int = 0
    deps_installed: int = 0
    deps_pending: list[str] = field(default_factory=list)
    missing_deps_cache: list[str] = field(default_factory=list)
    missing_deps_checked_at: float = 0.0


@dataclass(slots=True)
class ModelSnapshot:
    """对外暴露的模型快照（可被 JSON 化）。"""

    key: str
    capability: str
    display_name: str
    description: str
    homepage: str
    license: str
    status: ModelStatus
    phase: str
    files_total: int
    files_complete: int
    bytes_total: int | None
    bytes_complete: int
    extra_requirements: list[str]
    last_error: str
    current_file: str
    progress_bytes: int
    progress_total: int | None
    files_done: int
    last_event_at: float
    target_dir: str
    deps_total: int
    deps_installed: int
    deps_pending: list[str]
    missing_deps: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "capability": self.capability,
            "display_name": self.display_name,
            "description": self.description,
            "homepage": self.homepage,
            "license": self.license,
            "status": self.status.value,
            "phase": self.phase,
            "files_total": self.files_total,
            "files_complete": self.files_complete,
            "bytes_total": self.bytes_total,
            "bytes_complete": self.bytes_complete,
            "extra_requirements": list(self.extra_requirements),
            "last_error": self.last_error,
            "current_file": self.current_file,
            "progress_bytes": self.progress_bytes,
            "progress_total": self.progress_total,
            "files_done": self.files_done,
            "last_event_at": self.last_event_at,
            "target_dir": self.target_dir,
            "deps_total": self.deps_total,
            "deps_installed": self.deps_installed,
            "deps_pending": list(self.deps_pending),
            "missing_deps": list(self.missing_deps),
        }


def attach_auto_scan_post_save(
    *,
    media_manager: Any,
    intelligence_manager: "IntelligenceManager | None",
) -> None:
    """把"上传/恢复媒体后自动触发 CLIP / 人脸扫描"的钩子挂到 ``media_manager``。

    这段逻辑原本只写在插件主入口 ``main.py`` 里，导致 ``scripts/debug_webui.py``
    单跑时上传图片不会触发任何后台扫描。抽成模块级函数后可以同时在两处复用。

    - 仅对图像类型 (``record.kind == "image"``) 生效；
    - ``intelligence_manager`` 为 ``None`` 或总开关关闭时静默跳过；
    - 每个子能力（CLIP / 人脸）独立 try-except，互不影响；
    - 由 :class:`IntelligenceManager` 内部的 rescan-pending 队列保证：哪怕扫描任务正
      在跑，也不会丢掉新上传的文件——会在当前扫描结束后自动再补一轮。
    """

    async def _on_post_save(record: Any, action: str) -> None:
        if action not in {"created", "restored"}:
            return
        kind = getattr(record, "kind", "") or ""
        if str(kind).lower() != "image":
            return
        if intelligence_manager is None or not intelligence_manager.feature_enabled:
            return

        async def _iter_image_records() -> Any:
            getter = getattr(media_manager, "list_image_records_minimal", None)
            if not callable(getter):
                return []
            try:
                return await getter()
            except Exception:
                return []

        try:
            if intelligence_manager.clip_enabled:
                await intelligence_manager.trigger_clip_scan(
                    iter_image_records=_iter_image_records
                )
        except Exception as exc:
            logger.debug("自动 CLIP 索引失败: %s", exc)
        try:
            if intelligence_manager.face_enabled:
                await intelligence_manager.trigger_face_scan(
                    iter_image_records=_iter_image_records
                )
        except Exception as exc:
            logger.debug("自动人脸扫描失败: %s", exc)

    register = getattr(media_manager, "register_post_save_callback", None)
    if callable(register):
        register(_on_post_save)


class IntelligenceManager:
    """模型管理器。

    Args:
        plugin_data_dir: 插件数据根目录。
        feature_enabled: 智能能力总开关。
        clip_enabled: CLIP 子能力开关（仅决定 ``CLIP`` 模型是否在 UI 中标注为「已启用」）。
        face_enabled: 人脸子能力开关。
        hf_mirror_url: HuggingFace 镜像；空表示直连。
        max_concurrent_downloads: 并发下载数（1~3）。
        models: 自定义模型列表，缺省使用 :data:`DEFAULT_MODELS`。
    """

    def __init__(
        self,
        *,
        plugin_data_dir: Path,
        feature_enabled: bool = False,
        clip_enabled: bool = False,
        face_enabled: bool = False,
        hf_mirror_url: str = "",
        max_concurrent_downloads: int = 1,
        models: Iterable[ModelSpec] | None = None,
        face_min_det_score: float = 0.6,
        face_min_face_size: int = 60,
        face_min_blur_var: float = 60.0,
        dependency_installer: DependencyInstaller | None = None,
    ) -> None:
        self._plugin_data_dir = Path(plugin_data_dir)
        self._intelligence_dir = (self._plugin_data_dir / "intelligence").resolve()
        self._models_dir = (self._intelligence_dir / "models").resolve()
        self._intelligence_dir.mkdir(parents=True, exist_ok=True)
        self._models_dir.mkdir(parents=True, exist_ok=True)

        self._feature_enabled = bool(feature_enabled)
        self._clip_enabled = bool(clip_enabled)
        self._face_enabled = bool(face_enabled)
        self._face_min_det_score = max(0.0, min(1.0, float(face_min_det_score)))
        self._face_min_face_size = max(0, int(face_min_face_size))
        self._face_min_blur_var = max(0.0, float(face_min_blur_var))

        self._models: dict[str, ModelSpec] = {
            spec.key: spec for spec in (models or DEFAULT_MODELS)
        }
        self._runtimes: dict[str, _ModelRuntime] = {
            key: _ModelRuntime(total_files=len(spec.files))
            for key, spec in self._models.items()
        }
        self._lock = asyncio.Lock()
        self._max_concurrent_downloads = max(1, min(3, int(max_concurrent_downloads)))
        self._download_sema = asyncio.Semaphore(self._max_concurrent_downloads)
        self._engines: dict[str, Any] = {}
        self._downloader = ModelDownloader(
            root_dir=self._models_dir,
            hf_mirror_url=hf_mirror_url,
        )
        self._dependency_installer = dependency_installer

        self._clip_index_db = (self._intelligence_dir / "clip_index.db").resolve()
        self._clip_store: Any = None  # ClipIndexStore，懒初始化
        self._clip_worker: Any = None  # ClipIndexWorker
        self._clip_scan_task: asyncio.Task[Any] | None = None
        # 当扫描进行中又被 trigger（典型场景：上传连发），先标记此处，
        # 等当前扫描结束后再自动补一轮，避免新上传的文件被漏掉。
        self._clip_rescan_pending: bool = False
        self._clip_rescan_iter: Any = None

        self._face_index_db = (self._intelligence_dir / "face_index.db").resolve()
        self._face_thumb_dir = (self._intelligence_dir / "face_thumbs").resolve()
        self._face_thumb_dir.mkdir(parents=True, exist_ok=True)
        self._face_store: Any = None  # FaceIndexStore，懒初始化
        self._face_clusterer: Any = None
        self._face_worker: Any = None
        self._face_scan_task: asyncio.Task[Any] | None = None
        self._face_rescan_pending: bool = False
        self._face_rescan_iter: Any = None

        self._load_settings_file()
        self._load_state_file()
        self._refresh_disk_status_sync()

    # ----- 公共属性 -----

    @property
    def feature_enabled(self) -> bool:
        return self._feature_enabled

    @property
    def clip_enabled(self) -> bool:
        return self._feature_enabled and self._clip_enabled

    @property
    def face_enabled(self) -> bool:
        return self._feature_enabled and self._face_enabled

    @property
    def face_quality_thresholds(self) -> dict[str, float]:
        """对外暴露的人脸质量阈值快照。"""
        return {
            "min_det_score": float(self._face_min_det_score),
            "min_face_size": float(self._face_min_face_size),
            "min_blur_var": float(self._face_min_blur_var),
        }

    @property
    def hf_mirror_url(self) -> str:
        return self._downloader.hf_mirror_url

    @property
    def models_dir(self) -> Path:
        return self._models_dir

    @property
    def downloader(self) -> ModelDownloader:
        return self._downloader

    def list_specs(self) -> tuple[ModelSpec, ...]:
        return tuple(self._models.values())

    def get_spec(self, model_key: str) -> ModelSpec | None:
        return self._models.get(model_key)

    # ----- 引擎挂载 -----

    def register_engine(self, name: str, engine: Any) -> None:
        """挂载一个推理引擎实例（CLIP / FaceEngine 等）。"""
        self._engines[name] = engine

    def get_engine(self, name: str) -> Any | None:
        return self._engines.get(name)

    def has_engine(self, name: str) -> bool:
        return name in self._engines

    async def get_clip_engine(self) -> Any | None:
        """返回懒加载的 :class:`ClipEngine` 实例。

        - 总开关 / clip 子开关关闭 → ``None``；
        - 模型尚未 ``ready`` → ``None``；
        - 加载失败 → 记录日志并返回 ``None``，让上层降级回字面搜索。
        """
        if not self.clip_enabled:
            return None
        spec = self._models.get(CLIP_MODEL_KEY)
        if spec is None:
            return None
        runtime = self._runtimes.get(CLIP_MODEL_KEY)
        if runtime is None or runtime.status != ModelStatus.ready:
            return None

        engine = self._engines.get("clip")
        if engine is None:
            try:
                from .clip import ClipEngine  # 局部 import 避免在测试环境导入 ORT

                engine = ClipEngine(model_dir=self._downloader.model_dir(spec))
            except Exception:
                logger.exception("初始化 ClipEngine 失败")
                return None
            self._engines["clip"] = engine
        try:
            await engine.load()
        except Exception as exc:
            logger.warning("CLIP 引擎加载失败: %s", exc)
            return None
        return engine

    async def reset_clip_engine(self) -> None:
        """模型重新下载或开关切换时清理旧 session。"""
        engine = self._engines.pop("clip", None)
        if engine is None:
            return
        try:
            await engine.unload()
        except Exception:  # pragma: no cover
            logger.exception("卸载 CLIP 引擎失败")

    async def get_clip_store(self) -> Any | None:
        """返回懒加载的 :class:`ClipIndexStore`。"""
        if not self.clip_enabled:
            return None
        if self._clip_store is None:
            from .clip import ClipIndexStore

            self._clip_store = ClipIndexStore(db_path=self._clip_index_db)
            await self._clip_store.initialize()
        return self._clip_store

    async def close_clip_store(self) -> None:
        if self._clip_store is None:
            return
        try:
            await self._clip_store.close()
        except Exception:  # pragma: no cover
            logger.exception("关闭 CLIP 索引存储失败")
        self._clip_store = None

    async def trigger_clip_scan(
        self,
        *,
        iter_image_records: Any,
        wait: bool = False,
    ) -> bool:
        """触发一次 CLIP 全量扫描。

        - ``iter_image_records`` 必须是异步函数，返回
          ``Iterable[(media_id, sha256, abs_path)]``；
        - 若 CLIP 未就绪 / 任务已在跑则返回 ``False``；
        - ``wait=True`` 时阻塞直到任务完成（仅在测试中使用）。
        """
        engine = await self.get_clip_engine()
        store = await self.get_clip_store()
        if engine is None or store is None:
            return False
        if self._clip_scan_task and not self._clip_scan_task.done():
            # 当前已在扫描，记下还需要再跑一次（典型场景：上传期间又 push 进新文件）。
            self._clip_rescan_pending = True
            self._clip_rescan_iter = iter_image_records
            return False

        from .clip import ClipIndexWorker

        if self._clip_worker is None or getattr(self._clip_worker, "_store", None) is not store:
            self._clip_worker = ClipIndexWorker(
                store=store,
                iter_image_records=iter_image_records,
                encode_image=engine.encode_image,
                model_version=CLIP_MODEL_KEY,
            )
        else:
            # 不同回调时刷新（例如 worker 周期性扫描）
            self._clip_worker._iter_records = iter_image_records  # type: ignore[attr-defined]

        self._clip_rescan_pending = False
        self._clip_rescan_iter = None
        self._clip_scan_task = asyncio.create_task(
            self._run_clip_scan_with_followup(iter_image_records),
            name="clip-index-scan",
        )
        if wait:
            try:
                await self._clip_scan_task
            except Exception:  # pragma: no cover
                logger.exception("CLIP 扫描任务异常")
        return True

    async def _run_clip_scan_with_followup(self, iter_image_records: Any) -> Any:
        """跑一次 ``run_full_scan``；结束时若有 race 上来的请求则继续补跑。"""
        try:
            return await self._clip_worker.run_full_scan()
        finally:
            if self._clip_rescan_pending:
                pending_iter = self._clip_rescan_iter or iter_image_records
                self._clip_rescan_pending = False
                self._clip_rescan_iter = None

                async def _follow_up() -> None:
                    try:
                        await self.trigger_clip_scan(iter_image_records=pending_iter)
                    except Exception:  # pragma: no cover
                        logger.exception("CLIP 跟进扫描失败")

                # 用 create_task 让当前 task 先正常 done，然后再起新任务，
                # 否则在 finally 里直接 await 会让旧 task 一直挂着。
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:  # pragma: no cover
                    loop = asyncio.get_event_loop()
                loop.create_task(_follow_up(), name="clip-index-scan-followup")

    async def search_clip_by_text(
        self, text: str, *, top_k: int = 20
    ) -> list[tuple[int, float]]:
        """文本到图像的语义检索，返回 ``[(media_id, score)]``。"""
        engine = await self.get_clip_engine()
        store = await self.get_clip_store()
        if engine is None or store is None:
            return []
        try:
            vector = await engine.encode_text(text)
        except Exception as exc:
            logger.warning("CLIP encode_text 失败: %s", exc)
            return []
        return await store.search(vector, top_k=top_k)

    async def search_clip_by_image(
        self, image_source: Any, *, top_k: int = 20
    ) -> list[tuple[int, float]]:
        engine = await self.get_clip_engine()
        store = await self.get_clip_store()
        if engine is None or store is None:
            return []
        try:
            vector = await engine.encode_image(image_source)
        except Exception as exc:
            logger.warning("CLIP encode_image 失败: %s", exc)
            return []
        return await store.search(vector, top_k=top_k)

    # ----- 人脸子能力 -----

    async def get_face_engine(self) -> Any | None:
        if not self.face_enabled:
            return None
        spec = self._models.get(FACE_MODEL_KEY)
        if spec is None:
            return None
        runtime = self._runtimes.get(FACE_MODEL_KEY)
        if runtime is None or runtime.status != ModelStatus.ready:
            return None
        engine = self._engines.get("face")
        if engine is None:
            try:
                from .face import FaceEngine

                engine = FaceEngine(model_dir=self._downloader.model_dir(spec))
            except Exception:
                logger.exception("初始化 FaceEngine 失败")
                return None
            self._engines["face"] = engine
        try:
            await engine.load()
        except Exception as exc:
            logger.warning("FaceEngine 加载失败: %s", exc)
            return None
        return engine

    async def reset_face_engine(self) -> None:
        engine = self._engines.pop("face", None)
        if engine is None:
            return
        try:
            await engine.unload()
        except Exception:  # pragma: no cover
            logger.exception("卸载 FaceEngine 失败")

    async def get_face_store(self) -> Any | None:
        if not self.face_enabled:
            return None
        if self._face_store is None:
            from .face import FaceIndexStore

            self._face_store = FaceIndexStore(db_path=self._face_index_db)
            await self._face_store.initialize()
        return self._face_store

    async def get_face_clusterer(self) -> Any | None:
        store = await self.get_face_store()
        if store is None:
            return None
        if self._face_clusterer is None:
            from .face import FaceClusterer

            self._face_clusterer = FaceClusterer(store)
        return self._face_clusterer

    async def close_face_store(self) -> None:
        if self._face_store is None:
            return
        try:
            await self._face_store.close()
        except Exception:  # pragma: no cover
            logger.exception("关闭人脸索引存储失败")
        self._face_store = None
        self._face_clusterer = None

    async def trigger_face_scan(
        self,
        *,
        iter_image_records: Any,
        wait: bool = False,
    ) -> bool:
        engine = await self.get_face_engine()
        store = await self.get_face_store()
        clusterer = await self.get_face_clusterer()
        if engine is None or store is None or clusterer is None:
            return False
        if self._face_scan_task and not self._face_scan_task.done():
            self._face_rescan_pending = True
            self._face_rescan_iter = iter_image_records
            return False

        from .face import FaceIndexWorker

        rebuild_worker = (
            self._face_worker is None
            or getattr(self._face_worker, "_store", None) is not store
            or getattr(self._face_worker, "_engine", None) is not engine
        )
        if rebuild_worker:
            self._face_worker = FaceIndexWorker(
                store=store,
                engine=engine,
                clusterer=clusterer,
                iter_image_records=iter_image_records,
                thumb_dir=self._face_thumb_dir,
                model_version=FACE_MODEL_KEY,
                min_det_score=self._face_min_det_score,
                min_face_size=self._face_min_face_size,
                min_blur_var=self._face_min_blur_var,
            )
        else:
            self._face_worker._iter_records = iter_image_records  # type: ignore[attr-defined]
            self._face_worker.update_quality_thresholds(
                min_det_score=self._face_min_det_score,
                min_face_size=self._face_min_face_size,
                min_blur_var=self._face_min_blur_var,
            )

        self._face_rescan_pending = False
        self._face_rescan_iter = None
        self._face_scan_task = asyncio.create_task(
            self._run_face_scan_with_followup(iter_image_records),
            name="face-index-scan",
        )
        if wait:
            try:
                await self._face_scan_task
            except Exception:  # pragma: no cover
                logger.exception("人脸扫描任务异常")
        return True

    async def _run_face_scan_with_followup(self, iter_image_records: Any) -> Any:
        """跑一次人脸 ``run_full_scan``；结束时若有 race 请求则继续补跑。"""
        try:
            return await self._face_worker.run_full_scan()
        finally:
            if self._face_rescan_pending:
                pending_iter = self._face_rescan_iter or iter_image_records
                self._face_rescan_pending = False
                self._face_rescan_iter = None

                async def _follow_up() -> None:
                    try:
                        await self.trigger_face_scan(iter_image_records=pending_iter)
                    except Exception:  # pragma: no cover
                        logger.exception("人脸跟进扫描失败")

                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:  # pragma: no cover
                    loop = asyncio.get_event_loop()
                loop.create_task(_follow_up(), name="face-index-scan-followup")

    @property
    def face_thumb_dir(self) -> Path:
        return self._face_thumb_dir

    async def cleanup_face_orphans(
        self, valid_media_ids: Iterable[int]
    ) -> int:
        """删除已经在媒体库消失的人脸记录。"""
        store = await self.get_face_store()
        if store is None:
            return 0
        valid = {int(mid) for mid in valid_media_ids}
        existing = await store.list_indexed_media_ids()
        all_orphan_face_ids = await store.list_orphan_face_records(valid)
        removed = 0
        for media_id in existing - valid:
            removed += await store.delete_faces_for_media(media_id)
        if all_orphan_face_ids:
            assert store._conn is not None  # noqa: SLF001
            async with store._lock:  # noqa: SLF001
                placeholders = ",".join("?" * len(all_orphan_face_ids))
                await store._conn.execute(  # noqa: SLF001
                    f"DELETE FROM face_records WHERE id IN ({placeholders})",
                    [int(fid) for fid in all_orphan_face_ids],
                )
                await store._conn.commit()  # noqa: SLF001
        await store.recount_persons()
        return removed + len(all_orphan_face_ids)

    async def regenerate_face_thumbs(
        self,
        media_resolver: Callable[[int], Awaitable[str | None]],
        *,
        force: bool = True,
    ) -> tuple[int, int]:
        """重建所有人脸缩略图。返回 ``(成功数, 失败数)``。"""
        if not self.face_enabled:
            return 0, 0
        store = await self.get_face_store()
        if store is None:
            return 0, 0
        from .face import FaceIndexWorker

        if self._face_worker is None:
            engine = await self.get_face_engine()
            clusterer = await self.get_face_clusterer()
            if engine is None or clusterer is None:
                return 0, 0

            async def _empty_iter():
                return []

            self._face_worker = FaceIndexWorker(
                store=store,
                engine=engine,
                clusterer=clusterer,
                iter_image_records=_empty_iter,
                thumb_dir=self._face_thumb_dir,
                model_version=FACE_MODEL_KEY,
                min_det_score=self._face_min_det_score,
                min_face_size=self._face_min_face_size,
                min_blur_var=self._face_min_blur_var,
            )
        return await self._face_worker.regenerate_thumbs(
            media_resolver, force=force
        )

    async def prune_low_quality_faces(
        self,
        *,
        min_det_score: float | None = None,
        min_face_size: int | None = None,
        min_blur_var: float | None = None,
        ignore_blur_var_zero: bool = True,
    ) -> dict[str, Any]:
        """按当前（或显式传入的）阈值清理已有低质量人脸。

        - 缺省时使用 manager 当前阈值，等价于「按现行设置回溯清理」；
        - 删除完成后会调用 ``recount_persons`` 修正角色统计、清理空角色；
        - 返回 ``{"removed": [face_ids], "thresholds": {...}}``。
        """
        if not self.face_enabled:
            return {"removed": [], "thresholds": self.face_quality_thresholds}
        store = await self.get_face_store()
        if store is None:
            return {"removed": [], "thresholds": self.face_quality_thresholds}

        score = (
            self._face_min_det_score if min_det_score is None else float(min_det_score)
        )
        size = (
            self._face_min_face_size if min_face_size is None else int(min_face_size)
        )
        blur = (
            self._face_min_blur_var if min_blur_var is None else float(min_blur_var)
        )

        removed = await store.prune_low_quality_faces(
            min_det_score=max(0.0, score),
            min_face_size=max(0.0, float(size)),
            min_blur_var=max(0.0, blur),
            ignore_blur_var_zero=ignore_blur_var_zero,
        )

        if removed:
            await store.recount_persons()
            for person in await store.list_persons():
                if person.face_count == 0:
                    await store.delete_person(person.id)
        return {
            "removed": removed,
            "thresholds": {
                "min_det_score": float(score),
                "min_face_size": float(size),
                "min_blur_var": float(blur),
            },
        }

    async def clear_all_face_data(self) -> dict[str, int]:
        """删除所有已识别的人脸数据。

        覆盖范围：
          - ``face_records`` / ``face_persons`` / ``face_scans`` 三张索引表；
          - ``face_thumbs`` 目录下所有人脸缩略图文件；
          - ``FaceIndexWorker`` 内部 stats（``last_run_at``、``failed_media_ids`` 等）。

        如果当前正在扫描，会等待扫描结束（让 worker 持有的运行状态先释放）。

        返回 ``{"face_count": ..., "person_count": ..., "thumbs_removed": ...}``。
        """
        if not self.face_enabled:
            return {"face_count": 0, "person_count": 0, "thumbs_removed": 0}

        # 若正在扫描，等待当前任务结束，避免在写入过程中清表导致竞态。
        scan_task = self._face_scan_task
        if scan_task is not None and not scan_task.done():
            try:
                await asyncio.shield(asyncio.wait_for(scan_task, timeout=30))
            except (asyncio.TimeoutError, Exception):  # pragma: no cover
                logger.warning("等待人脸扫描结束超时或异常，仍继续执行清空")

        store = await self.get_face_store()
        if store is None:
            return {"face_count": 0, "person_count": 0, "thumbs_removed": 0}

        summary = await store.clear_all()

        thumbs_removed = 0
        try:
            for entry in self._face_thumb_dir.iterdir():
                if entry.is_file():
                    try:
                        entry.unlink()
                        thumbs_removed += 1
                    except OSError as exc:
                        logger.warning(
                            "删除人脸缩略图失败 path=%s err=%s", entry, exc
                        )
        except FileNotFoundError:
            self._face_thumb_dir.mkdir(parents=True, exist_ok=True)

        if self._face_worker is not None:
            try:
                self._face_worker.reset_stats()
            except Exception:  # pragma: no cover
                logger.exception("重置人脸 worker 统计失败")
        self._face_rescan_pending = False
        self._face_rescan_iter = None

        summary["thumbs_removed"] = thumbs_removed
        logger.info(
            "已清空所有人脸数据: faces=%s persons=%s thumbs=%s",
            summary.get("face_count", 0),
            summary.get("person_count", 0),
            thumbs_removed,
        )
        return summary

    # ----- 状态查询 -----

    def snapshot(self, model_key: str) -> ModelSnapshot | None:
        spec = self._models.get(model_key)
        if spec is None:
            return None
        return self._make_snapshot(spec)

    def snapshots(self) -> list[ModelSnapshot]:
        return [self._make_snapshot(spec) for spec in self._models.values()]

    def _make_snapshot(self, spec: ModelSpec) -> ModelSnapshot:
        runtime = self._runtimes[spec.key]
        files_complete = sum(
            1 for f in spec.required_files if self._downloader.is_file_complete(spec, f)
        )
        bytes_complete = 0
        for f in spec.required_files:
            path = self._downloader.file_path(spec, f)
            if path.is_file():
                try:
                    bytes_complete += path.stat().st_size
                except OSError:
                    pass

        bytes_total = sum(f.size_bytes or 0 for f in spec.required_files) or None
        missing_deps = self._compute_missing_deps(spec, runtime)
        return ModelSnapshot(
            key=spec.key,
            capability=spec.capability,
            display_name=spec.display_name,
            description=spec.description,
            homepage=spec.homepage,
            license=spec.license,
            status=runtime.status,
            phase=runtime.phase,
            files_total=len(spec.required_files),
            files_complete=files_complete,
            bytes_total=bytes_total,
            bytes_complete=bytes_complete,
            extra_requirements=list(spec.extra_requirements),
            last_error=runtime.last_error,
            current_file=runtime.current_file,
            progress_bytes=runtime.progress_bytes,
            progress_total=runtime.total_bytes,
            files_done=runtime.progress_files,
            last_event_at=runtime.last_event_at,
            target_dir=str(self._downloader.model_dir(spec)),
            deps_total=runtime.deps_total,
            deps_installed=runtime.deps_installed,
            deps_pending=list(runtime.deps_pending),
            missing_deps=list(missing_deps),
        )

    def _compute_missing_deps(
        self, spec: ModelSpec, runtime: _ModelRuntime
    ) -> list[str]:
        """惰性探测「已声明但当前环境仍缺失」的 pip 依赖。

        - 仅当模型处于 ``ready`` 状态时才执行探测：``not_downloaded``/``downloading``/
          ``failed`` 等状态下没有意义；
        - 结果按 :data:`_MISSING_DEPS_TTL_SECONDS` 缓存，避免高频前端轮询时反复
          调用 ``installer.find_missing``；
        - 任何异常都会被吞掉并返回空列表，保证状态查询不被阻塞。
        """
        installer = self._dependency_installer
        specs = tuple(spec.extra_requirements or ())
        if installer is None or not specs:
            runtime.missing_deps_cache = []
            runtime.missing_deps_checked_at = time.time()
            return []
        if runtime.status != ModelStatus.ready:
            return list(runtime.missing_deps_cache)
        now = time.time()
        if (
            runtime.missing_deps_checked_at
            and now - runtime.missing_deps_checked_at < _MISSING_DEPS_TTL_SECONDS
        ):
            return list(runtime.missing_deps_cache)
        try:
            missing_raw = installer.find_missing(specs)
        except Exception as exc:  # pragma: no cover - 检测失败不影响 UI
            logger.debug("依赖探测失败 (%s): %s", spec.key, exc)
            runtime.missing_deps_checked_at = now
            return list(runtime.missing_deps_cache)
        missing = [
            str(item).strip()
            for item in (missing_raw or [])
            if str(item).strip()
        ]
        runtime.missing_deps_cache = missing
        runtime.missing_deps_checked_at = now
        return list(missing)

    # ----- 配置更新 -----

    def update_settings(
        self,
        *,
        feature_enabled: bool | None = None,
        clip_enabled: bool | None = None,
        face_enabled: bool | None = None,
        hf_mirror_url: str | None = None,
        max_concurrent_downloads: int | None = None,
        face_min_det_score: float | None = None,
        face_min_face_size: int | None = None,
        face_min_blur_var: float | None = None,
    ) -> None:
        clip_changed = clip_enabled is not None and bool(clip_enabled) != self._clip_enabled
        face_changed = face_enabled is not None and bool(face_enabled) != self._face_enabled
        feature_changed = (
            feature_enabled is not None and bool(feature_enabled) != self._feature_enabled
        )
        if feature_enabled is not None:
            self._feature_enabled = bool(feature_enabled)
        if clip_enabled is not None:
            self._clip_enabled = bool(clip_enabled)
        if face_enabled is not None:
            self._face_enabled = bool(face_enabled)
        if hf_mirror_url is not None:
            self._downloader.update_mirror(hf_mirror_url)
        if max_concurrent_downloads is not None:
            self._max_concurrent_downloads = max(1, min(3, int(max_concurrent_downloads)))
            self._download_sema = asyncio.Semaphore(self._max_concurrent_downloads)
        if face_min_det_score is not None:
            try:
                self._face_min_det_score = max(0.0, min(1.0, float(face_min_det_score)))
            except (TypeError, ValueError):
                pass
        if face_min_face_size is not None:
            try:
                self._face_min_face_size = max(0, int(face_min_face_size))
            except (TypeError, ValueError):
                pass
        if face_min_blur_var is not None:
            try:
                self._face_min_blur_var = max(0.0, float(face_min_blur_var))
            except (TypeError, ValueError):
                pass
        if self._face_worker is not None:
            self._face_worker.update_quality_thresholds(
                min_det_score=self._face_min_det_score,
                min_face_size=self._face_min_face_size,
                min_blur_var=self._face_min_blur_var,
            )
        self._save_settings_file()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            if (clip_changed or feature_changed) and "clip" in self._engines:
                loop.create_task(self.reset_clip_engine())
            if (face_changed or feature_changed) and "face" in self._engines:
                loop.create_task(self.reset_face_engine())

    # ----- 下载操作 -----

    async def start_download(
        self,
        model_key: str,
        *,
        progress_cb: Callable[[DownloadEvent], Awaitable[None] | None] | None = None,
    ) -> None:
        spec = self._models.get(model_key)
        if spec is None:
            raise KeyError(f"未知模型 {model_key}")
        async with self._lock:
            runtime = self._runtimes[model_key]
            if runtime.task is not None and not runtime.task.done():
                logger.info("模型 %s 已在下载中，忽略重复请求。", model_key)
                return
            runtime.status = ModelStatus.downloading
            runtime.phase = DOWNLOAD_PHASE_IDLE
            runtime.last_error = ""
            runtime.last_event_at = time.time()
            runtime.deps_total = 0
            runtime.deps_installed = 0
            runtime.deps_pending = []
            runtime.task = asyncio.create_task(
                self._run_download(spec, progress_cb), name=f"intel-download-{model_key}"
            )

    async def cancel_download(self, model_key: str) -> bool:
        async with self._lock:
            runtime = self._runtimes.get(model_key)
            if runtime is None or runtime.task is None or runtime.task.done():
                return False
            runtime.task.cancel()
            return True

    async def remove_model(self, model_key: str) -> None:
        spec = self._models.get(model_key)
        if spec is None:
            return
        await self.cancel_download(model_key)
        runtime = self._runtimes[model_key]
        if runtime.task is not None:
            try:
                await runtime.task
            except (asyncio.CancelledError, Exception):
                pass
        await self._downloader.remove(spec)
        runtime.status = ModelStatus.not_downloaded
        runtime.phase = DOWNLOAD_PHASE_IDLE
        runtime.progress_bytes = 0
        runtime.progress_files = 0
        runtime.last_error = ""
        runtime.current_file = ""
        runtime.deps_total = 0
        runtime.deps_installed = 0
        runtime.deps_pending = []
        runtime.missing_deps_cache = []
        runtime.missing_deps_checked_at = 0.0
        runtime.last_event_at = time.time()
        if spec.capability == "clip":
            await self.reset_clip_engine()
        elif spec.capability == "face":
            await self.reset_face_engine()
        self._save_state_file()

    async def shutdown(self) -> None:
        """取消所有下载任务、卸载引擎并落盘状态。"""
        for task_attr in ("_clip_scan_task", "_face_scan_task"):
            task = getattr(self, task_attr)
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
            setattr(self, task_attr, None)
        async with self._lock:
            for runtime in self._runtimes.values():
                if runtime.task is not None and not runtime.task.done():
                    runtime.task.cancel()
        for runtime in self._runtimes.values():
            if runtime.task is not None:
                try:
                    await runtime.task
                except (asyncio.CancelledError, Exception):
                    pass
        await self.reset_clip_engine()
        await self.close_clip_store()
        await self.reset_face_engine()
        await self.close_face_store()
        self._save_state_file()

    async def _run_download(
        self,
        spec: ModelSpec,
        external_cb: Callable[[DownloadEvent], Awaitable[None] | None] | None,
    ) -> None:
        runtime = self._runtimes[spec.key]
        runtime.total_files = len(spec.files)

        try:
            await self._ensure_extra_requirements(spec)
        except asyncio.CancelledError:
            runtime.status = ModelStatus.cancelled
            runtime.last_error = "已取消"
            runtime.phase = DOWNLOAD_PHASE_IDLE
            runtime.last_event_at = time.time()
            self._save_state_file()
            raise
        except Exception as exc:
            logger.exception("模型 %s 安装依赖失败", spec.key)
            runtime.status = ModelStatus.failed
            runtime.last_error = f"依赖安装失败: {exc}" if str(exc) else "依赖安装失败"
            runtime.phase = DOWNLOAD_PHASE_IDLE
            runtime.last_event_at = time.time()
            self._save_state_file()
            return

        runtime.phase = DOWNLOAD_PHASE_DOWNLOADING_FILES
        runtime.current_file = ""
        runtime.last_event_at = time.time()

        async def cb(event: DownloadEvent) -> None:
            runtime.progress_bytes = event.bytes_done
            runtime.total_bytes = event.bytes_total
            runtime.progress_files = event.files_done
            runtime.current_file = event.file_relative_path
            runtime.last_event_at = time.time()
            if external_cb is not None:
                ret = external_cb(event)
                if asyncio.iscoroutine(ret):
                    await ret

        async with self._download_sema:
            try:
                await self._downloader.download(spec, progress_cb=cb)
                complete, missing = self._downloader.model_status(spec)
                if complete:
                    runtime.status = ModelStatus.ready
                    runtime.last_error = ""
                else:
                    runtime.status = ModelStatus.partial
                    runtime.last_error = (
                        "缺失文件: " + ", ".join(f.relative_path for f in missing)
                    )
            except asyncio.CancelledError:
                runtime.status = ModelStatus.cancelled
                runtime.last_error = "已取消"
                raise
            except Exception as exc:
                logger.exception("模型 %s 下载失败", spec.key)
                runtime.status = ModelStatus.failed
                runtime.last_error = str(exc) or exc.__class__.__name__
            finally:
                runtime.phase = DOWNLOAD_PHASE_IDLE
                runtime.last_event_at = time.time()
                self._save_state_file()

    async def _ensure_extra_requirements(self, spec: ModelSpec) -> None:
        """在真正下载文件之前，先确保 ``spec.extra_requirements`` 已经齐全。

        - 没有注入 ``DependencyInstaller`` 或模型未声明依赖时直接跳过；
        - ``find_missing`` 异常时不阻塞，仅记录日志后继续；
        - ``install`` 阶段抛出的异常会冒泡，让调用方落到 ``failed`` 状态。
        """
        runtime = self._runtimes[spec.key]
        runtime.deps_total = 0
        runtime.deps_installed = 0
        runtime.deps_pending = []

        installer = self._dependency_installer
        specs = tuple(spec.extra_requirements or ())
        if installer is None or not specs:
            return

        runtime.phase = DOWNLOAD_PHASE_CHECKING_DEPS
        runtime.current_file = ""
        runtime.last_event_at = time.time()
        try:
            missing_raw = installer.find_missing(specs)
        except Exception as exc:  # pragma: no cover - 检测阶段失败不阻塞
            logger.warning("依赖预检失败，跳过自动安装: %s", exc)
            return
        missing = [str(item).strip() for item in (missing_raw or []) if str(item).strip()]
        if not missing:
            runtime.missing_deps_cache = []
            runtime.missing_deps_checked_at = time.time()
            return

        runtime.phase = DOWNLOAD_PHASE_INSTALLING_DEPS
        runtime.deps_total = len(missing)
        runtime.deps_installed = 0
        runtime.deps_pending = list(missing)
        runtime.current_file = "、".join(missing[:3]) + (
            "…" if len(missing) > 3 else ""
        )
        runtime.last_event_at = time.time()
        logger.info(
            "模型 %s 准备安装 %d 个依赖: %s",
            spec.key,
            len(missing),
            ", ".join(missing),
        )

        await installer.install(tuple(missing))

        runtime.deps_installed = runtime.deps_total
        runtime.deps_pending = []
        runtime.missing_deps_cache = []
        runtime.missing_deps_checked_at = time.time()
        runtime.last_event_at = time.time()

    # ----- 持久化 -----

    @property
    def _state_path(self) -> Path:
        return self._intelligence_dir / _STATE_FILENAME

    @property
    def _settings_path(self) -> Path:
        return self._intelligence_dir / _SETTINGS_FILENAME

    def _settings_payload(self) -> dict[str, Any]:
        return {
            "feature_enabled": self._feature_enabled,
            "clip_enabled": self._clip_enabled,
            "face_enabled": self._face_enabled,
            "hf_mirror_url": self._downloader.hf_mirror_url,
            "max_concurrent_downloads": self._max_concurrent_downloads,
            "face_min_det_score": self._face_min_det_score,
            "face_min_face_size": self._face_min_face_size,
            "face_min_blur_var": self._face_min_blur_var,
        }

    def _refresh_disk_status_sync(self) -> None:
        """启动时根据磁盘文件刷新状态。"""
        for key, spec in self._models.items():
            runtime = self._runtimes[key]
            runtime.phase = DOWNLOAD_PHASE_IDLE
            runtime.deps_total = 0
            runtime.deps_installed = 0
            runtime.deps_pending = []
            runtime.missing_deps_cache = []
            runtime.missing_deps_checked_at = 0.0
            if runtime.status in {ModelStatus.downloading, ModelStatus.cancelled}:
                runtime.status = ModelStatus.not_downloaded
            complete, missing = self._downloader.model_status(spec)
            if complete:
                runtime.status = ModelStatus.ready
            elif any(
                self._downloader.is_file_complete(spec, f) is False
                and self._downloader.file_path(spec, f).exists()
                for f in spec.required_files
            ):
                runtime.status = ModelStatus.partial
            else:
                # 任何已存在但不完整的文件都视为 partial。
                if missing and len(missing) < len(spec.required_files):
                    runtime.status = ModelStatus.partial
                else:
                    runtime.status = ModelStatus.not_downloaded

    def _save_state_file(self) -> None:
        payload = {
            "version": 1,
            "models": {
                key: {
                    "status": rt.status.value,
                    "last_error": rt.last_error,
                    "last_event_at": rt.last_event_at,
                }
                for key, rt in self._runtimes.items()
            },
        }
        try:
            tmp_path = self._state_path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp_path, self._state_path)
        except OSError as exc:
            logger.warning("保存 intelligence 状态失败: %s", exc)

    def _save_settings_file(self) -> None:
        payload = {"version": 1, "settings": self._settings_payload()}
        try:
            tmp_path = self._settings_path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp_path, self._settings_path)
        except OSError as exc:
            logger.warning("保存 intelligence 设置失败: %s", exc)

    def _load_settings_file(self) -> None:
        path = self._settings_path
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("intelligence 设置文件损坏: %s", exc)
            return
        settings = data.get("settings") if isinstance(data, dict) else None
        if not isinstance(settings, dict):
            return

        if "feature_enabled" in settings:
            self._feature_enabled = bool(settings.get("feature_enabled"))
        if "clip_enabled" in settings:
            self._clip_enabled = bool(settings.get("clip_enabled"))
        if "face_enabled" in settings:
            self._face_enabled = bool(settings.get("face_enabled"))
        if "hf_mirror_url" in settings:
            self._downloader.update_mirror(str(settings.get("hf_mirror_url") or ""))
        if "max_concurrent_downloads" in settings:
            try:
                self._max_concurrent_downloads = max(
                    1,
                    min(3, int(settings.get("max_concurrent_downloads"))),
                )
                self._download_sema = asyncio.Semaphore(self._max_concurrent_downloads)
            except (TypeError, ValueError):
                pass
        if "face_min_det_score" in settings:
            try:
                self._face_min_det_score = max(
                    0.0,
                    min(1.0, float(settings.get("face_min_det_score"))),
                )
            except (TypeError, ValueError):
                pass
        if "face_min_face_size" in settings:
            try:
                self._face_min_face_size = max(
                    0,
                    int(settings.get("face_min_face_size")),
                )
            except (TypeError, ValueError):
                pass
        if "face_min_blur_var" in settings:
            try:
                self._face_min_blur_var = max(
                    0.0,
                    float(settings.get("face_min_blur_var")),
                )
            except (TypeError, ValueError):
                pass

    def _load_state_file(self) -> None:
        path = self._state_path
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("intelligence 状态文件损坏: %s", exc)
            return
        models = data.get("models") if isinstance(data, dict) else None
        if not isinstance(models, dict):
            return
        for key, snapshot in models.items():
            runtime = self._runtimes.get(key)
            if runtime is None or not isinstance(snapshot, dict):
                continue
            try:
                runtime.status = ModelStatus(snapshot.get("status") or ModelStatus.not_downloaded.value)
            except ValueError:
                runtime.status = ModelStatus.not_downloaded
            runtime.last_error = str(snapshot.get("last_error") or "")
            runtime.last_event_at = float(snapshot.get("last_event_at") or 0.0)

