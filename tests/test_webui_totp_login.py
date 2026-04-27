"""TOTP 双因素登录的端到端 webui 测试。

只覆盖 ``server.py`` 中新增的两步登录与账号 / TOTP 路由，
不重复 ``test_totp_store.py`` 里对存储层的细节断言。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pyotp = pytest.importorskip("pyotp")

from astrbot_plugin_media_portal.webui.server import WebUIServer


class _DummyDownloader:
    def __init__(self, temp_dir: Path) -> None:
        self.temp_dir = temp_dir


class _MediaManager:
    def __init__(self, media_root: Path, plugin_data_dir: Path) -> None:
        self.media_root = media_root
        self.plugin_data_dir = plugin_data_dir
        self.downloader = _DummyDownloader(plugin_data_dir / "temp")
        self.max_file_size = 4 * 1024 * 1024


class _CategoryManager:
    pass


def _build_server(tmp_path: Path, *, totp_enabled: bool) -> WebUIServer:
    media_root = (tmp_path / "media").resolve()
    plugin_data_dir = (tmp_path / "plugin_data").resolve()
    data_root = (tmp_path / "astrbot_data").resolve()
    for path in (media_root, plugin_data_dir, data_root):
        path.mkdir(parents=True, exist_ok=True)
    return WebUIServer(
        media_manager=_MediaManager(media_root, plugin_data_dir),
        category_manager=_CategoryManager(),
        config={
            "enabled": True,
            "host": "127.0.0.1",
            "port": 7003,
            "access_password": "secret-pw",
            "session_timeout": 3600,
            "public_base_url": "",
            "expose_astrbot_data": False,
            "allowed_origins": [],
            "readonly_token_ttl": 3600,
            "share_url_ttl": 3600,
            "data_token_ttl": 3600,
            "totp_enabled": totp_enabled,
            "totp_issuer": "MediaPortalTest",
            "totp_account": "operator",
        },
        data_root=data_root,
    )


def _enable_totp(server: WebUIServer) -> tuple[str, list[str]]:
    """直接走 store API 完成绑定，避免还需要走 webui 设置流程。"""
    import asyncio

    async def _go() -> tuple[str, list[str]]:
        info = await server._totp_store.begin_setup()
        secret = info["secret"]
        confirm = await server._totp_store.confirm_setup(pyotp.TOTP(secret).now())
        return secret, confirm["recovery_codes"]

    return asyncio.run(_go())


def test_totp_disabled_login_returns_session_token(tmp_path: Path) -> None:
    server = _build_server(tmp_path, totp_enabled=False)
    client = TestClient(server.app)
    resp = client.post("/api/login", json={"password": "secret-pw"})
    assert resp.status_code == 200
    body = resp.json()
    assert "token" in body
    assert "challenge" not in body


def test_login_config_exposes_totp_flags(tmp_path: Path) -> None:
    server = _build_server(tmp_path, totp_enabled=True)
    client = TestClient(server.app)
    token = client.post("/api/login", json={"password": "secret-pw"}).json()["token"]
    cfg = client.get("/api/config", headers={"Authorization": f"Bearer {token}"}).json()
    assert cfg["totp_feature_enabled"] is True
    # not yet bound, so totp_active should be False
    assert cfg["totp_active"] is False


def test_two_step_login_with_totp(tmp_path: Path) -> None:
    server = _build_server(tmp_path, totp_enabled=True)
    secret, recovery_codes = _enable_totp(server)
    assert server.totp_active is True
    client = TestClient(server.app)

    # Step 1: password only -> challenge
    step1 = client.post("/api/login", json={"password": "secret-pw"})
    assert step1.status_code == 200
    payload = step1.json()
    assert payload["challenge"] == "totp"
    assert payload["challenge_token"]
    assert "token" not in payload

    # Step 2 (wrong code) -> 401
    bad = client.post(
        "/api/login/totp",
        json={"challenge_token": payload["challenge_token"], "code": "000000"},
    )
    assert bad.status_code == 401

    # Step 2 (correct code) -> session token
    good_code = pyotp.TOTP(secret).now()
    ok = client.post(
        "/api/login/totp",
        json={"challenge_token": payload["challenge_token"], "code": good_code},
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["token"]

    # Test recovery code path on a fresh challenge
    step1b = client.post("/api/login", json={"password": "secret-pw"}).json()
    rc_resp = client.post(
        "/api/login/totp",
        json={
            "challenge_token": step1b["challenge_token"],
            "recovery_code": recovery_codes[0],
        },
    )
    assert rc_resp.status_code == 200
    assert rc_resp.json()["token"]


def test_totp_login_rejects_wrong_password_at_step1(tmp_path: Path) -> None:
    server = _build_server(tmp_path, totp_enabled=True)
    _enable_totp(server)
    client = TestClient(server.app)
    resp = client.post("/api/login", json={"password": "wrong"})
    assert resp.status_code == 401


def test_totp_login_rejects_invalid_challenge_token(tmp_path: Path) -> None:
    server = _build_server(tmp_path, totp_enabled=True)
    _enable_totp(server)
    client = TestClient(server.app)
    resp = client.post(
        "/api/login/totp",
        json={"challenge_token": "not-a-real-token", "code": "123456"},
    )
    assert resp.status_code == 401


def test_account_totp_setup_confirm_and_disable(tmp_path: Path) -> None:
    server = _build_server(tmp_path, totp_enabled=True)
    client = TestClient(server.app)
    token = client.post("/api/login", json={"password": "secret-pw"}).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    status = client.get("/api/account/totp/status", headers=headers).json()
    assert status["enabled"] is False
    assert status["feature_enabled"] is True

    setup = client.post("/api/account/totp/setup", headers=headers).json()
    assert setup["secret"]
    assert setup["otpauth_uri"].startswith("otpauth://totp/")
    assert setup["qrcode_svg"]  # SVG fallback always present
    secret = setup["secret"]

    # 错误码应返回 4xx
    bad = client.post(
        "/api/account/totp/confirm", headers=headers, json={"code": "000000"}
    )
    assert bad.status_code in (400, 422)

    confirm = client.post(
        "/api/account/totp/confirm",
        headers=headers,
        json={"code": pyotp.TOTP(secret).now()},
    )
    assert confirm.status_code == 200, confirm.text
    body = confirm.json()
    assert body["enabled"] is True
    assert len(body["recovery_codes"]) == 8

    status_after = client.get("/api/account/totp/status", headers=headers).json()
    assert status_after["enabled"] is True
    assert status_after["remaining_recovery_codes"] == 8

    # disable with current OTP
    disabled = client.post(
        "/api/account/totp/disable",
        headers=headers,
        json={"code": pyotp.TOTP(secret).now()},
    )
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False


def test_account_totp_regenerate_recovery_requires_otp(tmp_path: Path) -> None:
    server = _build_server(tmp_path, totp_enabled=True)
    secret, _ = _enable_totp(server)
    client = TestClient(server.app)
    token = client.post(
        "/api/login/totp",
        json={
            "challenge_token": client.post(
                "/api/login", json={"password": "secret-pw"}
            ).json()["challenge_token"],
            "code": pyotp.TOTP(secret).now(),
        },
    ).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    bad = client.post(
        "/api/account/totp/regenerate-recovery",
        headers=headers,
        json={"code": "000000"},
    )
    assert bad.status_code in (400, 422)

    ok = client.post(
        "/api/account/totp/regenerate-recovery",
        headers=headers,
        json={"code": pyotp.TOTP(secret).now()},
    )
    assert ok.status_code == 200
    assert len(ok.json()["recovery_codes"]) == 8
