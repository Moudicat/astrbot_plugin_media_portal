"""模型规范（ModelSpec / ModelFile）。

这里只描述「模型由哪些文件组成、如何下载、放在哪里、用来做什么」，
不涉及任何 ML 框架细节，使得即便没有安装 onnxruntime / insightface 也能加载。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ModelCapability = Literal["clip", "face"]


@dataclass(slots=True, frozen=True)
class ModelFile:
    """模型中的单个文件。

    Attributes:
        relative_path: 相对模型根目录的路径（同时也是落盘后的相对路径）。
        url: 完整下载 URL。当配置了 HuggingFace 镜像时，下载器会把 ``huggingface.co``
            字符串替换为镜像主机。
        size_bytes: 期望大小（字节）。仅做合理性校验，可为 ``None``。
        sha256: 期望 SHA-256 摘要，小写十六进制。提供时下载完成后会校验。
            未提供则跳过摘要校验，仅做大小核对。
        required: ``True`` 表示本文件缺失则视为模型未就绪。
    """

    relative_path: str
    url: str
    size_bytes: int | None = None
    sha256: str | None = None
    required: bool = True


@dataclass(slots=True, frozen=True)
class ModelSpec:
    """单个模型的全量描述。"""

    key: str
    """全局唯一键，例如 ``clip-vit-b16-zh``。"""

    capability: ModelCapability
    """所属能力：``clip`` 或 ``face``。"""

    display_name: str
    description: str
    files: tuple[ModelFile, ...] = field(default_factory=tuple)
    license: str = ""
    homepage: str = ""
    extra_requirements: tuple[str, ...] = field(default_factory=tuple)
    """提示用户额外需要安装的 pip 包（仅展示用）。"""

    @property
    def total_size(self) -> int:
        """已声明尺寸的总和（仅作为下载进度估算）。"""
        return sum(f.size_bytes or 0 for f in self.files)

    @property
    def required_files(self) -> tuple[ModelFile, ...]:
        return tuple(f for f in self.files if f.required)
