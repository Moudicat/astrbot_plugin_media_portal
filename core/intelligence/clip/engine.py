"""ONNX Runtime 驱动的 Chinese-CLIP 推理引擎。

设计要点：
- ``ClipEngine`` 仅在调用 :meth:`load` / :meth:`encode_image` / :meth:`encode_text`
  时按需创建 ``onnxruntime.InferenceSession``，避免在缺少模型文件 / SDK 时直接崩溃；
- 不对调用方暴露 numpy 类型，只用 ``list[float]`` 作为对外向量表示；
- 支持懒加载、可重置（更换镜像/重新下载后调用 :meth:`unload` 即可）；
- 单线程访问 ONNX session（用 :class:`asyncio.Lock` 保护一次性加载，
  并发推理交由 ORT 内部线程池处理）。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from .preprocess import ImageProcessor
from .tokenize import TextTokenizer


logger = logging.getLogger(__name__)


class ClipEngineUnavailable(RuntimeError):
    """模型文件 / 依赖缺失时抛出。调用方据此降级回字面搜索。"""


# 视觉 / 文本 ONNX 中可能的输入名（不同导出版本会略有差异）。
_VISION_INPUT_CANDIDATES = ("pixel_values", "input", "images")
_TEXT_INPUT_ID_CANDIDATES = ("input_ids", "input")
_TEXT_ATTENTION_MASK_CANDIDATES = ("attention_mask",)


class ClipEngine:
    """Chinese-CLIP ViT-B/16 推理封装。"""

    def __init__(
        self,
        model_dir: Path,
        *,
        providers: list[str] | None = None,
    ) -> None:
        self._model_dir = Path(model_dir)
        self._providers = providers
        self._vision_session: Any = None
        self._text_session: Any = None
        self._image_processor: ImageProcessor | None = None
        self._text_tokenizer: TextTokenizer | None = None
        self._load_lock = asyncio.Lock()

    @property
    def model_dir(self) -> Path:
        return self._model_dir

    @property
    def is_loaded(self) -> bool:
        return self._vision_session is not None and self._text_session is not None

    def is_ready(self) -> bool:
        """快速校验本地是否具备最小可推理文件集。"""
        required = (
            "onnx/text_model_quantized.onnx",
            "onnx/vision_model_quantized.onnx",
            "tokenizer.json",
        )
        return all((self._model_dir / name).is_file() for name in required)

    async def load(self) -> None:
        """按需加载 ONNX session（含视觉 / 文本两侧）。"""
        if self.is_loaded:
            return
        async with self._load_lock:
            if self.is_loaded:
                return
            await asyncio.to_thread(self._load_sync)

    def _load_sync(self) -> None:
        if not self.is_ready():
            raise ClipEngineUnavailable(
                f"CLIP 模型未就绪，请先在设置面板完成下载: {self._model_dir}"
            )
        try:
            import onnxruntime as ort  # type: ignore
        except ImportError as exc:
            raise ClipEngineUnavailable(
                "缺少 onnxruntime，请安装 requirements-clip.txt"
            ) from exc

        providers = self._providers or ort.get_available_providers()
        sess_opts = ort.SessionOptions()
        sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        try:
            self._vision_session = ort.InferenceSession(
                str(self._model_dir / "onnx" / "vision_model_quantized.onnx"),
                sess_options=sess_opts,
                providers=providers,
            )
            self._text_session = ort.InferenceSession(
                str(self._model_dir / "onnx" / "text_model_quantized.onnx"),
                sess_options=sess_opts,
                providers=providers,
            )
        except Exception as exc:
            self._vision_session = None
            self._text_session = None
            raise ClipEngineUnavailable(f"CLIP ONNX 加载失败: {exc}") from exc

        self._image_processor = ImageProcessor(self._model_dir)
        self._text_tokenizer = TextTokenizer(self._model_dir)

    async def unload(self) -> None:
        async with self._load_lock:
            self._vision_session = None
            self._text_session = None
            self._image_processor = None
            self._text_tokenizer = None

    async def encode_image(self, image_source: Any) -> list[float]:
        """计算单张图片的归一化嵌入。

        Args:
            image_source: 路径 / bytes / PIL.Image，详见
                :meth:`ImageProcessor.preprocess`。
        """
        await self.load()
        assert self._image_processor is not None
        tensor = await asyncio.to_thread(
            self._image_processor.preprocess, image_source
        )
        return await asyncio.to_thread(self._run_vision, tensor)

    async def encode_text(self, text: str) -> list[float]:
        await self.load()
        assert self._text_tokenizer is not None
        ids, mask = await asyncio.to_thread(self._text_tokenizer.encode, text)
        return await asyncio.to_thread(self._run_text, ids, mask)

    def _run_vision(self, tensor: Any) -> list[float]:
        session = self._vision_session
        if session is None:
            raise ClipEngineUnavailable("vision session 未加载")
        input_name = self._pick_input_name(session, _VISION_INPUT_CANDIDATES)
        outputs = session.run(None, {input_name: tensor})
        return _l2_normalize_to_list(outputs[0][0])

    def _run_text(self, ids: Any, mask: Any) -> list[float]:
        session = self._text_session
        if session is None:
            raise ClipEngineUnavailable("text session 未加载")
        feed: dict[str, Any] = {}
        id_input = self._pick_input_name(session, _TEXT_INPUT_ID_CANDIDATES)
        feed[id_input] = ids
        if any(inp.name in _TEXT_ATTENTION_MASK_CANDIDATES for inp in session.get_inputs()):
            for cand in _TEXT_ATTENTION_MASK_CANDIDATES:
                if any(inp.name == cand for inp in session.get_inputs()):
                    feed[cand] = mask
                    break
        outputs = session.run(None, feed)
        return _l2_normalize_to_list(outputs[0][0])

    @staticmethod
    def _pick_input_name(session: Any, candidates: tuple[str, ...]) -> str:
        names = [inp.name for inp in session.get_inputs()]
        for cand in candidates:
            if cand in names:
                return cand
        return names[0]


def _l2_normalize_to_list(vec: Any) -> list[float]:
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover
        raise ClipEngineUnavailable(
            "缺少 numpy，请安装 requirements-clip.txt"
        ) from exc

    array = np.asarray(vec, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(array))
    if norm > 0:
        array = array / norm
    return array.astype(np.float32).tolist()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """对外提供的余弦相似度（向量已归一化时 = 点积）。"""
    if len(a) != len(b) or not a:
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))
