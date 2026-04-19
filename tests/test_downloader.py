from __future__ import annotations

import asyncio
import socket
from pathlib import Path

import pytest

from core.downloader import MediaDownloader, MediaSource, _PublicIPResolver


def test_parse_source_supports_http_and_local_file(tmp_path: Path) -> None:
    downloader = MediaDownloader(temp_dir=tmp_path / "temp", max_file_size_mb=5)

    source_url = downloader.parse_source(" https://example.com/a.jpg ")
    assert source_url.source_type == "url"
    assert source_url.value == "https://example.com/a.jpg"

    local_file = tmp_path / "demo.png"
    local_file.write_bytes(b"demo")
    source_local = downloader.parse_source(str(local_file))
    assert source_local.source_type == "local"
    assert source_local.value == str(local_file.resolve())
    assert source_local.filename_hint == "demo.png"


def test_parse_source_rejects_empty_text(tmp_path: Path) -> None:
    downloader = MediaDownloader(temp_dir=tmp_path / "temp", max_file_size_mb=5)
    with pytest.raises(ValueError, match="source 不能为空"):
        downloader.parse_source("")


def test_parse_source_rejects_local_when_flag_disabled(tmp_path: Path) -> None:
    downloader = MediaDownloader(
        temp_dir=tmp_path / "temp",
        max_file_size_mb=5,
        allow_local_path_source=False,
    )
    local_file = tmp_path / "x.png"
    local_file.write_bytes(b"x")
    with pytest.raises(ValueError, match="仅支持 URL"):
        downloader.parse_source(str(local_file))


def test_parse_source_respects_local_path_whitelist(tmp_path: Path) -> None:
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    allowed_file = allowed_dir / "in.png"
    allowed_file.write_bytes(b"in")
    outside_file = tmp_path / "out.png"
    outside_file.write_bytes(b"out")

    downloader = MediaDownloader(
        temp_dir=tmp_path / "temp",
        max_file_size_mb=5,
        local_path_whitelist=[str(allowed_dir)],
    )

    parsed = downloader.parse_source(str(allowed_file))
    assert parsed.source_type == "local"
    assert parsed.value == str(allowed_file.resolve())

    with pytest.raises(ValueError, match="白名单"):
        downloader.parse_source(str(outside_file))


def test_parse_source_empty_whitelist_rejects_all_local_paths(tmp_path: Path) -> None:
    downloader = MediaDownloader(
        temp_dir=tmp_path / "temp",
        max_file_size_mb=5,
        local_path_whitelist=[],
    )
    local_file = tmp_path / "any.png"
    local_file.write_bytes(b"x")
    with pytest.raises(ValueError, match="白名单"):
        downloader.parse_source(str(local_file))


def test_parse_local_value_supports_file_uri(tmp_path: Path) -> None:
    downloader = MediaDownloader(temp_dir=tmp_path / "temp", max_file_size_mb=5)
    local_file = tmp_path / "song.mp3"
    local_file.write_bytes(b"audio")

    assert downloader._parse_local_value(local_file.resolve().as_uri()) == str(
        local_file.resolve()
    )
    assert downloader._parse_local_value("https://example.com/file.mp3") == ""


def test_filename_from_headers_is_sanitized(tmp_path: Path) -> None:
    _ = tmp_path
    header = "attachment; filename=\"../unsafe<> name?.png\""
    parsed = MediaDownloader._filename_from_headers(header)
    assert parsed == "unsafe_name.png"


def test_is_public_ip_classification(tmp_path: Path) -> None:
    _ = tmp_path
    assert MediaDownloader._is_public_ip("8.8.8.8") is True
    assert MediaDownloader._is_public_ip("127.0.0.1") is False
    assert MediaDownloader._is_public_ip("192.168.1.10") is False
    assert MediaDownloader._is_public_ip("not-an-ip") is False


def test_assert_safe_url_rejects_non_http_scheme(tmp_path: Path) -> None:
    async def scenario() -> None:
        downloader = MediaDownloader(temp_dir=tmp_path / "temp", max_file_size_mb=5)
        with pytest.raises(ValueError, match="仅支持 http/https URL"):
            await downloader._assert_safe_url("ftp://example.com/demo.png")

    asyncio.run(scenario())


def test_assert_public_host_rejects_local_addresses(tmp_path: Path) -> None:
    async def scenario() -> None:
        downloader = MediaDownloader(temp_dir=tmp_path / "temp", max_file_size_mb=5)
        with pytest.raises(ValueError, match="禁止访问本地或内网地址"):
            await downloader._assert_public_host("localhost")
        with pytest.raises(ValueError, match="禁止访问本地或内网地址"):
            await downloader._assert_public_host("127.0.0.1")

    asyncio.run(scenario())


def test_assert_public_host_domain_defer_dns_check(tmp_path: Path, monkeypatch) -> None:
    async def scenario() -> None:
        downloader = MediaDownloader(temp_dir=tmp_path / "temp", max_file_size_mb=5)
        monkeypatch.setattr(
            asyncio,
            "get_running_loop",
            lambda: (_ for _ in ()).throw(AssertionError("不应在此阶段触发 DNS 解析")),
        )
        await downloader._assert_public_host("example.com")

    asyncio.run(scenario())


def test_public_ip_resolver_rejects_private_ip_result(monkeypatch) -> None:
    class _FakeLoop:
        async def getaddrinfo(self, *_args, **_kwargs):
            return [
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("127.0.0.1", 443),
                )
            ]

    async def scenario() -> None:
        monkeypatch.setattr(asyncio, "get_running_loop", lambda: _FakeLoop())
        resolver = _PublicIPResolver(MediaDownloader._is_public_ip)
        with pytest.raises(OSError, match="禁止访问本地或内网地址"):
            await resolver.resolve("example.com", 443)

    asyncio.run(scenario())


def test_public_ip_resolver_accepts_public_ip_result(monkeypatch) -> None:
    class _FakeLoop:
        async def getaddrinfo(self, *_args, **_kwargs):
            return [
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("8.8.8.8", 443),
                )
            ]

    async def scenario() -> None:
        monkeypatch.setattr(asyncio, "get_running_loop", lambda: _FakeLoop())
        resolver = _PublicIPResolver(MediaDownloader._is_public_ip)
        resolved = await resolver.resolve("example.com", 443)
        assert len(resolved) == 1
        assert resolved[0]["host"] == "8.8.8.8"
        assert resolved[0]["hostname"] == "example.com"

    asyncio.run(scenario())


def test_parse_url_value_accepts_only_http_url(tmp_path: Path) -> None:
    downloader = MediaDownloader(temp_dir=tmp_path / "temp", max_file_size_mb=5)
    assert downloader._parse_url_value(" https://example.com/a.mp4 ") == "https://example.com/a.mp4"
    assert downloader._parse_url_value("file:///tmp/a.mp4") == ""
    assert downloader._parse_url_value(None) == ""


def test_extract_sources_from_event_deduplicates_sources(tmp_path: Path) -> None:
    class _Comp:
        def __init__(self, **kwargs) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    class _MsgObj:
        def __init__(self, message) -> None:
            self.message = message

    class _Event:
        def __init__(self, components) -> None:
            self.message_obj = _MsgObj(components)

    async def scenario() -> None:
        downloader = MediaDownloader(temp_dir=tmp_path / "temp", max_file_size_mb=5)
        local_file = tmp_path / "dup.png"
        local_file.write_bytes(b"image")

        comps = [
            _Comp(url="https://example.com/a.png", name="a.png"),
            _Comp(url="https://example.com/a.png", name="a2.png"),  # duplicate URL
            _Comp(file=str(local_file), filename="dup.png"),
            _Comp(path=str(local_file), filename="dup2.png"),  # duplicate local
        ]
        event = _Event(comps)
        sources = await downloader.extract_sources_from_event(event)

        assert len(sources) == 2
        assert any(item.source_type == "url" for item in sources)
        assert any(item.source_type == "local" for item in sources)

    asyncio.run(scenario())


def test_extract_sources_from_event_supports_get_messages_and_converter(
    tmp_path: Path,
) -> None:
    class _CompWithConverter:
        def __init__(self, converted_path: str) -> None:
            self.name = ""
            self.filename = ""
            self.url = None
            self.file = None
            self.path = None
            self._converted_path = converted_path

        async def convert_to_file_path(self):
            return self._converted_path

    class _Event:
        def __init__(self, comps) -> None:
            self._comps = comps

        def get_messages(self):
            return self._comps

    async def scenario() -> None:
        downloader = MediaDownloader(temp_dir=tmp_path / "temp", max_file_size_mb=5)
        local_file = tmp_path / "converted.mp3"
        local_file.write_bytes(b"audio")

        event = _Event([_CompWithConverter(str(local_file))])
        sources = await downloader.extract_sources_from_event(event)

        assert sources == [
            MediaSource(
                source_type="local",
                value=str(local_file.resolve()),
                filename_hint="converted.mp3",
                component_type="_compwithconverter",
            )
        ]

    asyncio.run(scenario())
