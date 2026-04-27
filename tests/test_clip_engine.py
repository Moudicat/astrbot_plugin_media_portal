"""CLIP 推理引擎单元测试。

不依赖 ``onnxruntime`` / ``tokenizers``，通过 monkey-patch 的方式注入假的 InferenceSession
与 Tokenizer，以验证：
- 图像/文本输入名能在多个候选中正确匹配；
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


def _prepare_model_dir(tmp_path: Path) -> Path:
    model_dir = tmp_path / "clip"
    (model_dir / "onnx").mkdir(parents=True)
    (model_dir / "onnx" / "vision_model_quantized.onnx").write_bytes(b"fake")
    (model_dir / "onnx" / "text_model_quantized.onnx").write_bytes(b"fake")
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


class _FakeInput:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeSession:
    def __init__(self, input_names: list[str], output_dim: int = 4) -> None:
        self._inputs = [_FakeInput(n) for n in input_names]
        self._output_dim = output_dim
        self.last_feed: dict | None = None

    def get_inputs(self) -> list[_FakeInput]:
        return self._inputs

    def run(self, _outputs, feed: dict):
        self.last_feed = feed
        # 输出形状: [1, output_dim]
        first_value = next(iter(feed.values()))
        if hasattr(first_value, "sum"):
            seed = float(first_value.sum())
        else:
            seed = 1.0
        return [np.full((1, self._output_dim), seed, dtype=np.float32)]


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


def _patch_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import types

    fake_ort = types.ModuleType("onnxruntime")

    class _GraphLevel:
        ORT_ENABLE_ALL = 0

    class _SessionOptions:
        def __init__(self) -> None:
            self.graph_optimization_level = 0
            self.intra_op_num_threads = 1

    def _make_session(path: str, *, sess_options=None, providers=None):
        # 根据路径选择不同的输入名集合
        if "vision" in path:
            return _FakeSession(["pixel_values"])
        return _FakeSession(["input_ids", "attention_mask"])

    fake_ort.GraphOptimizationLevel = _GraphLevel
    fake_ort.SessionOptions = _SessionOptions
    fake_ort.InferenceSession = _make_session
    fake_ort.get_available_providers = lambda: ["CPUExecutionProvider"]
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)

    fake_tokenizers = types.ModuleType("tokenizers")
    fake_tokenizers.Tokenizer = _FakeTokenizer
    monkeypatch.setitem(sys.modules, "tokenizers", fake_tokenizers)


async def test_engine_not_ready_when_files_missing(tmp_path: Path) -> None:
    engine = ClipEngine(model_dir=tmp_path / "missing")
    assert engine.is_ready() is False
    with pytest.raises(ClipEngineUnavailable):
        await engine.encode_text("hello")


async def test_engine_encode_text_and_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_runtime(monkeypatch)
    model_dir = _prepare_model_dir(tmp_path)
    engine = ClipEngine(model_dir=model_dir)
    assert engine.is_ready() is True

    # 文本编码
    vec = await engine.encode_text("hello")
    assert isinstance(vec, list)
    assert len(vec) == 4
    norm_sq = sum(v * v for v in vec)
    assert abs(norm_sq - 1.0) < 1e-5

    # 图像编码：构造 32×32 PIL 图
    from PIL import Image

    img = Image.new("RGB", (32, 32), color=(255, 0, 0))
    img_path = tmp_path / "red.png"
    img.save(img_path)
    image_vec = await engine.encode_image(img_path)
    assert len(image_vec) == 4
    norm_sq = sum(v * v for v in image_vec)
    assert abs(norm_sq - 1.0) < 1e-5

    # cosine_similarity helper
    sim = cosine_similarity(vec, vec)
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
