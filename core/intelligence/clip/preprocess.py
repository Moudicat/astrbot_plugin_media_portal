"""Chinese-CLIP ViT-B/16 的图像预处理。

依据 ``preprocessor_config.json``：
- shortest-edge 等比缩放到 224；
- 中心裁剪 224×224；
- 转 RGB；
- 标准化：mean=[0.48145466, 0.4578275, 0.40821073], std=[0.26862954, 0.26130258, 0.27577711]
- 输出 NCHW float32（[1, 3, 224, 224]）。

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
        self.resolution = int(resolution or cfg.get("size", _DEFAULT_RESOLUTION))
        if isinstance(self.resolution, dict):  # 一些模型用 {"shortest_edge": 224}
            self.resolution = int(self.resolution.get("shortest_edge", _DEFAULT_RESOLUTION))
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

    def preprocess(self, image_source: Any) -> Any:
        """把任意图片输入转为 ``np.ndarray(shape=[1, 3, 224, 224], dtype=float32)``。

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

        target = self.resolution
        # 1. shortest-edge 等比缩放
        w, h = img.size
        if w < h:
            new_w = target
            new_h = round(h * (target / w))
        else:
            new_h = target
            new_w = round(w * (target / h))
        img = img.resize((new_w, new_h), Image.BICUBIC)

        # 2. center crop
        left = (new_w - target) // 2
        upper = (new_h - target) // 2
        img = img.crop((left, upper, left + target, upper + target))

        # 3. to ndarray, 归一化
        arr = np.asarray(img, dtype=np.float32) / 255.0
        mean = np.array(self.mean, dtype=np.float32).reshape(1, 1, 3)
        std = np.array(self.std, dtype=np.float32).reshape(1, 1, 3)
        arr = (arr - mean) / std
        # HWC -> CHW -> NCHW
        arr = np.transpose(arr, (2, 0, 1))[None, ...]
        return arr
