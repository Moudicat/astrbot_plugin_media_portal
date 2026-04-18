from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException

import astrbot_plugin_media_portal.webui.server as server_mod
from astrbot_plugin_media_portal.core.media_manager import MediaRecord
from astrbot_plugin_media_portal.webui.server import WebUIServer


class _DummyDownloader:
    def __init__(self, temp_dir: Path) -> None:
        self.temp_dir = temp_dir


class _DummyMediaManager:
    def __init__(self, media_root: Path, plugin_data_dir: Path) -> None:
        self.media_root = media_root
        self.plugin_data_dir = plugin_data_dir
        self.downloader = _DummyDownloader(plugin_data_dir / "temp")
        self.max_file_size = 10 * 1024 * 1024


class _DummyCategoryManager:
    pass


class _FakeRequest:
    def __init__(
        self, *, query: dict[str, str] | None = None, headers: dict[str, str] | None = None
    ) -> None:
        self.query_params = query or {}
        self.headers = headers or {}


def _build_server(
    tmp_path: Path,
    *,
    callback_api_base: str = "",
    **config_overrides,
) -> WebUIServer:
    media_root = (tmp_path / "media").resolve()
    plugin_data_dir = (tmp_path / "plugin_data").resolve()
    data_root = (tmp_path / "astrbot_data").resolve()
    media_root.mkdir(parents=True, exist_ok=True)
    plugin_data_dir.mkdir(parents=True, exist_ok=True)
    data_root.mkdir(parents=True, exist_ok=True)

    config: dict[str, object] = {
        "enabled": True,
        "host": "0.0.0.0",
        "port": 7003,
        "access_password": "test-pass",
        "session_timeout": 3600,
        "public_base_url": "",
        "expose_astrbot_data": True,
        "allowed_origins": [],
        "readonly_token_ttl": 3600,
        "share_url_ttl": 3600,
        "data_token_ttl": 3600,
    }
    config.update(config_overrides)

    return WebUIServer(
        media_manager=_DummyMediaManager(media_root, plugin_data_dir),
        category_manager=_DummyCategoryManager(),
        config=config,
        data_root=data_root,
        callback_api_base=callback_api_base,
    )


def test_parse_allowed_origins_supports_string_and_iterables() -> None:
    assert WebUIServer._parse_allowed_origins(" https://a.example; https://b.example ") == [
        "https://a.example",
        "https://b.example",
    ]
    assert WebUIServer._parse_allowed_origins(
        [" https://a.example ", "https://b.example"]
    ) == ["https://a.example", "https://b.example"]
    assert WebUIServer._parse_allowed_origins(None) == []


def test_get_access_urls_filters_container_ips_by_default(
    tmp_path: Path, monkeypatch
) -> None:
    server = _build_server(tmp_path, public_base_url="https://public.example.com")
    monkeypatch.setattr(
        server,
        "_classify_access_ips",
        lambda: {"lan": ["192.168.1.10"], "container": ["172.18.0.2"]},
    )

    urls = server.get_access_urls()
    urls_with_container = server.get_access_urls(include_container=True)

    assert urls[0] == "https://public.example.com"
    assert "http://192.168.1.10:7003" in urls
    assert "http://172.18.0.2:7003" not in urls
    assert "http://172.18.0.2:7003" in urls_with_container


def test_get_environment_notes_for_container_without_public_url(
    tmp_path: Path, monkeypatch
) -> None:
    server = _build_server(tmp_path, public_base_url="")
    monkeypatch.setattr(
        server,
        "_classify_access_ips",
        lambda: {"lan": [], "container": ["172.17.0.2"]},
    )
    monkeypatch.setattr(server_mod, "is_container_environment", lambda: True)

    notes = server.get_environment_notes()

    assert notes
    assert any("public_base_url" in item for item in notes)
    assert any("172.17.0.2" in item for item in notes)


def test_capability_token_validation_and_expiry(tmp_path: Path, monkeypatch) -> None:
    server = _build_server(tmp_path)
    monkeypatch.setattr(server_mod.time, "time", lambda: 1_000_000)
    token = server._issue_capability_token("media", "cats/a.png", 120)

    assert server._validate_capability_token(token, scope="media", subject="cats/a.png")
    assert not server._validate_capability_token(token, scope="media", subject="cats/b.png")
    assert not server._validate_capability_token(token, scope="data", subject="cats/a.png")

    monkeypatch.setattr(server_mod.time, "time", lambda: 1_000_121)
    assert server._decode_capability_payload(token) is None


def test_capability_secret_persisted_between_instances(tmp_path: Path) -> None:
    server1 = _build_server(tmp_path)
    secret_path = (tmp_path / "plugin_data" / ".capability_secret").resolve()
    token = server1._issue_capability_token("media", "cats/demo.png", 600)

    server2 = _build_server(tmp_path)

    assert secret_path.exists()
    assert server1._capability_secret == server2._capability_secret
    assert server2._validate_capability_token(token, scope="media", subject="cats/demo.png")


def test_capability_secret_invalid_file_will_regenerate(tmp_path: Path) -> None:
    secret_path = (tmp_path / "plugin_data" / ".capability_secret").resolve()
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    secret_path.write_text("invalid-secret", encoding="utf-8")

    server = _build_server(tmp_path)
    persisted = secret_path.read_text(encoding="utf-8").strip()

    assert len(server._capability_secret) == 32
    assert len(persisted) == 64
    assert persisted != "invalid-secret"


def test_resolve_data_path_rejects_escape(tmp_path: Path) -> None:
    server = _build_server(tmp_path)
    resolved = server._resolve_data_path("logs/app.log")

    assert resolved == (server.data_root / "logs" / "app.log").resolve()
    with pytest.raises(ValueError):
        server._resolve_data_path("../secret.txt")


def test_build_media_url_encodes_path_and_issues_token(tmp_path: Path) -> None:
    server = _build_server(tmp_path, public_base_url="https://media.example.com")
    record = MediaRecord(
        id=1,
        category="猫 图",
        filename="a b.png",
        rel_path="猫 图/a b.png",
        abs_path=str((tmp_path / "media" / "猫 图" / "a b.png").resolve()),
        kind="image",
        mime="image/png",
        size=123,
        sha256="x",
        source_url="",
        sender_id="",
        description="",
        tags=[],
        created_at=0.0,
        updated_at=0.0,
    )

    url = server.build_media_url(record)
    parsed = urlparse(url)
    token = parse_qs(parsed.query).get("token", [""])[0]

    assert parsed.netloc == "media.example.com"
    assert "/files/%E7%8C%AB%20%E5%9B%BE/a%20b.png" in parsed.path
    assert token
    assert server._validate_capability_token(token, scope="media", subject=record.rel_path)


def test_validate_token_rejects_expired_session(tmp_path: Path) -> None:
    async def scenario() -> None:
        server = _build_server(tmp_path, session_timeout=60)
        now = server_mod.time.time()
        server._tokens["expired"] = {"created_at": now - 90_000, "last_active": now}

        with pytest.raises(HTTPException) as exc:
            await server._validate_token("expired")
        assert exc.value.status_code == 401

    asyncio.run(scenario())


def test_can_access_media_file_with_capability_or_session_token(tmp_path: Path) -> None:
    async def scenario() -> None:
        server = _build_server(tmp_path)
        subject = "cats/demo.png"
        capability_token = server._issue_capability_token("media", subject, 300)

        query_allowed = await server._can_access_media_file(
            _FakeRequest(query={"token": capability_token}),
            subject,
        )

        session_token = "session-token"
        now = server_mod.time.time()
        server._tokens[session_token] = {"created_at": now, "last_active": now}
        bearer_allowed = await server._can_access_media_file(
            _FakeRequest(headers={"Authorization": f"Bearer {session_token}"}),
            subject,
        )

        denied = await server._can_access_media_file(_FakeRequest(), subject)

        assert query_allowed is True
        assert bearer_allowed is True
        assert denied is False

    asyncio.run(scenario())


def test_cleanup_tokens_and_attempts(tmp_path: Path, monkeypatch) -> None:
    server = _build_server(tmp_path, session_timeout=60)
    now = 2_000_000.0
    monkeypatch.setattr(server_mod.time, "time", lambda: now)

    server._tokens["old"] = {"created_at": now - 90_000, "last_active": now}
    server._tokens["idle"] = {"created_at": now - 100, "last_active": now - 120}
    server._tokens["fresh"] = {"created_at": now - 10, "last_active": now - 10}
    server._cleanup_tokens_locked()

    assert "fresh" in server._tokens
    assert "old" not in server._tokens
    assert "idle" not in server._tokens

    server._failed_attempts = {
        "a": [now - 20, now - 10],
        "b": [now - 400],
    }
    server._cleanup_attempts_locked()
    assert "a" in server._failed_attempts
    assert "b" not in server._failed_attempts


def test_extract_token_prefers_bearer_header(tmp_path: Path) -> None:
    server = _build_server(tmp_path)

    header_token = server._extract_token(
        _FakeRequest(headers={"Authorization": "Bearer abc", "X-Auth-Token": "xyz"})
    )
    fallback_token = server._extract_token(_FakeRequest(headers={"X-Auth-Token": "xyz"}))

    assert header_token == "abc"
    assert fallback_token == "xyz"


def test_rate_limit_threshold(tmp_path: Path) -> None:
    async def scenario() -> None:
        server = _build_server(tmp_path)
        client_ip = "127.0.0.1"
        for _ in range(5):
            await server._record_failed_attempt(client_ip)
        assert await server._check_rate_limit(client_ip) is False

    asyncio.run(scenario())
