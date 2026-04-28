"""TotpStore 单元测试。

覆盖范围：
1. 初始状态 / public_status 字段；
2. begin_setup → confirm_setup（错误码拒绝、正确码绑定）；
3. verify_code 成功与失败；
4. consume_recovery_code 一次性 + 不可重复；
5. regenerate_recovery_codes 后旧码失效、新码可用；
6. disable 支持 OTP 与恢复码；
7. 状态文件被加载后跨实例一致；
8. cancel_setup 清空临时 secret。

注意：``pyotp`` 是可选依赖；模块顶部按需 import。若运行环境缺少则整个文件 skip。
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

pyotp = pytest.importorskip("pyotp")

from astrbot_plugin_media_portal.core.security.totp_store import (
    TOTP_STATE_FILENAME,
    TotpState,
    TotpStore,
)


def _run(coro):
    return asyncio.run(coro)


def _make_store(tmp_path: Path) -> TotpStore:
    state_dir = tmp_path / "plugin_data"
    state_dir.mkdir(parents=True, exist_ok=True)
    return TotpStore(state_dir, issuer="MediaPortalTest", account="alice")


def test_initial_status_is_disabled(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    assert store.enabled is False
    assert store.has_pending_setup is False
    status = store.public_status()
    assert status["enabled"] is False
    assert status["issuer"] == "MediaPortalTest"
    assert status["account"] == "alice"
    assert status["remaining_recovery_codes"] == 0
    assert status["pending_setup"] is False


def test_begin_setup_returns_provisioning_uri(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    payload = _run(store.begin_setup())
    assert set(payload.keys()) >= {"secret", "otpauth_uri", "issuer", "account", "expires_in"}
    assert payload["issuer"] == "MediaPortalTest"
    assert payload["account"] == "alice"
    assert payload["otpauth_uri"].startswith("otpauth://totp/")
    assert "secret=" in payload["otpauth_uri"]
    assert store.has_pending_setup is True


def test_confirm_setup_rejects_wrong_code_and_accepts_valid(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    payload = _run(store.begin_setup())
    secret = payload["secret"]

    with pytest.raises(ValueError):
        _run(store.confirm_setup("000000"))

    code = pyotp.TOTP(secret).now()
    confirm = _run(store.confirm_setup(code))
    assert confirm["enabled"] is True
    assert confirm["remaining_recovery_codes"] == 8
    assert len(confirm["recovery_codes"]) == 8
    assert all(len(c) == 8 for c in confirm["recovery_codes"])

    assert store.enabled is True
    assert store.has_pending_setup is False


def test_state_file_is_persisted_and_chmod_600(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    payload = _run(store.begin_setup())
    secret = payload["secret"]
    _run(store.confirm_setup(pyotp.TOTP(secret).now()))

    state_path = tmp_path / "plugin_data" / TOTP_STATE_FILENAME
    assert state_path.exists()
    raw = json.loads(state_path.read_text(encoding="utf-8"))
    assert raw["enabled"] is True
    assert raw["secret"] == secret
    assert raw["issuer"] == "MediaPortalTest"
    assert isinstance(raw["recovery_hashes"], list) and len(raw["recovery_hashes"]) == 8
    if os.name == "posix":
        mode = state_path.stat().st_mode & 0o777
        assert mode == 0o600


def test_state_loaded_from_disk_keeps_enabled(tmp_path: Path) -> None:
    s1 = _make_store(tmp_path)
    secret = _run(s1.begin_setup())["secret"]
    _run(s1.confirm_setup(pyotp.TOTP(secret).now()))

    s2 = _make_store(tmp_path)
    assert s2.enabled is True
    assert s2.state.secret == secret
    assert s2.remaining_recovery_codes() == 8


def test_verify_code_accepts_current_and_rejects_invalid(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    secret = _run(store.begin_setup())["secret"]
    _run(store.confirm_setup(pyotp.TOTP(secret).now()))

    assert _run(store.verify_code(pyotp.TOTP(secret).now())) is True
    assert _run(store.verify_code("000000")) is False
    assert _run(store.verify_code("")) is False


def test_recovery_code_is_one_shot(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    secret = _run(store.begin_setup())["secret"]
    confirm = _run(store.confirm_setup(pyotp.TOTP(secret).now()))
    rc = confirm["recovery_codes"][0]

    assert _run(store.consume_recovery_code(rc)) is True
    assert store.remaining_recovery_codes() == 7
    assert _run(store.consume_recovery_code(rc)) is False
    assert _run(store.consume_recovery_code("INVALID0")) is False


def test_regenerate_invalidates_old_recovery_codes(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    secret = _run(store.begin_setup())["secret"]
    confirm = _run(store.confirm_setup(pyotp.TOTP(secret).now()))
    old_codes = confirm["recovery_codes"]

    new_codes = _run(store.regenerate_recovery_codes(code=pyotp.TOTP(secret).now()))
    assert len(new_codes) == 8
    assert set(new_codes).isdisjoint(old_codes), "新旧恢复码不应重叠"

    # 旧码应全部失效
    for code in old_codes:
        assert _run(store.consume_recovery_code(code)) is False

    # 新码可用一次
    assert _run(store.consume_recovery_code(new_codes[0])) is True


def test_regenerate_requires_valid_otp(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    secret = _run(store.begin_setup())["secret"]
    _run(store.confirm_setup(pyotp.TOTP(secret).now()))

    with pytest.raises(ValueError):
        _run(store.regenerate_recovery_codes(code="000000"))


def test_disable_with_otp_and_with_recovery(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    secret = _run(store.begin_setup())["secret"]
    confirm = _run(store.confirm_setup(pyotp.TOTP(secret).now()))

    _run(store.disable(code=pyotp.TOTP(secret).now()))
    assert store.enabled is False
    assert store.remaining_recovery_codes() == 0

    # Re-enable to verify recovery-code disable path
    secret2 = _run(store.begin_setup())["secret"]
    confirm2 = _run(store.confirm_setup(pyotp.TOTP(secret2).now()))
    rc = confirm2["recovery_codes"][0]
    _run(store.disable(recovery_code=rc))
    assert store.enabled is False


def test_disable_rejects_when_neither_provided(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    secret = _run(store.begin_setup())["secret"]
    _run(store.confirm_setup(pyotp.TOTP(secret).now()))

    with pytest.raises(ValueError):
        _run(store.disable())
    assert store.enabled is True


def test_cancel_setup_clears_pending_secret(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    _run(store.begin_setup())
    assert store.has_pending_setup is True
    _run(store.cancel_setup())
    assert store.has_pending_setup is False

    with pytest.raises(ValueError):
        _run(store.confirm_setup("000000"))


def test_state_corrupt_falls_back_to_disabled(tmp_path: Path) -> None:
    state_dir = tmp_path / "plugin_data"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / TOTP_STATE_FILENAME).write_text("{not json", encoding="utf-8")

    store = TotpStore(state_dir, issuer="MediaPortalTest", account="alice")
    assert store.enabled is False
    # 损坏文件不应抛出，且 issuer / account 退回构造参数
    assert store.state.issuer == "MediaPortalTest"
    assert store.state.account == "alice"


def test_totp_state_payload_roundtrip() -> None:
    state = TotpState(
        enabled=True,
        secret="ABCDEFGH",
        recovery_hashes=["a" * 64, "b" * 64],
        enrolled_at=1.0,
        last_used_at=2.0,
        issuer="X",
        account="y",
    )
    payload = state.to_payload()
    assert payload["enabled"] is True
    restored = TotpState.from_payload(payload)
    assert restored == state
