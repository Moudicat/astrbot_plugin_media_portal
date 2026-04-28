"""Chinese-CLIP ViT-B/16 的图像预处理。

依据 ``preprocessor_config.json`` 的 HuggingFace 标准约定：

- ``size`` 三种合法形式：
  * ``int``                            → 走 shortest-edge resize
  * ``{"shortest_edge": N}``           → 同上
  * ``{"height": H, "width": W}``      → 直接 resize 到 ``(W, H)``
- ``do_center_crop`` 为真时再按 ``crop_size``
  （形如 ``{"height": H, "width": W}``）做中心裁剪；
- ``image_mean`` / ``image_std`` 标准化；
- 输出 NCHW float32（默认 ``[1, 3, 224, 224]``）。

当前 Xenova/chinese-clip-vit-base-patch16 的 preprocessor_config 使用
``size = {"height":224,"width":224}``、``do_center_crop = false``，
意味着等价于「直接拉伸到 224×224 + 标准化」；老式 OpenAI CLIP 风格的
shortest-edge + center-crop 也通过同一段代码兼容。

为了避免在导入阶段拉起 numpy/PIL，本文件**不**做模块级 import，
所有依赖都在 :class:`ImageProcessor` 内部 lazy 引入。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_DEFAULT_MEAN = (0.48145466, 0.4578275, 0.40821073)
_DEFAULT_STD = (0.26862954, 0.26130258, 0.27577711)
_DEFAULT_RESOLUTION = 224


class _SizeSpec:
    """归一化后的 resize / crop 尺寸说明。

    Attributes:
        target_h / target_w: resize 目标。
        shortest_edge: 是否按 shortest-edge 等比缩放（``True`` 时
            ``target_h == target_w`` 表示短边长度）。
        crop_h / crop_w: 中心裁剪尺寸；``None`` 表示不裁剪。
    """

    __slots__ = ("target_h", "target_w", "shortest_edge", "crop_h", "crop_w")

    def __init__(
        self,
        *,
        target_h: int,
        target_w: int,
        shortest_edge: bool,
        crop_h: int | None,
        crop_w: int | None,
    ) -> None:
        self.target_h = target_h
        self.target_w = target_w
        self.shortest_edge = shortest_edge
        self.crop_h = crop_h
        self.crop_w = crop_w


class ImageProcessor:
    """加载 ``preprocessor_config.json`` 并把图像转成模型输入张量。"""

    def __init__(
        self,
        model_dir: Path,
        *,
        resolution: int | None = None,
        mean: tuple[float, float, float] | None = None,
        std: tuple[float, float, float] | None = None,
    ) -> None:
        self._model_dir = Path(model_dir)
        cfg = self._load_config()

        self._size_spec = self._resolve_size_spec(cfg, override=resolution)
        # 对外暴露的 `resolution` 取「最终输出张量的边长」，方便调用方拿来构造 dummy 张量。
        # 若中心裁剪存在则以裁剪尺寸为准；否则按 resize 目标。
        if self._size_spec.crop_h is not None and self._size_spec.crop_w is not None:
            self.resolution = int(max(self._size_spec.crop_h, self._size_spec.crop_w))
        else:
            self.resolution = int(max(self._size_spec.target_h, self._size_spec.target_w))

        raw_mean = cfg.get("image_mean") or _DEFAULT_MEAN
        raw_std = cfg.get("image_std") or _DEFAULT_STD
        self.mean = tuple(float(v) for v in (mean or raw_mean))
        self.std = tuple(float(v) for v in (std or raw_std))

    def _load_config(self) -> dict[str, Any]:
        path = self._model_dir / "preprocessor_config.json"
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _resolve_size_spec(cfg: dict[str, Any], *, override: int | None) -> _SizeSpec:
        """根据 preprocessor 配置归一化出 resize / crop 规格。"""
        # 1. resize 目标
        target_h = target_w = _DEFAULT_RESOLUTION
        shortest_edge = True

        if override is not None:
            target_h = target_w = int(override)
        else:
            raw_size = cfg.get("size", None)
            if isinstance(raw_size, dict):
                if "shortest_edge" in raw_size:
                    se = int(raw_size.get("shortest_edge") or _DEFAULT_RESOLUTION)
                    target_h = target_w = se
                    shortest_edge = True
                elif "height" in raw_size or "width" in raw_size:
                    h = raw_size.get("height") or raw_size.get("width") or _DEFAULT_RESOLUTION
                    w = raw_size.get("width") or raw_size.get("height") or _DEFAULT_RESOLUTION
                    target_h, target_w = int(h), int(w)
                    shortest_edge = False
            elif isinstance(raw_size, (int, float)):
                target_h = target_w = int(raw_size)
                shortest_edge = True
            elif isinstance(raw_size, str):
                # 极少见但容错：纯数字字符串
                try:
                    target_h = target_w = int(raw_size)
                except ValueError:
                    pass

        # 2. center crop
        do_crop = bool(cfg.get("do_center_crop", False))
        crop_h: int | None = None
        crop_w: int | None = None
        raw_crop = cfg.get("crop_size", None)
        if do_crop:
            if isinstance(raw_crop, dict):
                ch = raw_crop.get("height") or raw_crop.get("width") or target_h
                cw = raw_crop.get("width") or raw_crop.get("height") or target_w
                crop_h, crop_w = int(ch), int(cw)
            elif isinstance(raw_crop, (int, float)):
                crop_h = crop_w = int(raw_crop)
            else:
                crop_h, crop_w = target_h, target_w
        elif shortest_edge:
            # 对于「shortest-edge resize」必然要再裁出方形，否则张量形状不固定。
            # 没有显式 crop_size 时按 resize 目标兜底。
            if isinstance(raw_crop, dict):
                ch = raw_crop.get("height") or raw_crop.get("width") or target_h
                cw = raw_crop.get("width") or raw_crop.get("height") or target_w
                crop_h, crop_w = int(ch), int(cw)
            else:
                crop_h, crop_w = target_h, target_w

        return _SizeSpec(
            target_h=target_h,
            target_w=target_w,
            shortest_edge=shortest_edge,
            crop_h=crop_h,
            crop_w=crop_w,
        )

    def preprocess(self, image_source: Any) -> Any:
        """把任意图片输入转为 ``np.ndarray(shape=[1, 3, H, W], dtype=float32)``。

        ``image_source`` 接受：
            * ``str`` / :class:`pathlib.Path`：文件路径
            * ``bytes``：原始字节
            * ``PIL.Image.Image``：已加载的图像
        """
        try:
            from PIL import Image, ImageOps
        except ImportError as exc:  # pragma: no cover - 由 ClipEngine 上层捕获
            raise RuntimeError("缺少 Pillow，请安装 requirements-clip.txt") from exc
        try:
            import numpy as np
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("缺少 numpy，请安装 requirements-clip.txt") from exc

        if isinstance(image_source, (str, Path)):
            img = Image.open(image_source)
        elif isinstance(image_source, (bytes, bytearray)):
            from io import BytesIO

            img = Image.open(BytesIO(bytes(image_source)))
        else:
            img = image_source  # 假定已经是 PIL.Image
        img = ImageOps.exif_transpose(img).convert("RGB")

        spec = self._size_spec

        # 1. resize
        w, h = img.size
        if spec.shortest_edge:
            short = min(spec.target_h, spec.target_w)
            if w < h:
                new_w = short
                new_h = max(1, round(h * (short / w)))
            else:
                new_h = short
                new_w = max(1, round(w * (short / h)))
        else:
            new_w = max(1, int(spec.target_w))
            new_h = max(1, int(spec.target_h))
        img = img.resize((new_w, new_h), Image.BICUBIC)

        # 2. center crop（必要时）
        if spec.crop_h is not None and spec.crop_w is not None:
            crop_w = min(int(spec.crop_w), new_w)
            crop_h = min(int(spec.crop_h), new_h)
            left = max(0, (new_w - crop_w) // 2)
            upper = max(0, (new_h - crop_h) // 2)
            img = img.crop((left, upper, left + crop_w, upper + crop_h))

        # 3. to ndarray, 归一化
        arr = np.asarray(img, dtype=np.float32) / 255.0
        # 防御性处理灰度 / RGBA 转 RGB 后仍然异常的情况
        if arr.ndim == 2:
            arr = np.stack([arr, arr, arr], axis=-1)
        elif arr.ndim == 3 and arr.shape[2] == 4:
            arr = arr[:, :, :3]
        mean = np.array(self.mean, dtype=np.float32).reshape(1, 1, 3)
        std = np.array(self.std, dtype=np.float32).reshape(1, 1, 3)
        arr = (arr - mean) / std
        # HWC -> CHW -> NCHW
        arr = np.transpose(arr, (2, 0, 1))[None, ...]
        return arr.astype(np.float32, copy=False)
