"""Media Portal 智能能力子模块。

本子包提供：
- :class:`ModelSpec` / :class:`ModelFile` —— 模型清单与单文件描述；
- :class:`ModelDownloader` —— 通用 HuggingFace 风格模型下载器（支持镜像、断点、取消、SHA256 校验）；
- :class:`IntelligenceManager` —— 统一调度与状态查询入口；
- :data:`DEFAULT_MODELS` —— 内置 CLIP / 人脸等模型清单。

子能力（CLIP 推理、人脸推理）会在后续 milestone 中以独立模块挂入本管理器，
管理器本身**不强依赖**任何 ML SDK，便于在缺失这些可选依赖时也能正常加载并展示状态。
"""

from .config_state import ModelStatus
from .downloader import DownloadEvent, ModelDownloader
from .manager import IntelligenceManager, ModelSnapshot
from .models import ModelFile, ModelSpec
from .registry import (
    CLIP_MODEL_KEY,
    DEFAULT_MODELS,
    FACE_MODEL_KEY,
    get_default_models,
)

__all__ = [
    "CLIP_MODEL_KEY",
    "DEFAULT_MODELS",
    "DownloadEvent",
    "FACE_MODEL_KEY",
    "IntelligenceManager",
    "ModelDownloader",
    "ModelFile",
    "ModelSnapshot",
    "ModelSpec",
    "ModelStatus",
    "get_default_models",
]
