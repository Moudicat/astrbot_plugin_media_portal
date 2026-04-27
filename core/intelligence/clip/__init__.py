"""CLIP 语义检索子模块（图文双塔 ONNX 推理 + 索引 + 后台 worker）。"""

from .engine import ClipEngine, ClipEngineUnavailable, cosine_similarity
from .index import ClipIndexStore, deserialize_vector, serialize_vector
from .worker import ClipIndexWorker, WorkerStats

__all__ = [
    "ClipEngine",
    "ClipEngineUnavailable",
    "ClipIndexStore",
    "ClipIndexWorker",
    "WorkerStats",
    "cosine_similarity",
    "deserialize_vector",
    "serialize_vector",
]
