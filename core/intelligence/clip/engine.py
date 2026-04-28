"""ONNX Runtime 驱动的 Chinese-CLIP 推理引擎。

设计要点：
- 适配 :data:`Xenova/chinese-clip-vit-base-patch16` 的「合并图」ONNX
  （由 🤗 Optimum 导出）。该图同时承载视觉与文本编码器，
  推理时**必须同时**喂 ``input_ids`` / ``pixel_values`` / ``attention_mask``
  三类输入；输出包含 ``image_embeds`` / ``text_embeds`` 等。
- ``ClipEngine`` 仅在调用 :meth:`load` / :meth:`encode_image` / :meth:`encode_text`
  时按需创建 ``onnxruntime.InferenceSession``，避免在缺少模型文件 / SDK 时直接崩溃；
- 不对调用方暴露 numpy 类型，只用 ``list[float]`` 作为对外向量表示；
- 支持懒加载、可重置（更换镜像/重新下载后调用 :meth:`unload` 即可）；
- 单 session 访问 ONNX（用 :class:`asyncio.Lock` 保护一次性加载，
  并发推理交由 ORT 内部线程池处理）；
- 通过给 ``session.run`` 传入指定的 fetch 名单，让 ORT 优化器有机会
  剪掉无关子图算子，从而避免每次推理都同时跑视觉与文本两侧。
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

from .preprocess import ImageProcessor
from .tokenize import TextTokenizer


logger = logging.getLogger(__name__)


class ClipEngineUnavailable(RuntimeError):
    """模型文件 / 依赖缺失时抛出。调用方据此降级回字面搜索。"""


_MODEL_RELATIVE_PATH = "onnx/model_quantized.onnx"

# Chinese-CLIP 合并图的标准输入 / 输出名（参见
# transformers/v4.31.0/src/transformers/models/chinese_clip/configuration_chinese_clip.py
# 中的 ``ChineseCLIPOnnxConfig``）。在不同 Optimum 版本下可能略有差异，
# 因此推理时仍按 session.get_inputs / get_outputs 的实际命名做兜底匹配。
_INPUT_PIXEL_VALUES = "pixel_values"
_INPUT_INPUT_IDS = "input_ids"
_INPUT_ATTENTION_MASK = "attention_mask"

_OUTPUT_IMAGE_EMBEDS = "image_embeds"
_OUTPUT_TEXT_EMBEDS = "text_embeds"

# 兜底候选名（按重要性优先级排序）。
_PIXEL_VALUE_CANDIDATES = (_INPUT_PIXEL_VALUES, "pixel_values:0", "images")
_INPUT_ID_CANDIDATES = (_INPUT_INPUT_IDS, "input_ids:0", "input")
_ATTENTION_MASK_CANDIDATES = (_INPUT_ATTENTION_MASK, "attention_mask:0")
_IMAGE_EMBED_CANDIDATES = (_OUTPUT_IMAGE_EMBEDS, "image_embeddings", "vision_embeds")
_TEXT_EMBED_CANDIDATES = (_OUTPUT_TEXT_EMBEDS, "text_embeddings")

# 各 GPU ExecutionProvider 在 Windows 上需要的运行库 DLL（任一存在即可）。
# 探测失败时会提前从 default providers 中剔除该 EP，避免 InferenceSession
# 启动阶段刷长篇 EP Error 后再回退 CPU 的噪声。
# 已显式传入 ``providers=`` 的调用方完全绕过这个探测逻辑。
_GPU_EP_REQUIRED_DLLS: dict[str, tuple[tuple[str, ...], ...]] = {
    # TensorRT EP 依赖 nvinfer_*.dll（不同版本号）。
    "TensorrtExecutionProvider": (
        ("nvinfer_10.dll", "nvinfer.dll", "nvinfer_8.dll"),
    ),
    # CUDA EP 同时需要 cuDNN 与 CUDA Runtime 都能找到。
    "CUDAExecutionProvider": (
        ("cudnn64_9.dll", "cudnn64_8.dll", "cudnn64_7.dll"),
        ("cudart64_12.dll", "cudart64_11.dll", "cudart64_10.dll"),
    ),
}


class ClipEngine:
    """Chinese-CLIP ViT-B/16 推理封装（合并图版本）。"""

    def __init__(
        self,
        model_dir: Path,
        *,
        providers: list[str] | None = None,
    ) -> None:
        self._model_dir = Path(model_dir)
        self._providers = providers
        self._session: Any = None
        self._image_processor: ImageProcessor | None = None
        self._text_tokenizer: TextTokenizer | None = None
        self._load_lock = asyncio.Lock()

        self._pixel_values_name: str = _INPUT_PIXEL_VALUES
        self._input_ids_name: str = _INPUT_INPUT_IDS
        self._attention_mask_name: str | None = _INPUT_ATTENTION_MASK
        self._image_embed_output: str | None = _OUTPUT_IMAGE_EMBEDS
        self._text_embed_output: str | None = _OUTPUT_TEXT_EMBEDS

    @property
    def model_dir(self) -> Path:
        return self._model_dir

    @property
    def is_loaded(self) -> bool:
        return self._session is not None

    def is_ready(self) -> bool:
        """快速校验本地是否具备最小可推理文件集。"""
        required = (
            _MODEL_RELATIVE_PATH,
            "tokenizer.json",
            "preprocessor_config.json",
        )
        return all((self._model_dir / name).is_file() for name in required)

    async def load(self) -> None:
        """按需加载 ONNX session（合并图，单文件）。"""
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

        providers = self._providers or self._select_default_providers(ort)
        sess_opts = ort.SessionOptions()
        sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        try:
            self._session = ort.InferenceSession(
                str(self._model_dir / _MODEL_RELATIVE_PATH),
                sess_options=sess_opts,
                providers=providers,
            )
        except Exception as exc:
            self._session = None
            raise ClipEngineUnavailable(f"CLIP ONNX 加载失败: {exc}") from exc

        try:
            self._resolve_io_names(self._session)
        except Exception as exc:
            self._session = None
            raise ClipEngineUnavailable(
                f"CLIP ONNX 输入/输出契约不兼容: {exc}"
            ) from exc

        self._image_processor = ImageProcessor(self._model_dir)
        self._text_tokenizer = TextTokenizer(self._model_dir)

    def _resolve_io_names(self, session: Any) -> None:
        """根据实际 session 的输入/输出名做一次 best-effort 绑定。"""
        input_names = [inp.name for inp in session.get_inputs()]
        output_names = [out.name for out in session.get_outputs()]

        pixel = self._first_match(input_names, _PIXEL_VALUE_CANDIDATES)
        ids = self._first_match(input_names, _INPUT_ID_CANDIDATES)
        if pixel is None or ids is None:
            raise RuntimeError(
                f"未找到 pixel_values / input_ids 输入: inputs={input_names}"
            )
        self._pixel_values_name = pixel
        self._input_ids_name = ids
        self._attention_mask_name = self._first_match(
            input_names, _ATTENTION_MASK_CANDIDATES
        )

        self._image_embed_output = self._first_match(
            output_names, _IMAGE_EMBED_CANDIDATES
        )
        self._text_embed_output = self._first_match(
            output_names, _TEXT_EMBED_CANDIDATES
        )

    @staticmethod
    def _first_match(haystack: list[str], needles: tuple[str, ...]) -> str | None:
        for cand in needles:
            if cand in haystack:
                return cand
        return None

    @staticmethod
    def _select_default_providers(ort: Any) -> list[str]:
        """从 ORT 的 available providers 中剔除当前环境下加载会失败的 GPU EP。

        在 Windows + onnxruntime-gpu 包的常见组合里，TensorRT / CUDA EP
        会因为缺少匹配版本的 NVIDIA 运行库（如 ``nvinfer_10.dll`` /
        ``cudnn64_9.dll``）在 InferenceSession 创建阶段输出长篇 ``EP Error``，
        然后自动回退 CPU。功能虽不受影响，但每次推理日志都被淹没。

        本方法通过 :mod:`ctypes` 探测对应 DLL 是否能加载，缺失则提前剔除
        该 EP；仍然保留所有可正常加载的 GPU EP 供 ORT 使用。

        如确实想强制使用某个 EP（包括 TensorRT），请在构造 :class:`ClipEngine`
        时显式传 ``providers=[...]``，会完全跳过本探测逻辑。
        """
        try:
            available = list(ort.get_available_providers())
        except Exception:  # pragma: no cover - 极少数情况下 ORT 自检异常
            return ["CPUExecutionProvider"]

        excluded: set[str] = set()
        for ep, dll_groups in _GPU_EP_REQUIRED_DLLS.items():
            if ep not in available:
                continue
            if not _all_dll_groups_loadable(dll_groups):
                excluded.add(ep)
                logger.info(
                    "禁用 ONNX EP %s：本机缺少匹配的运行库 (%s)。",
                    ep,
                    ", ".join("/".join(g) for g in dll_groups),
                )
        filtered = [p for p in available if p not in excluded]
        return filtered or ["CPUExecutionProvider"]

    async def unload(self) -> None:
        async with self._load_lock:
            self._session = None
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
        return await asyncio.to_thread(self._run_image, tensor)

    async def encode_text(self, text: str) -> list[float]:
        await self.load()
        assert self._text_tokenizer is not None
        ids, mask = await asyncio.to_thread(self._text_tokenizer.encode, text)
        return await asyncio.to_thread(self._run_text, ids, mask)

    def _run_image(self, tensor: Any) -> list[float]:
        session = self._session
        if session is None:
            raise ClipEngineUnavailable("CLIP session 未加载")

        try:
            import numpy as np
        except ImportError as exc:  # pragma: no cover
            raise ClipEngineUnavailable(
                "缺少 numpy，请安装 requirements-clip.txt"
            ) from exc

        feed = self._build_feed_for_image(tensor, np)
        fetches = (
            [self._image_embed_output] if self._image_embed_output else None
        )
        outputs = session.run(fetches, feed)
        return _l2_normalize_to_list(self._pick_output(outputs, prefer="image"))

    def _run_text(self, ids: Any, mask: Any) -> list[float]:
        session = self._session
        if session is None:
            raise ClipEngineUnavailable("CLIP session 未加载")

        try:
            import numpy as np
        except ImportError as exc:  # pragma: no cover
            raise ClipEngineUnavailable(
                "缺少 numpy，请安装 requirements-clip.txt"
            ) from exc

        feed = self._build_feed_for_text(ids, mask, np)
        fetches = (
            [self._text_embed_output] if self._text_embed_output else None
        )
        outputs = session.run(fetches, feed)
        return _l2_normalize_to_list(self._pick_output(outputs, prefer="text"))

    def _build_feed_for_image(self, tensor: Any, np: Any) -> dict[str, Any]:
        # 文本侧用最短 dummy（[CLS][SEP]，长度 2），attention_mask 全 1。
        dummy_ids = np.asarray([[101, 102]], dtype=np.int64)
        dummy_mask = np.ones((1, 2), dtype=np.int64)
        feed: dict[str, Any] = {
            self._pixel_values_name: tensor,
            self._input_ids_name: dummy_ids,
        }
        if self._attention_mask_name is not None:
            feed[self._attention_mask_name] = dummy_mask
        return feed

    def _build_feed_for_text(self, ids: Any, mask: Any, np: Any) -> dict[str, Any]:
        # 视觉侧用 dummy 全零张量；resolution 取 image_processor 的配置，
        # 缺省 224，覆盖 ViT-B/16 与 384 patch16 等常见尺寸。
        resolution = (
            self._image_processor.resolution
            if self._image_processor is not None
            else 224
        )
        dummy_pixels = np.zeros((1, 3, resolution, resolution), dtype=np.float32)
        feed: dict[str, Any] = {
            self._pixel_values_name: dummy_pixels,
            self._input_ids_name: ids,
        }
        if self._attention_mask_name is not None:
            feed[self._attention_mask_name] = mask
        return feed

    def _pick_output(self, outputs: list[Any], *, prefer: str) -> Any:
        """从 ``session.run`` 的返回结果里取出目标向量。

        - 调用 ``session.run([target], feed)`` 时 outputs 长度为 1，直接取索引 0；
        - 调用 ``session.run(None, feed)`` 时按 OnnxConfig 默认顺序兜底：
          ``[logits_per_image, logits_per_text, text_embeds, image_embeds]``。
        """
        if not outputs:
            raise ClipEngineUnavailable("ONNX 推理未返回任何输出")
        if len(outputs) == 1:
            return outputs[0][0]
        # 兜底顺序索引
        idx = 3 if prefer == "image" else 2
        if idx >= len(outputs):
            idx = -1
        return outputs[idx][0]


def _all_dll_groups_loadable(groups: tuple[tuple[str, ...], ...]) -> bool:
    """在 Windows 上探测每个 DLL 组里是否至少有一个文件能被加载。

    其它平台不做探测，直接返回 ``True`` —— Linux / macOS 上 EP 缺依赖的
    报错形式不同，这里也不会被过度屏蔽。
    """
    if sys.platform != "win32":
        return True
    try:
        import ctypes
    except ImportError:  # pragma: no cover - 极少数嵌入式 Python 没有 ctypes
        return True
    for group in groups:
        if not _any_dll_loadable(ctypes, group):
            return False
    return True


def _any_dll_loadable(ctypes_mod: Any, names: tuple[str, ...]) -> bool:
    for name in names:
        try:
            ctypes_mod.WinDLL(name)
            return True
        except OSError:
            continue
    return False


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
