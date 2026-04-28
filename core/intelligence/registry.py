"""内置模型清单（CLIP / 人脸）。

URL 默认指向 huggingface.co；下载器会按配置的镜像自动改写为 hf-mirror.com 等。
SHA256 暂时为空，留待后续接入官方校验时填充——下载流程会在缺失时仅做大小核对。
"""

from __future__ import annotations

from .models import ModelFile, ModelSpec

# Chinese-CLIP ViT-B/16 (ONNX, by Xenova)
# https://huggingface.co/Xenova/chinese-clip-vit-base-patch16
#
# 仓库由 transformers.js 团队（Hugging Face 官方）通过 🤗 Optimum 从
# OFA-Sys/chinese-clip-vit-base-patch16 导出。当前 onnx/ 子目录只提供
# 「合并图」（同时含 vision + text 编码器，按输入名分发），不再提供历史
# 版本的 text_model / vision_model 拆分文件。我们选用 int8 量化后的
# ``model_quantized.onnx``（约 190 MB），在保持中文检索效果的同时显著降低
# 体积与加载时间，配套的 tokenizer / preprocessor / config 也一并下载。
_CLIP_BASE_URL = (
    "https://huggingface.co/Xenova/chinese-clip-vit-base-patch16/resolve/main"
)

CLIP_MODEL_KEY = "clip-vit-b16-zh"
CLIP_MODEL_SPEC = ModelSpec(
    key=CLIP_MODEL_KEY,
    capability="clip",
    display_name="Chinese-CLIP ViT-B/16 (ONNX)",
    description=(
        "中文 CLIP 模型（图文双塔），用于本地语义检索。"
        "图像/文本编码均在本地 ONNX Runtime 完成，不会上传任何隐私数据。"
    ),
    license="Apache-2.0",
    homepage="https://huggingface.co/Xenova/chinese-clip-vit-base-patch16",
    extra_requirements=(
        "onnxruntime>=1.17",
        "tokenizers>=0.15",
        "Pillow>=10.0",
        "numpy>=1.26",
        "hnswlib>=0.7",
    ),
    files=(
        ModelFile(
            relative_path="onnx/model_quantized.onnx",
            url=f"{_CLIP_BASE_URL}/onnx/model_quantized.onnx",
        ),
        ModelFile(
            relative_path="tokenizer.json",
            url=f"{_CLIP_BASE_URL}/tokenizer.json",
        ),
        ModelFile(
            relative_path="tokenizer_config.json",
            url=f"{_CLIP_BASE_URL}/tokenizer_config.json",
        ),
        ModelFile(
            relative_path="vocab.txt",
            url=f"{_CLIP_BASE_URL}/vocab.txt",
        ),
        ModelFile(
            relative_path="preprocessor_config.json",
            url=f"{_CLIP_BASE_URL}/preprocessor_config.json",
        ),
        ModelFile(
            relative_path="special_tokens_map.json",
            url=f"{_CLIP_BASE_URL}/special_tokens_map.json",
            required=False,
        ),
        ModelFile(
            relative_path="config.json",
            url=f"{_CLIP_BASE_URL}/config.json",
            required=False,
        ),
    ),
)


# InsightFace buffalo_s (检测 + 识别 + 关键点)
#
# 注意：immich-app/buffalo_s 仓库虽然名字里有 buffalo_s，但**实际只**提供
# ``detection/model.onnx`` 与 ``recognition/model.onnx`` 两个文件，
# 直接对外的 ``1k3d68.onnx`` / ``2d106det.onnx`` 等会 404。
#
# 这里改用 deepghs/insightface 仓库的 ``buffalo_s`` 子目录，包含完整 5 个 ONNX
# （``1k3d68 / 2d106det / det_500m / genderage / w600k_mbf``），与 InsightFace
# 官方 ``buffalo_s.zip`` 的内容一致，FaceAnalysis 可以直接拿来用。
# https://huggingface.co/deepghs/insightface/tree/main/buffalo_s
_FACE_BASE_URL = (
    "https://huggingface.co/deepghs/insightface/resolve/main/buffalo_s"
)

FACE_MODEL_KEY = "insightface-buffalo-s"
FACE_MODEL_SPEC = ModelSpec(
    key=FACE_MODEL_KEY,
    capability="face",
    display_name="InsightFace buffalo_s",
    description=(
        "InsightFace 官方提供的轻量人脸模型集合，包含检测（SCRFD）、关键点、"
        "属性以及 ArcFace 嵌入。适用于占用与精度的平衡。"
    ),
    license="Apache-2.0",
    homepage="https://github.com/deepinsight/insightface",
    extra_requirements=(
        "insightface>=0.7.3",
        "onnxruntime>=1.17",
        "scikit-learn>=1.3",
        "numpy>=1.26",
        "Pillow>=10.0",
    ),
    files=(
        ModelFile(
            relative_path="1k3d68.onnx",
            url=f"{_FACE_BASE_URL}/1k3d68.onnx",
        ),
        ModelFile(
            relative_path="2d106det.onnx",
            url=f"{_FACE_BASE_URL}/2d106det.onnx",
        ),
        ModelFile(
            relative_path="det_500m.onnx",
            url=f"{_FACE_BASE_URL}/det_500m.onnx",
        ),
        ModelFile(
            relative_path="genderage.onnx",
            url=f"{_FACE_BASE_URL}/genderage.onnx",
        ),
        ModelFile(
            relative_path="w600k_mbf.onnx",
            url=f"{_FACE_BASE_URL}/w600k_mbf.onnx",
        ),
    ),
)


DEFAULT_MODELS: tuple[ModelSpec, ...] = (CLIP_MODEL_SPEC, FACE_MODEL_SPEC)


def get_default_models() -> tuple[ModelSpec, ...]:
    """返回内置模型清单的不可变快照。"""
    return DEFAULT_MODELS
