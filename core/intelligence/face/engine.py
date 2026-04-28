"""InsightFace ``buffalo_s`` 推理封装。

设计要点：
- 直接基于 :mod:`insightface.model_zoo` 的低层接口加载 SCRFD 检测器与 ArcFace
  识别器，避免 :class:`insightface.app.FaceAnalysis` 隐式联网拉模型；
- 仅向调用方暴露 :class:`FaceDetection` 这种纯数据载体，不泄露 ``cv2`` / ``numpy``
  的具体类型，便于测试通过 monkeypatch 替换；
- 异步友好：所有 CPU 重活均通过 :func:`asyncio.to_thread` 调度。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


class FaceEngineUnavailable(RuntimeError):
    """模型文件 / 依赖缺失时抛出。调用方据此降级。"""


@dataclass(slots=True)
class FaceDetection:
    """单个检测人脸的结构化结果。"""

    bbox: tuple[float, float, float, float]
    """``(x1, y1, x2, y2)`` 像素坐标。"""

    kps: list[tuple[float, float]] = field(default_factory=list)
    """5 点关键点（眼/鼻/嘴角），可能为空。"""

    det_score: float = 0.0
    """检测置信度。"""

    embedding: list[float] = field(default_factory=list)
    """L2 归一化后的 512 维 ArcFace 嵌入。"""

    blur_var: float = 0.0
    """112×112 对齐人脸的 Laplacian 方差，越大越清晰。0 表示未计算或失败。"""


_DETECTOR_FILENAME = "det_500m.onnx"
_RECOGNITION_FILENAME = "w600k_mbf.onnx"


class FaceEngine:
    """InsightFace ``buffalo_s`` 推理引擎。"""

    def __init__(
        self,
        model_dir: Path,
        *,
        providers: list[str] | None = None,
        det_size: tuple[int, int] = (640, 640),
        det_thresh: float = 0.5,
    ) -> None:
        self._model_dir = Path(model_dir)
        self._providers = providers
        self._det_size = det_size
        self._det_thresh = float(det_thresh)
        self._det_model: Any = None
        self._rec_model: Any = None
        self._load_lock = asyncio.Lock()

    @property
    def model_dir(self) -> Path:
        return self._model_dir

    @property
    def is_loaded(self) -> bool:
        return self._det_model is not None and self._rec_model is not None

    def is_ready(self) -> bool:
        """是否具备最小可推理文件集。"""
        return all(
            (self._model_dir / name).is_file()
            for name in (_DETECTOR_FILENAME, _RECOGNITION_FILENAME)
        )

    async def load(self) -> None:
        if self.is_loaded:
            return
        async with self._load_lock:
            if self.is_loaded:
                return
            await asyncio.to_thread(self._load_sync)

    def _load_sync(self) -> None:
        if not self.is_ready():
            raise FaceEngineUnavailable(
                f"人脸模型未就绪，请先在设置面板完成下载: {self._model_dir}"
            )
        try:
            from insightface.model_zoo import model_zoo  # type: ignore
        except ImportError as exc:
            raise FaceEngineUnavailable(
                "缺少 insightface，请安装 requirements-face.txt"
            ) from exc

        try:
            det_model = model_zoo.get_model(
                str(self._model_dir / _DETECTOR_FILENAME),
                providers=self._providers,
            )
            det_model.prepare(
                ctx_id=-1, det_thresh=self._det_thresh, input_size=self._det_size
            )
            rec_model = model_zoo.get_model(
                str(self._model_dir / _RECOGNITION_FILENAME),
                providers=self._providers,
            )
            rec_model.prepare(ctx_id=-1)
        except Exception as exc:
            self._det_model = None
            self._rec_model = None
            raise FaceEngineUnavailable(f"InsightFace 加载失败: {exc}") from exc

        self._det_model = det_model
        self._rec_model = rec_model

    async def unload(self) -> None:
        async with self._load_lock:
            self._det_model = None
            self._rec_model = None

    async def detect(self, image_source: Any) -> list[FaceDetection]:
        """检测并嵌入图片中的所有人脸。

        ``image_source`` 接受：
        - ``str`` / :class:`pathlib.Path`：文件路径
        - ``bytes`` / ``bytearray``：原始字节
        - ``PIL.Image.Image`` / ``numpy.ndarray``：已经在内存的图像
        """
        await self.load()
        return await asyncio.to_thread(self._detect_sync, image_source)

    def _detect_sync(self, image_source: Any) -> list[FaceDetection]:
        try:
            import numpy as np
        except ImportError as exc:  # pragma: no cover
            raise FaceEngineUnavailable(
                "缺少 numpy，请安装 requirements-face.txt"
            ) from exc

        bgr = _load_bgr(image_source)
        det_model = self._det_model
        rec_model = self._rec_model
        if det_model is None or rec_model is None:
            raise FaceEngineUnavailable("人脸引擎未加载")

        bboxes, kpss = det_model.detect(bgr, max_num=0, metric="default")
        if bboxes is None or len(bboxes) == 0:
            return []

        results: list[FaceDetection] = []
        for i in range(len(bboxes)):
            box = bboxes[i]
            x1, y1, x2, y2, score = (float(v) for v in box[:5])
            kps_arr = kpss[i] if kpss is not None and i < len(kpss) else None
            kps_list: list[tuple[float, float]] = []
            if kps_arr is not None:
                kps_list = [(float(p[0]), float(p[1])) for p in kps_arr]

            embedding: list[float] = []
            blur_var = 0.0
            if kps_arr is not None:
                try:
                    aligned = _align_face(bgr, kps_arr)
                except Exception as exc:  # pragma: no cover
                    logger.warning("人脸对齐失败: %s", exc)
                    aligned = None
                if aligned is not None:
                    try:
                        feat = rec_model.get_feat(aligned)
                        embedding = _l2_normalize(np.asarray(feat).reshape(-1))
                    except Exception as exc:  # pragma: no cover
                        logger.warning("人脸嵌入计算失败: %s", exc)
                    try:
                        blur_var = _laplacian_variance(aligned)
                    except Exception as exc:  # pragma: no cover
                        logger.debug("人脸清晰度估计失败: %s", exc)
                        blur_var = 0.0

            results.append(
                FaceDetection(
                    bbox=(x1, y1, x2, y2),
                    kps=kps_list,
                    det_score=score,
                    embedding=embedding,
                    blur_var=blur_var,
                )
            )
        return results


def _load_bgr(image_source: Any) -> Any:
    """把任意图片输入转换成 InsightFace 期望的 BGR ``np.ndarray``。"""
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover
        raise FaceEngineUnavailable("缺少 numpy") from exc

    if hasattr(image_source, "shape"):
        return image_source

    try:
        from PIL import Image, ImageOps
    except ImportError as exc:  # pragma: no cover
        raise FaceEngineUnavailable("缺少 Pillow") from exc

    if isinstance(image_source, (str, Path)):
        img = Image.open(image_source)
    elif isinstance(image_source, (bytes, bytearray)):
        from io import BytesIO

        img = Image.open(BytesIO(bytes(image_source)))
    else:
        img = image_source

    img = ImageOps.exif_transpose(img).convert("RGB")
    arr = np.asarray(img)  # HWC, RGB
    return arr[:, :, ::-1].copy()  # → BGR


def _align_face(bgr: Any, kps: Any) -> Any:
    """根据五点关键点把人脸对齐到 112x112，复用 InsightFace 的工具函数。"""
    from insightface.utils import face_align  # type: ignore

    return face_align.norm_crop(bgr, landmark=kps, image_size=112)


def _l2_normalize(vec: Any) -> list[float]:
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover
        raise FaceEngineUnavailable("缺少 numpy") from exc

    arr = np.asarray(vec, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(arr))
    if norm > 0:
        arr = arr / norm
    return arr.astype(np.float32).tolist()


def _laplacian_variance(aligned_bgr: Any) -> float:
    """对 112×112 对齐人脸做 Laplacian 方差，作为清晰度指标。

    优先使用 ``cv2``（C 实现，~毫秒级），缺失时退回 numpy 手工实现的 3x3 离散
    Laplacian 卷积，仍能给出可比的相对值。
    """
    try:
        import numpy as np
    except ImportError:  # pragma: no cover
        return 0.0

    arr = np.asarray(aligned_bgr)
    if arr.size == 0:
        return 0.0

    if arr.ndim == 3:
        try:
            import cv2  # type: ignore
        except ImportError:  # pragma: no cover - insightface 自带 cv2
            cv2 = None
        if cv2 is not None:
            gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
        else:
            r = arr[:, :, 2].astype(np.float32)
            g = arr[:, :, 1].astype(np.float32)
            b = arr[:, :, 0].astype(np.float32)
            gray = (0.299 * r + 0.587 * g + 0.114 * b)
    else:
        gray = arr

    gray = gray.astype(np.float32)

    try:
        import cv2  # type: ignore
    except ImportError:  # pragma: no cover
        cv2 = None

    if cv2 is not None:
        lap = cv2.Laplacian(gray, cv2.CV_32F)
    else:  # pragma: no cover - 兜底实现，便于无 OpenCV 的最小环境
        if gray.shape[0] < 3 or gray.shape[1] < 3:
            return 0.0
        center = gray[1:-1, 1:-1]
        lap = (
            gray[:-2, 1:-1]
            + gray[2:, 1:-1]
            + gray[1:-1, :-2]
            + gray[1:-1, 2:]
            - 4.0 * center
        )

    return float(lap.var())
