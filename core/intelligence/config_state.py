"""模型在磁盘上的状态枚举。"""

from __future__ import annotations

from enum import Enum


class ModelStatus(str, Enum):
    """模型生命周期状态。

    - ``not_downloaded``: 本地完全没有文件。
    - ``partial``: 部分必需文件缺失或大小不匹配，需要重新下载。
    - ``downloading``: 当前正有任务在下载。
    - ``ready``: 全部必需文件已就绪。
    - ``failed``: 上一次任务失败（保留错误信息便于 UI 展示）。
    - ``cancelled``: 用户主动取消。
    - ``corrupted``: 校验未通过。
    """

    not_downloaded = "not_downloaded"
    partial = "partial"
    downloading = "downloading"
    ready = "ready"
    failed = "failed"
    cancelled = "cancelled"
    corrupted = "corrupted"
