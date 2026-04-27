"""人脸检测 / 识别 / 聚类子模块。

提供：
- :class:`FaceEngine`：包装 InsightFace ``buffalo_s`` 模型，输出
  ``[(bbox, kps, det_score, embedding)]``；
- :class:`FaceIndexStore`：人脸 / 角色 SQLite 持久化（独立 ``face_index.db``）；
- :class:`FaceClusterer`：在线增量分配 + DBSCAN 重聚类的可拆解服务；
- :class:`FaceIndexWorker`：与 :class:`ClipIndexWorker` 对称的后台扫描 worker。
"""

from .cluster import (
    DEFAULT_ASSIGN_THRESHOLD,
    DEFAULT_DBSCAN_EPS,
    DEFAULT_DBSCAN_MIN_SAMPLES,
    FaceClusterer,
)
from .engine import FaceDetection, FaceEngine, FaceEngineUnavailable
from .index import FaceIndexStore, FaceRecord, PersonRecord
from .worker import FaceIndexWorker, FaceWorkerStats

__all__ = [
    "DEFAULT_ASSIGN_THRESHOLD",
    "DEFAULT_DBSCAN_EPS",
    "DEFAULT_DBSCAN_MIN_SAMPLES",
    "FaceClusterer",
    "FaceDetection",
    "FaceEngine",
    "FaceEngineUnavailable",
    "FaceIndexStore",
    "FaceIndexWorker",
    "FaceRecord",
    "FaceWorkerStats",
    "PersonRecord",
]
