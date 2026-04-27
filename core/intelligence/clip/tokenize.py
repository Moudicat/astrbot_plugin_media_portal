"""Chinese-CLIP 文本侧 tokenizer 加载与编码。

使用 HuggingFace ``tokenizers`` 库直接加载 ``tokenizer.json``，避免引入
``transformers`` 体积。Chinese-CLIP 文本最大长度约为 52；这里默认 52、
可通过构造参数覆盖。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DEFAULT_MAX_LENGTH = 52


class TextTokenizer:
    def __init__(self, model_dir: Path, *, max_length: int | None = None) -> None:
        self._model_dir = Path(model_dir)
        self._tokenizer: Any = None
        cfg_max = self._read_max_length()
        self.max_length = int(max_length or cfg_max or _DEFAULT_MAX_LENGTH)

    def _read_max_length(self) -> int | None:
        cfg_path = self._model_dir / "tokenizer_config.json"
        if not cfg_path.is_file():
            return None
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        candidate = data.get("model_max_length") or data.get("max_length")
        if isinstance(candidate, (int, float)) and candidate > 0:
            return int(candidate)
        return None

    def _load(self) -> Any:
        if self._tokenizer is not None:
            return self._tokenizer
        try:
            from tokenizers import Tokenizer  # type: ignore
        except ImportError as exc:  # pragma: no cover - 由 ClipEngine 上层捕获
            raise RuntimeError("缺少 tokenizers，请安装 requirements-clip.txt") from exc
        path = self._model_dir / "tokenizer.json"
        if not path.is_file():
            raise RuntimeError(f"找不到 tokenizer.json: {path}")
        self._tokenizer = Tokenizer.from_file(str(path))
        # 显式启用 padding/truncation，降低输出尺寸不一致风险。
        try:
            self._tokenizer.enable_truncation(max_length=self.max_length)
        except Exception:
            pass
        try:
            self._tokenizer.enable_padding(length=self.max_length)
        except Exception:
            pass
        return self._tokenizer

    def encode(self, text: str) -> tuple[Any, Any]:
        """返回 ``(input_ids, attention_mask)``，均为 ``np.ndarray[int64]``。"""
        try:
            import numpy as np
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("缺少 numpy，请安装 requirements-clip.txt") from exc
        tokenizer = self._load()
        encoded = tokenizer.encode(str(text or ""))
        ids = list(encoded.ids[: self.max_length])
        mask = list(encoded.attention_mask[: self.max_length])
        if len(ids) < self.max_length:
            pad_len = self.max_length - len(ids)
            ids.extend([0] * pad_len)
            mask.extend([0] * pad_len)
        return (
            np.asarray([ids], dtype=np.int64),
            np.asarray([mask], dtype=np.int64),
        )
