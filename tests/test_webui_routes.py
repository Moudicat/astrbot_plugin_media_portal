from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import astrbot_plugin_media_portal.webui.server as server_mod
from astrbot_plugin_media_portal.webui.server import WebUIServer


class _DummyDownloader:
    def __init__(self, temp_dir: Path) -> None:
        self.temp_dir = temp_dir


class _RouteMediaManager:
    def __init__(self, media_root: Path, plugin_data_dir: Path) -> None:
        self.media_root = media_root
        self.plugin_data_dir = plugin_data_dir
        self.downloader = _DummyDownloader(plugin_data_dir / "temp")
        self.max_file_size = 4 * 1024 * 1024

    async def get_stats(self):
        return {"categories": [], "total_count": 0, "total_size": 0, "by_kind": {}}


class _RouteCategoryManager:
    def get_description(self, _category: str) -> str:
        return ""


def _build_server(tmp_path: Path, *, expose_data: bool = True) -> WebUIServer:
    media_root = (tmp_path / "media").resolve()
    plugin_data_dir = (tmp_path / "plugin_data").resolve()
    data_root = (tmp_path / "astrbot_data").resolve()
    media_root.mkdir(parents=True, exist_ok=True)
    plugin_data_dir.mkdir(parents=True, exist_ok=True)
    data_root.mkdir(parents=True, exist_ok=True)
    return WebUIServer(
        media_manager=_RouteMediaManager(media_root, plugin_data_dir),
        category_manager=_RouteCategoryManager(),
        config={
            "enabled": True,
            "host": "127.0.0.1",
            "port": 7003,
            "access_password": "secret",
            "session_timeout": 3600,
            "public_base_url": "",
            "expose_astrbot_data": expose_data,
            "allowed_origins": [],
            "readonly_token_ttl": 3600,
            "share_url_ttl": 3600,
            "data_token_ttl": 3600,
        },
        data_root=data_root,
    )


def _login(client: TestClient, password: str = "secret") -> str:
    response = client.post("/api/login", json={"password": password})
    assert response.status_code == 200
    return response.json()["token"]


def test_login_config_logout_flow(tmp_path: Path) -> None:
    server = _build_server(tmp_path)
    client = TestClient(server.app)

    assert client.get("/api/health").status_code == 200
    assert client.post("/api/login", json={}).status_code == 400
    assert client.post("/api/login", json={"password": "bad"}).status_code == 401

    token = _login(client)
    config_resp = client.get("/api/config", headers={"Authorization": f"Bearer {token}"})
    assert config_resp.status_code == 200
    config_payload = config_resp.json()
    assert config_payload["max_file_size_bytes"] == 4 * 1024 * 1024
    assert config_payload["readonly_token"]

    assert (
        client.post("/api/logout", headers={"Authorization": f"Bearer {token}"}).status_code
        == 200
    )
    assert (
        client.get("/api/config", headers={"Authorization": f"Bearer {token}"}).status_code
        == 401
    )


def test_files_route_requires_auth_and_accepts_capability_token(tmp_path: Path) -> None:
    server = _build_server(tmp_path)
    client = TestClient(server.app)

    target = server.media_root / "cats" / "hello.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("hello", encoding="utf-8")

    subject = "cats/hello.txt"
    token = server._issue_capability_token("media", subject, 300)
    wrong_token = server._issue_capability_token("media", "cats/other.txt", 300)

    assert client.get("/files/cats/hello.txt").status_code == 401

    ok = client.get(f"/files/cats/hello.txt?token={token}")
    assert ok.status_code == 200
    assert ok.text == "hello"
    assert ok.headers.get("Accept-Ranges") == "bytes"

    assert client.get(f"/files/cats/hello.txt?token={wrong_token}").status_code == 401
    assert client.get("/files/cats/%2e%2e/%2e%2e/secret.txt").status_code == 400


def test_data_routes_with_token_and_text_preview(tmp_path: Path) -> None:
    server = _build_server(tmp_path, expose_data=True)
    client = TestClient(server.app)

    logs_dir = server.data_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "app.log"
    log_file.write_text("line1\nline2\n", encoding="utf-8")

    bearer = _login(client)
    headers = {"Authorization": f"Bearer {bearer}"}

    tree = client.get("/api/data-tree?path=logs", headers=headers)
    assert tree.status_code == 200
    assert tree.json()["items"][0]["name"] == "app.log"

    text = client.get("/api/data-text?path=logs/app.log", headers=headers)
    assert text.status_code == 200
    payload = text.json()
    assert payload["is_text"] is True
    assert "line1" in payload["content"]

    assert client.get("/api/data-file?path=logs/app.log").status_code == 401
    data_token = server._issue_capability_token("data", "logs/app.log", 300)
    data_file = client.get(f"/api/data-file?path=logs/app.log&token={data_token}")
    assert data_file.status_code == 200
    assert "line1" in data_file.text


def test_data_routes_disabled_returns_forbidden(tmp_path: Path) -> None:
    server = _build_server(tmp_path, expose_data=False)
    client = TestClient(server.app)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/data-tree", headers=headers)
    assert response.status_code == 403


def test_login_rate_limit_after_multiple_failures(
    tmp_path: Path, monkeypatch
) -> None:
    server = _build_server(tmp_path)
    client = TestClient(server.app)

    async def _no_sleep(_seconds: float):
        return None

    monkeypatch.setattr(server_mod.asyncio, "sleep", _no_sleep)

    for _ in range(5):
        resp = client.post("/api/login", json={"password": "wrong"})
        assert resp.status_code == 401

    limited = client.post("/api/login", json={"password": "wrong"})
    assert limited.status_code == 429


def test_data_file_download_header_and_binary_preview(tmp_path: Path) -> None:
    server = _build_server(tmp_path, expose_data=True)
    client = TestClient(server.app)

    logs_dir = server.data_root / "bin"
    logs_dir.mkdir(parents=True, exist_ok=True)
    bin_file = logs_dir / "raw.bin"
    bin_file.write_bytes(b"\x00\x01\x02abc")

    bearer = _login(client)
    headers = {"Authorization": f"Bearer {bearer}"}
    text_resp = client.get("/api/data-text?path=bin/raw.bin", headers=headers)
    assert text_resp.status_code == 200
    assert text_resp.json()["is_text"] is False

    data_token = server._issue_capability_token("data", "bin/raw.bin", 300)
    download_resp = client.get(
        f"/api/data-file?path=bin/raw.bin&token={data_token}&download=1"
    )
    assert download_resp.status_code == 200
    assert "attachment;" in download_resp.headers.get("Content-Disposition", "")


def test_data_text_reports_truncated_for_large_file(tmp_path: Path) -> None:
    server = _build_server(tmp_path, expose_data=True)
    client = TestClient(server.app)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    big_dir = server.data_root / "big"
    big_dir.mkdir(parents=True, exist_ok=True)
    big_file = big_dir / "big.log"
    max_bytes = server_mod.TEXT_PREVIEW_MAX_BYTES
    big_file.write_text("a" * (max_bytes + 100), encoding="utf-8")

    resp = client.get("/api/data-text?path=big/big.log", headers=headers)
    payload = resp.json()

    assert resp.status_code == 200
    assert payload["truncated"] is True
    assert payload["read_bytes"] == max_bytes
    assert payload["is_text"] is True


def test_thumb_route_for_non_image_returns_original_file(tmp_path: Path) -> None:
    server = _build_server(tmp_path)
    client = TestClient(server.app)

    target = server.media_root / "docs" / "note.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("note", encoding="utf-8")
    token = server._issue_capability_token("media", "docs/note.txt", 300)

    resp = client.get(f"/thumb/docs/note.txt?token={token}&size=9999")
    assert resp.status_code == 200
    assert resp.text == "note"
    assert resp.headers.get("Accept-Ranges") == "bytes"
