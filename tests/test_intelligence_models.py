"""ModelDownloader / IntelligenceManager 的单元测试。

启用 ``aiohttp`` 的内嵌 ``Application`` 来模拟 HuggingFace 服务，覆盖：
- 镜像 URL 重写；
- 完整下载、SHA256 校验；
- 断点续传（416 / 206）；
- 取消任务保留 .part；
- 状态文件持久化与读取；
- IntelligenceManager 控制下载并维护快照。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import socket
from pathlib import Path

import pytest
from aiohttp import web

from astrbot_plugin_media_portal.core.intelligence import (
    IntelligenceManager,
    ModelStatus,
)
from astrbot_plugin_media_portal.core.intelligence.downloader import (
    DownloadEvent,
    ModelDownloader,
)
from astrbot_plugin_media_portal.core.intelligence.models import ModelFile, ModelSpec


pytestmark = pytest.mark.asyncio


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _FakeHF:
    """伪装 HuggingFace 端点，按相对路径返回字节并支持 Range。"""

    def __init__(self, files: dict[str, bytes]):
        self.files = files
        self.app = web.Application()
        self.app.router.add_get("/{path:.*}", self._handle)
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None
        self.host = "127.0.0.1"
        self.port = _free_port()

    async def _handle(self, request: web.Request) -> web.StreamResponse:
        rel = request.match_info.get("path", "")
        if rel not in self.files:
            return web.Response(status=404)
        data = self.files[rel]
        range_header = request.headers.get("Range", "")
        start = 0
        end = len(data) - 1
        status = 200
        if range_header.startswith("bytes="):
            try:
                spec = range_header.split("=", 1)[1]
                start_text, end_text = (spec.split("-") + [""])[:2]
                start = int(start_text or 0)
                if end_text:
                    end = int(end_text)
            except ValueError:
                return web.Response(status=400)
            if start > len(data) - 1:
                return web.Response(
                    status=416,
                    headers={"Content-Range": f"bytes */{len(data)}"},
                )
            status = 206
        chunk = data[start : end + 1]
        headers = {"Content-Length": str(len(chunk))}
        if status == 206:
            headers["Content-Range"] = f"bytes {start}-{end}/{len(data)}"
        return web.Response(body=chunk, status=status, headers=headers)

    async def __aenter__(self) -> "_FakeHF":
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self.runner is not None:
            await self.runner.cleanup()


def _make_spec(payloads: dict[str, bytes], *, with_hash: bool = True) -> ModelSpec:
    files = []
    for relpath, data in payloads.items():
        files.append(
            ModelFile(
                relative_path=relpath,
                # 使用 huggingface.co 的占位 URL，下载器会被强制改写到本地 mirror。
                url=f"https://huggingface.co/{relpath}",
                size_bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest() if with_hash else None,
            )
        )
    return ModelSpec(
        key="dummy-model",
        capability="clip",
        display_name="Dummy",
        description="测试模型",
        files=tuple(files),
    )


async def test_model_downloader_full_download(tmp_path: Path) -> None:
    payload = b"hello-clip-bytes" * 64
    payloads = {"weights.onnx": payload, "tokenizer.json": b"{\"v\": 1}"}
    spec = _make_spec(payloads)
    async with _FakeHF(payloads) as hf:
        downloader = ModelDownloader(
            root_dir=tmp_path / "models",
            hf_mirror_url=f"http://{hf.host}:{hf.port}",
        )
        events: list[DownloadEvent] = []
        result = await downloader.download(spec, progress_cb=events.append)

        assert result.files_downloaded == 2
        for relpath, data in payloads.items():
            target = downloader.file_path(spec, ModelFile(relative_path=relpath, url=""))
            assert target.is_file()
            assert target.read_bytes() == data
        assert any(e.message == "completed" for e in events)


async def test_model_downloader_resume(tmp_path: Path) -> None:
    """提前写入 .part 文件，下载器应当走 Range 续传并最终拼成完整文件。"""
    payload = b"X" * 1024 + b"Y" * 1024
    payloads = {"big.bin": payload}
    spec = _make_spec(payloads)

    async with _FakeHF(payloads) as hf:
        downloader = ModelDownloader(
            root_dir=tmp_path / "models",
            hf_mirror_url=f"http://{hf.host}:{hf.port}",
        )
        target = downloader.file_path(spec, spec.files[0])
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".part")
        partial.write_bytes(payload[:512])

        result = await downloader.download(spec)
        assert result.files_downloaded == 1
        assert target.read_bytes() == payload


async def test_model_downloader_skip_complete(tmp_path: Path) -> None:
    payload = b"complete"
    payloads = {"a.bin": payload}
    spec = _make_spec(payloads, with_hash=False)
    async with _FakeHF(payloads) as hf:
        downloader = ModelDownloader(
            root_dir=tmp_path / "models",
            hf_mirror_url=f"http://{hf.host}:{hf.port}",
        )
        # 预先放置完整文件
        path = downloader.file_path(spec, spec.files[0])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

        result = await downloader.download(spec)
        assert result.skipped_files == ["a.bin"]
        assert result.files_downloaded == 0


async def test_model_downloader_sha256_mismatch(tmp_path: Path) -> None:
    real = b"good"
    spec = ModelSpec(
        key="bad-model",
        capability="clip",
        display_name="Bad",
        description="",
        files=(
            ModelFile(
                relative_path="x.bin",
                url="https://huggingface.co/x.bin",
                size_bytes=len(real),
                sha256="0" * 64,  # 故意错的
            ),
        ),
    )
    async with _FakeHF({"x.bin": real}) as hf:
        downloader = ModelDownloader(
            root_dir=tmp_path / "models",
            hf_mirror_url=f"http://{hf.host}:{hf.port}",
        )
        with pytest.raises(RuntimeError, match="SHA-256"):
            await downloader.download(spec)
        # 校验失败应该删掉 .part，避免下次跳过
        target = downloader.file_path(spec, spec.files[0])
        partial = target.with_suffix(target.suffix + ".part")
        assert not partial.exists()
        assert not target.exists()


async def test_intelligence_manager_lifecycle(tmp_path: Path) -> None:
    payloads = {"w.bin": b"abcdef" * 100, "t.json": b"{}"}
    spec = _make_spec(payloads)

    async with _FakeHF(payloads) as hf:
        manager = IntelligenceManager(
            plugin_data_dir=tmp_path,
            feature_enabled=True,
            clip_enabled=True,
            face_enabled=False,
            hf_mirror_url=f"http://{hf.host}:{hf.port}",
            models=[spec],
        )

        snap = manager.snapshot("dummy-model")
        assert snap is not None
        assert snap.status == ModelStatus.not_downloaded

        await manager.start_download("dummy-model")
        # 等到任务结束
        runtime = manager._runtimes["dummy-model"]  # type: ignore[attr-defined]
        assert runtime.task is not None
        await runtime.task

        snap_after = manager.snapshot("dummy-model")
        assert snap_after is not None
        assert snap_after.status == ModelStatus.ready
        assert snap_after.files_complete == 2

        # 持久化的状态文件应记录 ready
        state = json.loads((tmp_path / "intelligence" / "state.json").read_text("utf-8"))
        assert state["models"]["dummy-model"]["status"] == ModelStatus.ready.value

        await manager.remove_model("dummy-model")
        snap_removed = manager.snapshot("dummy-model")
        assert snap_removed is not None
        assert snap_removed.status == ModelStatus.not_downloaded

        await manager.shutdown()


async def test_intelligence_manager_ready_summary(tmp_path: Path) -> None:
    """clip_ready 应当同时取决于 `clip_enabled` 与磁盘状态。"""
    payloads = {"file.bin": b"data"}
    spec = _make_spec(payloads, with_hash=False)
    async with _FakeHF(payloads) as hf:
        manager = IntelligenceManager(
            plugin_data_dir=tmp_path,
            feature_enabled=True,
            clip_enabled=False,
            face_enabled=False,
            hf_mirror_url=f"http://{hf.host}:{hf.port}",
            models=[spec],
        )
        await manager.start_download(spec.key)
        runtime = manager._runtimes[spec.key]  # type: ignore[attr-defined]
        await runtime.task  # type: ignore[arg-type]

        snap = manager.snapshot(spec.key)
        assert snap is not None
        assert snap.status == ModelStatus.ready

        manager.update_settings(clip_enabled=True)
        assert manager.clip_enabled is True

        await manager.shutdown()


async def test_intelligence_manager_cancel(tmp_path: Path) -> None:
    """取消下载应当让 .part 保留并把状态置为 cancelled。"""
    big = b"a" * 4096

    class _SlowHF(_FakeHF):
        async def _handle(self, request: web.Request) -> web.StreamResponse:  # type: ignore[override]
            response = web.StreamResponse(status=200, headers={"Content-Length": str(len(big))})
            await response.prepare(request)
            for offset in range(0, len(big), 256):
                await response.write(big[offset : offset + 256])
                await asyncio.sleep(0.05)
            await response.write_eof()
            return response

    payloads = {"slow.bin": big}
    spec = ModelSpec(
        key="slow-model",
        capability="clip",
        display_name="Slow",
        description="",
        files=(
            ModelFile(
                relative_path="slow.bin",
                url="https://huggingface.co/slow.bin",
                size_bytes=len(big),
            ),
        ),
    )
    async with _SlowHF(payloads) as hf:
        manager = IntelligenceManager(
            plugin_data_dir=tmp_path,
            feature_enabled=True,
            clip_enabled=True,
            hf_mirror_url=f"http://{hf.host}:{hf.port}",
            models=[spec],
        )
        await manager.start_download(spec.key)
        await asyncio.sleep(0.08)
        cancelled = await manager.cancel_download(spec.key)
        assert cancelled is True
        runtime = manager._runtimes[spec.key]  # type: ignore[attr-defined]
        try:
            await runtime.task  # type: ignore[arg-type]
        except asyncio.CancelledError:
            pass
        snap = manager.snapshot(spec.key)
        assert snap is not None
        assert snap.status == ModelStatus.cancelled
        await manager.shutdown()


@pytest.mark.asyncio(loop_scope="function")
async def test_default_models_present() -> None:
    from astrbot_plugin_media_portal.core.intelligence import DEFAULT_MODELS

    keys = [spec.key for spec in DEFAULT_MODELS]
    assert "clip-vit-b16-zh" in keys
    assert "insightface-buffalo-s" in keys
    capabilities = {spec.capability for spec in DEFAULT_MODELS}
    assert capabilities == {"clip", "face"}
