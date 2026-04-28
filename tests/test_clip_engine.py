"""CLIP 推理引擎单元测试。

不依赖 ``onnxruntime`` / ``tokenizers``，通过 monkey-patch 的方式注入假的 InferenceSession
与 Tokenizer，以验证：

- 合并图（Xenova/chinese-clip-vit-base-patch16）的输入/输出契约能正确解析；
- 图像编码会喂入真实 ``pixel_values`` + dummy ``input_ids`` / ``attention_mask``；
- 文本编码会喂入真实 ``input_ids`` / ``attention_mask`` + dummy ``pixel_values``；
- 输出向量经过 L2 归一化；
- ``is_ready`` 在缺文件时返回 False；
- ``ClipEngineUnavailable`` 抛错路径。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
PIL = pytest.importorskip("PIL")

from astrbot_plugin_media_portal.core.intelligence.clip.engine import (
    ClipEngine,
    ClipEngineUnavailable,
    cosine_similarity,
)


pytestmark = pytest.mark.asyncio


_MERGED_INPUTS = ("input_ids", "pixel_values", "attention_mask")
_MERGED_OUTPUTS = (
    "logits_per_image",
    "logits_per_text",
    "text_embeds",
    "image_embeds",
)


def _prepare_model_dir(tmp_path: Path) -> Path:
    model_dir = tmp_path / "clip"
    (model_dir / "onnx").mkdir(parents=True)
    (model_dir / "onnx" / "model_quantized.onnx").write_bytes(b"fake")
    (model_dir / "tokenizer.json").write_text("{}", encoding="utf-8")
    (model_dir / "tokenizer_config.json").write_text(
        json.dumps({"model_max_length": 16}), encoding="utf-8"
    )
    (model_dir / "preprocessor_config.json").write_text(
        json.dumps(
            {
                "size": 32,
                "image_mean": [0.5, 0.5, 0.5],
                "image_std": [0.5, 0.5, 0.5],
            }
        ),
        encoding="utf-8",
    )
    return model_dir


class _FakeIO:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeSession:
    """假 ONNX session：模拟合并图输入/输出。

    根据 ``fetches`` 是否被指定，返回对应输出向量。基于真实输入派生
    种子值，确保「图像编码」与「文本编码」拿到的向量不同（从而能验证
    ``encode_image`` / ``encode_text`` 真的接到了不同的真实数据）。
    """

    def __init__(self, output_dim: int = 4) -> None:
        self._inputs = [_FakeIO(n) for n in _MERGED_INPUTS]
        self._outputs = [_FakeIO(n) for n in _MERGED_OUTPUTS]
        self._output_dim = output_dim
        self.last_feed: dict | None = None
        self.last_fetches: list[str] | None = None

    def get_inputs(self) -> list[_FakeIO]:
        return self._inputs

    def get_outputs(self) -> list[_FakeIO]:
        return self._outputs

    def run(self, fetches, feed: dict):
        self.last_feed = feed
        self.last_fetches = list(fetches) if fetches is not None else None

        def _vec_for(name: str):
            if name == "image_embeds":
                seed = float(feed["pixel_values"].sum() + 1.0)
            elif name == "text_embeds":
                seed = float(feed["input_ids"].sum() + 1.0)
            elif name == "logits_per_image":
                seed = 0.1
            else:  # logits_per_text
                seed = 0.2
            return np.full((1, self._output_dim), seed, dtype=np.float32)

        if fetches is None:
            return [_vec_for(o.name) for o in self._outputs]
        return [_vec_for(name) for name in fetches]


class _FakeTokenizerEncoded:
    def __init__(self, ids: list[int]) -> None:
        self.ids = ids
        self.attention_mask = [1] * len(ids)


class _FakeTokenizer:
    @classmethod
    def from_file(cls, path: str) -> "_FakeTokenizer":
        return cls()

    def enable_truncation(self, **_kwargs) -> None:
        return None

    def enable_padding(self, **_kwargs) -> None:
        return None

    def encode(self, text: str) -> _FakeTokenizerEncoded:
        return _FakeTokenizerEncoded([ord(c) % 1000 for c in text[:8]] or [0])


def _patch_runtime(monkeypatch: pytest.MonkeyPatch) -> _FakeSession:
    import sys
    import types

    fake_ort = types.ModuleType("onnxruntime")

    class _GraphLevel:
        ORT_ENABLE_ALL = 0

    class _SessionOptions:
        def __init__(self) -> None:
            self.graph_optimization_level = 0
            self.intra_op_num_threads = 1

    instance = _FakeSession()

    def _make_session(_path: str, *, sess_options=None, providers=None):
        return instance

    fake_ort.GraphOptimizationLevel = _GraphLevel
    fake_ort.SessionOptions = _SessionOptions
    fake_ort.InferenceSession = _make_session
    fake_ort.get_available_providers = lambda: ["CPUExecutionProvider"]
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)

    fake_tokenizers = types.ModuleType("tokenizers")
    fake_tokenizers.Tokenizer = _FakeTokenizer
    monkeypatch.setitem(sys.modules, "tokenizers", fake_tokenizers)

    return instance


async def test_engine_not_ready_when_files_missing(tmp_path: Path) -> None:
    engine = ClipEngine(model_dir=tmp_path / "missing")
    assert engine.is_ready() is False
    with pytest.raises(ClipEngineUnavailable):
        await engine.encode_text("hello")


async def test_engine_encode_text_and_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_session = _patch_runtime(monkeypatch)
    model_dir = _prepare_model_dir(tmp_path)
    engine = ClipEngine(model_dir=model_dir)
    assert engine.is_ready() is True

    text_vec = await engine.encode_text("hello")
    assert isinstance(text_vec, list)
    assert len(text_vec) == 4
    assert abs(sum(v * v for v in text_vec) - 1.0) < 1e-5
    assert fake_session.last_fetches == ["text_embeds"]
    feed = fake_session.last_feed or {}
    assert "input_ids" in feed and "pixel_values" in feed
    assert feed["pixel_values"].shape == (1, 3, 32, 32)
    assert float(feed["pixel_values"].sum()) == 0.0  # 图像侧为 dummy 全零

    from PIL import Image

    img = Image.new("RGB", (32, 32), color=(255, 0, 0))
    img_path = tmp_path / "red.png"
    img.save(img_path)
    image_vec = await engine.encode_image(img_path)
    assert len(image_vec) == 4
    assert abs(sum(v * v for v in image_vec) - 1.0) < 1e-5
    assert fake_session.last_fetches == ["image_embeds"]
    feed = fake_session.last_feed or {}
    assert "pixel_values" in feed and "input_ids" in feed
    assert feed["input_ids"].tolist() == [[101, 102]]  # 文本侧为 dummy [CLS][SEP]

    sim = cosine_similarity(text_vec, text_vec)
    assert abs(sim - 1.0) < 1e-5

    await engine.unload()
    assert engine.is_loaded is False


async def test_engine_load_failure_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """模型目录看似齐全但 ONNX 加载失败时应包装为 ClipEngineUnavailable。"""
    import sys
    import types

    fake_ort = types.ModuleType("onnxruntime")

    class _GraphLevel:
        ORT_ENABLE_ALL = 0

    class _SessionOptions:
        def __init__(self) -> None:
            self.graph_optimization_level = 0
            self.intra_op_num_threads = 1

    def _broken(*_args, **_kwargs):
        raise RuntimeError("bad onnx")

    fake_ort.GraphOptimizationLevel = _GraphLevel
    fake_ort.SessionOptions = _SessionOptions
    fake_ort.InferenceSession = _broken
    fake_ort.get_available_providers = lambda: ["CPUExecutionProvider"]
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)

    fake_tokenizers = types.ModuleType("tokenizers")
    fake_tokenizers.Tokenizer = _FakeTokenizer
    monkeypatch.setitem(sys.modules, "tokenizers", fake_tokenizers)

    model_dir = _prepare_model_dir(tmp_path)
    engine = ClipEngine(model_dir=model_dir)
    with pytest.raises(ClipEngineUnavailable, match="ONNX 加载失败"):
        await engine.load()
    assert engine.is_loaded is False
