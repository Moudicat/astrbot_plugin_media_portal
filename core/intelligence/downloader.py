"""通用模型下载器。

特点：
- 支持 HuggingFace 镜像（``hf_mirror_url`` 配置）；
- 支持 ``Range`` 断点续传，意外中断后再次开启可从已下载偏移继续；
- 任务取消使用 :class:`asyncio.CancelledError`，会立即停止下一个 chunk 写入；
- 校验：声明 ``sha256`` 时执行严格摘要校验，未声明时仅做大小一致性核对；
- 仅依赖 ``aiohttp`` / ``aiofiles``，无需额外引入 ML SDK。

下载器只对**单个模型**的多个文件提供顺序下载与统一进度上报；并发由
:class:`IntelligenceManager` 控制。
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Awaitable, Callable
from urllib.parse import urlparse, urlunparse

import aiofiles
import aiohttp

from astrbot.api import logger

from .models import ModelFile, ModelSpec


_HF_HOST = "huggingface.co"
_DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=None, sock_connect=20, sock_read=120)
_USER_AGENT = "astrbot-media-portal-intelligence/1.0"
_CHUNK_SIZE = 1024 * 256


@dataclass(slots=True)
class DownloadEvent:
    """下载过程中的回调事件。"""

    model_key: str
    file_relative_path: str
    bytes_done: int
    bytes_total: int | None
    files_done: int
    files_total: int
    message: str = ""


ProgressCallback = Callable[[DownloadEvent], Awaitable[None] | None]


@dataclass(slots=True)
class DownloadResult:
    """模型整体下载结果。"""

    model_key: str
    files_total: int
    files_downloaded: int
    bytes_downloaded: int
    skipped_files: list[str] = field(default_factory=list)
    cancelled: bool = False


class ModelDownloader:
    """以 ``ModelSpec`` 为单位下载文件到磁盘。

    使用方式::

        downloader = ModelDownloader(root_dir=plugin_data / "intelligence" / "models")
        result = await downloader.download(spec, hf_mirror_url="https://hf-mirror.com")
    """

    def __init__(
        self,
        root_dir: Path,
        *,
        hf_mirror_url: str = "",
        connector_factory: Callable[[], aiohttp.BaseConnector] | None = None,
    ) -> None:
        self._root_dir = Path(root_dir)
        self._hf_mirror_url = self._normalize_mirror(hf_mirror_url)
        self._connector_factory = connector_factory

    @staticmethod
    def _normalize_mirror(url: str) -> str:
        text = (url or "").strip()
        if not text:
            return ""
        try:
            parsed = urlparse(text)
        except Exception:
            return ""
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            logger.warning("intelligence.hf_mirror_url=%r 不是合法 URL，已忽略。", url)
            return ""
        return urlunparse((parsed.scheme, parsed.netloc, "", "", "", "")).rstrip("/")

    @property
    def hf_mirror_url(self) -> str:
        return self._hf_mirror_url

    def update_mirror(self, hf_mirror_url: str) -> None:
        self._hf_mirror_url = self._normalize_mirror(hf_mirror_url)

    def model_dir(self, spec: ModelSpec) -> Path:
        return (self._root_dir / spec.key).resolve()

    def file_path(self, spec: ModelSpec, file: ModelFile) -> Path:
        return (self.model_dir(spec) / file.relative_path).resolve()

    def rewrite_url(self, raw_url: str) -> str:
        """将 ``huggingface.co`` 改写为镜像主机。"""
        if not self._hf_mirror_url:
            return raw_url
        try:
            parsed = urlparse(raw_url)
        except Exception:
            return raw_url
        if parsed.netloc.lower() != _HF_HOST:
            return raw_url
        mirror = urlparse(self._hf_mirror_url)
        return urlunparse(
            (
                mirror.scheme or parsed.scheme,
                mirror.netloc or parsed.netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )

    def is_file_complete(self, spec: ModelSpec, file: ModelFile) -> bool:
        path = self.file_path(spec, file)
        if not path.is_file():
            return False
        if file.size_bytes and path.stat().st_size != file.size_bytes:
            return False
        return True

    def model_status(self, spec: ModelSpec) -> tuple[bool, list[ModelFile]]:
        """返回 ``(完整, 缺失文件列表)``。"""
        missing: list[ModelFile] = []
        for f in spec.required_files:
            if not self.is_file_complete(spec, f):
                missing.append(f)
        return (not missing, missing)

    async def download(
        self,
        spec: ModelSpec,
        *,
        progress_cb: ProgressCallback | None = None,
        hf_mirror_url: str | None = None,
    ) -> DownloadResult:
        """下载 ``spec`` 全部 ``required=True`` 的文件。

        Args:
            spec: 模型规格。
            progress_cb: 进度回调，可同步或异步。
            hf_mirror_url: 临时覆盖镜像；不传则使用初始化时配置。

        Raises:
            asyncio.CancelledError: 由调用方取消时立即抛出。
            RuntimeError: 网络错误或校验失败。
        """
        if hf_mirror_url is not None:
            mirror = self._normalize_mirror(hf_mirror_url)
        else:
            mirror = self._hf_mirror_url

        target_dir = self.model_dir(spec)
        target_dir.mkdir(parents=True, exist_ok=True)

        files = list(spec.files)
        files_total = len(files)
        files_done = 0
        bytes_downloaded = 0
        skipped: list[str] = []

        connector = (
            self._connector_factory()
            if self._connector_factory is not None
            else aiohttp.TCPConnector(limit=4)
        )
        async with aiohttp.ClientSession(
            timeout=_DEFAULT_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
            connector=connector,
        ) as session:
            for file in files:
                final_path = self.file_path(spec, file)
                final_path.parent.mkdir(parents=True, exist_ok=True)
                if self.is_file_complete(spec, file):
                    files_done += 1
                    skipped.append(file.relative_path)
                    await _emit(
                        progress_cb,
                        DownloadEvent(
                            model_key=spec.key,
                            file_relative_path=file.relative_path,
                            bytes_done=final_path.stat().st_size,
                            bytes_total=final_path.stat().st_size,
                            files_done=files_done,
                            files_total=files_total,
                            message="skipped",
                        ),
                    )
                    continue

                effective_url = self._rewrite_with(file.url, mirror)
                got_bytes = await self._download_one(
                    session=session,
                    url=effective_url,
                    target=final_path,
                    expected_size=file.size_bytes,
                    expected_sha256=file.sha256,
                    spec_key=spec.key,
                    file_rel=file.relative_path,
                    files_done=files_done,
                    files_total=files_total,
                    progress_cb=progress_cb,
                )
                bytes_downloaded += got_bytes
                files_done += 1

        return DownloadResult(
            model_key=spec.key,
            files_total=files_total,
            files_downloaded=files_done - len(skipped),
            bytes_downloaded=bytes_downloaded,
            skipped_files=skipped,
        )

    def _rewrite_with(self, url: str, mirror: str) -> str:
        if not mirror:
            return url
        try:
            parsed = urlparse(url)
        except Exception:
            return url
        if parsed.netloc.lower() != _HF_HOST:
            return url
        m = urlparse(mirror)
        return urlunparse(
            (m.scheme, m.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
        )

    async def _download_one(
        self,
        *,
        session: aiohttp.ClientSession,
        url: str,
        target: Path,
        expected_size: int | None,
        expected_sha256: str | None,
        spec_key: str,
        file_rel: str,
        files_done: int,
        files_total: int,
        progress_cb: ProgressCallback | None,
    ) -> int:
        partial = target.with_suffix(target.suffix + ".part")
        offset = partial.stat().st_size if partial.exists() else 0
        headers: dict[str, str] = {}
        if offset > 0:
            headers["Range"] = f"bytes={offset}-"

        try:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 416 and offset > 0:
                    # Range Not Satisfiable —— 服务器认为已经下载完毕。
                    partial.replace(target)
                    await self._verify_and_finalize(
                        target, expected_size, expected_sha256
                    )
                    await _emit(
                        progress_cb,
                        DownloadEvent(
                            model_key=spec_key,
                            file_relative_path=file_rel,
                            bytes_done=target.stat().st_size,
                            bytes_total=target.stat().st_size,
                            files_done=files_done + 1,
                            files_total=files_total,
                            message="resumed-complete",
                        ),
                    )
                    return target.stat().st_size

                if resp.status not in (200, 206):
                    raise RuntimeError(
                        f"下载 {file_rel} 失败：HTTP {resp.status} ({url})"
                    )

                total = resp.content_length
                if total is not None and resp.status == 206:
                    total += offset

                hasher = hashlib.sha256() if expected_sha256 else None
                if hasher and offset > 0 and partial.exists():
                    # 续传时需要把已存在的字节先喂给摘要器。
                    async with aiofiles.open(partial, "rb") as fp:
                        while True:
                            chunk = await fp.read(_CHUNK_SIZE)
                            if not chunk:
                                break
                            hasher.update(chunk)

                bytes_done = offset
                async with aiofiles.open(partial, "ab") as fp:
                    async for chunk in resp.content.iter_chunked(_CHUNK_SIZE):
                        if not chunk:
                            continue
                        await fp.write(chunk)
                        if hasher:
                            hasher.update(chunk)
                        bytes_done += len(chunk)
                        await _emit(
                            progress_cb,
                            DownloadEvent(
                                model_key=spec_key,
                                file_relative_path=file_rel,
                                bytes_done=bytes_done,
                                bytes_total=total,
                                files_done=files_done,
                                files_total=files_total,
                                message="downloading",
                            ),
                        )

                if hasher and expected_sha256:
                    actual = hasher.hexdigest()
                    if actual.lower() != expected_sha256.lower():
                        partial.unlink(missing_ok=True)
                        raise RuntimeError(
                            f"{file_rel} SHA-256 校验失败 (expected {expected_sha256[:8]}…, got {actual[:8]}…)"
                        )

                if expected_size and partial.stat().st_size != expected_size:
                    partial.unlink(missing_ok=True)
                    raise RuntimeError(
                        f"{file_rel} 大小不匹配 (expected {expected_size}, got {partial.stat().st_size})"
                    )

                partial.replace(target)
                await _emit(
                    progress_cb,
                    DownloadEvent(
                        model_key=spec_key,
                        file_relative_path=file_rel,
                        bytes_done=target.stat().st_size,
                        bytes_total=target.stat().st_size,
                        files_done=files_done + 1,
                        files_total=files_total,
                        message="completed",
                    ),
                )
                return bytes_done - offset
        except asyncio.CancelledError:
            # 不删除 .part，便于下次续传。
            raise

    @staticmethod
    async def _verify_and_finalize(
        target: Path, expected_size: int | None, expected_sha256: str | None
    ) -> None:
        if expected_size and target.stat().st_size != expected_size:
            raise RuntimeError(f"{target.name} 大小不匹配。")
        if not expected_sha256:
            return
        hasher = hashlib.sha256()
        async with aiofiles.open(target, "rb") as fp:
            while True:
                chunk = await fp.read(_CHUNK_SIZE)
                if not chunk:
                    break
                hasher.update(chunk)
        if hasher.hexdigest().lower() != expected_sha256.lower():
            raise RuntimeError(f"{target.name} SHA-256 校验失败。")

    async def remove(self, spec: ModelSpec) -> None:
        """删除模型目录下的所有文件。"""
        directory = self.model_dir(spec)
        if not directory.exists():
            return
        for file in spec.files:
            try:
                self.file_path(spec, file).unlink(missing_ok=True)
            except OSError:
                continue
            partial = self.file_path(spec, file).with_suffix(
                self.file_path(spec, file).suffix + ".part"
            )
            try:
                partial.unlink(missing_ok=True)
            except OSError:
                continue
        # 清理空目录树
        try:
            for sub in sorted(
                (p for p in directory.rglob("*") if p.is_dir()),
                key=lambda p: len(p.parts),
                reverse=True,
            ):
                try:
                    sub.rmdir()
                except OSError:
                    continue
            directory.rmdir()
        except OSError:
            pass


async def _emit(callback: ProgressCallback | None, event: DownloadEvent) -> None:
    if callback is None:
        return
    try:
        result = callback(event)
        if asyncio.iscoroutine(result):
            await result
    except asyncio.CancelledError:
        raise
    except Exception:  # pragma: no cover - 不让回调把下载流程拖崩
        logger.warning("intelligence 下载进度回调异常", exc_info=True)


async def _async_iter_chunks(
    stream: aiohttp.StreamReader, chunk_size: int = _CHUNK_SIZE
) -> AsyncIterator[bytes]:  # pragma: no cover - 备用辅助
    async for chunk in stream.iter_chunked(chunk_size):
        yield chunk
