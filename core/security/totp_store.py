"""TOTP（双因素登录）持久化与运行时校验。

设计要点：

1. 仅落一个文件 ``plugin_data_dir/.totp_state``，与 ``.capability_secret`` 同级，方便备份策略统一过滤；
2. 文件内容是单条 JSON，写入时使用 ``tmp + replace`` 原子化，权限 0600，避免人为复制造成多设备共享 secret 的混乱；
3. 不主动写主 DB，避免 ``index.db`` 备份时夹带 TOTP 密钥；
4. 模块本身**不**直接依赖 ``pyotp``：仅在显式 ``verify_code`` / ``provisioning_uri`` 调用时按需 import，让用户即使没有装 ``requirements-totp.txt`` 也不会触发 import 失败。
"""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from astrbot.api import logger

TOTP_STATE_FILENAME = ".totp_state"
TOTP_RECOVERY_CODE_LENGTH = 8
TOTP_RECOVERY_CODE_COUNT = 8
TOTP_DEFAULT_ISSUER = "Media Portal"
TOTP_DEFAULT_ACCOUNT = "admin"

# 验证码默认窗口 ±1 步（30s），允许时钟漂移
TOTP_VERIFY_WINDOW = 1


def _now() -> float:
    return time.time()


def _generate_recovery_codes(count: int = TOTP_RECOVERY_CODE_COUNT) -> list[str]:
    """生成一批 8 字符 Base32 恢复码。

    取 5 字节随机熵 → Base32 → 截断到 8 字符（足够 40 bits 熵，离线爆破不现实）。
    """
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    codes: list[str] = []
    for _ in range(count):
        code = "".join(secrets.choice(alphabet) for _ in range(TOTP_RECOVERY_CODE_LENGTH))
        codes.append(code)
    return codes


def _hash_recovery_code(code: str) -> str:
    """对恢复码做不可逆摘要，避免文件泄漏即等于明文恢复码。"""
    import hashlib

    normalized = "".join(ch for ch in str(code or "").upper() if ch.isalnum())
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("ascii")).hexdigest()


@dataclass(slots=True)
class TotpState:
    enabled: bool = False
    secret: str = ""
    recovery_hashes: list[str] = field(default_factory=list)
    enrolled_at: float = 0.0
    last_used_at: float = 0.0
    issuer: str = TOTP_DEFAULT_ISSUER
    account: str = TOTP_DEFAULT_ACCOUNT

    def to_payload(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.enabled),
            "secret": str(self.secret or ""),
            "recovery_hashes": list(self.recovery_hashes or []),
            "enrolled_at": float(self.enrolled_at or 0.0),
            "last_used_at": float(self.last_used_at or 0.0),
            "issuer": str(self.issuer or TOTP_DEFAULT_ISSUER),
            "account": str(self.account or TOTP_DEFAULT_ACCOUNT),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "TotpState":
        if not isinstance(payload, dict):
            return cls()
        return cls(
            enabled=bool(payload.get("enabled", False)),
            secret=str(payload.get("secret", "") or ""),
            recovery_hashes=[
                str(item) for item in payload.get("recovery_hashes", []) if str(item)
            ],
            enrolled_at=float(payload.get("enrolled_at", 0) or 0),
            last_used_at=float(payload.get("last_used_at", 0) or 0),
            issuer=str(payload.get("issuer", "") or TOTP_DEFAULT_ISSUER),
            account=str(payload.get("account", "") or TOTP_DEFAULT_ACCOUNT),
        )


class TotpStore:
    """运行时单例：负责加载 / 保存 / 校验 TOTP 状态。"""

    def __init__(
        self,
        state_dir: Path,
        *,
        issuer: str = TOTP_DEFAULT_ISSUER,
        account: str = TOTP_DEFAULT_ACCOUNT,
    ) -> None:
        self._state_dir = Path(state_dir).resolve()
        self._state_path = self._state_dir / TOTP_STATE_FILENAME
        self._lock = asyncio.Lock()
        self._issuer = issuer or TOTP_DEFAULT_ISSUER
        self._account = account or TOTP_DEFAULT_ACCOUNT
        self._state: TotpState = self._load()
        # 待绑定（setup 阶段）的临时 secret 不落盘，仅内存
        self._pending_secret: str | None = None
        self._pending_created_at: float = 0.0

    # ---- 读 ----

    @property
    def state(self) -> TotpState:
        return self._state

    @property
    def enabled(self) -> bool:
        return bool(self._state.enabled and self._state.secret)

    @property
    def has_pending_setup(self) -> bool:
        return bool(self._pending_secret) and (_now() - self._pending_created_at) < 600

    def remaining_recovery_codes(self) -> int:
        return len(self._state.recovery_hashes)

    def public_status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "issuer": self._state.issuer or self._issuer,
            "account": self._state.account or self._account,
            "enrolled_at": self._state.enrolled_at,
            "last_used_at": self._state.last_used_at,
            "remaining_recovery_codes": self.remaining_recovery_codes(),
            "pending_setup": self.has_pending_setup,
        }

    # ---- 内部存取 ----

    def _load(self) -> TotpState:
        if not self._state_path.exists():
            return TotpState(issuer=self._issuer, account=self._account)
        try:
            raw = self._state_path.read_text(encoding="utf-8")
            payload = json.loads(raw)
            state = TotpState.from_payload(payload)
            if not state.issuer:
                state.issuer = self._issuer
            if not state.account:
                state.account = self._account
            return state
        except Exception as exc:
            logger.warning("加载 TOTP 状态失败，将回退到未启用: %s", exc)
            return TotpState(issuer=self._issuer, account=self._account)

    async def _save(self) -> None:
        payload = self._state.to_payload()
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

        def _write() -> None:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            tmp = self._state_path.with_suffix(self._state_path.suffix + ".tmp")
            tmp.write_text(data, encoding="utf-8")
            try:
                os.chmod(tmp, 0o600)
            except Exception:
                pass
            tmp.replace(self._state_path)
            try:
                os.chmod(self._state_path, 0o600)
            except Exception:
                pass

        await asyncio.to_thread(_write)

    # ---- 注册流程 ----

    async def begin_setup(self) -> dict[str, Any]:
        """开始绑定：生成临时 secret（不落盘），返回 otpauth URI。"""
        try:
            import pyotp
        except ImportError as exc:
            raise RuntimeError(
                "未安装 pyotp，请先安装 requirements-totp.txt 中的依赖。"
            ) from exc

        async with self._lock:
            secret = pyotp.random_base32()
            self._pending_secret = secret
            self._pending_created_at = _now()
            issuer = self._state.issuer or self._issuer
            account = self._state.account or self._account
            uri = pyotp.TOTP(secret).provisioning_uri(name=account, issuer_name=issuer)
            return {
                "secret": secret,
                "otpauth_uri": uri,
                "issuer": issuer,
                "account": account,
                "expires_in": 600,
            }

    async def confirm_setup(self, code: str) -> dict[str, Any]:
        """完成绑定：校验当前一次性码 → 持久化 secret + 生成恢复码（明文一次性返回）。"""
        try:
            import pyotp
        except ImportError as exc:
            raise RuntimeError(
                "未安装 pyotp，请先安装 requirements-totp.txt 中的依赖。"
            ) from exc

        async with self._lock:
            pending = self._pending_secret
            if not pending or (_now() - self._pending_created_at) >= 600:
                self._pending_secret = None
                raise ValueError("绑定会话已过期，请重新发起绑定。")
            if not pyotp.TOTP(pending).verify(
                str(code or "").strip(), valid_window=TOTP_VERIFY_WINDOW
            ):
                raise ValueError("验证码错误，请使用最新的 6 位动态码。")

            recovery_codes_plain = _generate_recovery_codes()
            self._state = TotpState(
                enabled=True,
                secret=pending,
                recovery_hashes=[
                    _hash_recovery_code(code) for code in recovery_codes_plain
                ],
                enrolled_at=_now(),
                last_used_at=_now(),
                issuer=self._state.issuer or self._issuer,
                account=self._state.account or self._account,
            )
            self._pending_secret = None
            self._pending_created_at = 0.0
            await self._save()
            return {
                "enabled": True,
                "recovery_codes": recovery_codes_plain,
                "remaining_recovery_codes": len(recovery_codes_plain),
            }

    async def cancel_setup(self) -> None:
        async with self._lock:
            self._pending_secret = None
            self._pending_created_at = 0.0

    async def disable(
        self,
        *,
        code: str | None = None,
        recovery_code: str | None = None,
    ) -> None:
        """关闭 TOTP：要求一次有效的 OTP **或**未用过的恢复码。"""
        async with self._lock:
            if not self.enabled:
                return
            ok = False
            if code:
                ok = await self._verify_code_locked(code)
            if not ok and recovery_code:
                ok = await self._consume_recovery_code_locked(recovery_code)
            if not ok:
                raise ValueError("验证失败，无法关闭 TOTP。")
            self._state = TotpState(
                enabled=False,
                secret="",
                recovery_hashes=[],
                enrolled_at=0.0,
                last_used_at=0.0,
                issuer=self._state.issuer or self._issuer,
                account=self._state.account or self._account,
            )
            await self._save()

    async def regenerate_recovery_codes(self, *, code: str) -> list[str]:
        async with self._lock:
            if not self.enabled:
                raise ValueError("TOTP 未启用。")
            if not await self._verify_code_locked(code):
                raise ValueError("验证码错误。")
            recovery_codes_plain = _generate_recovery_codes()
            self._state.recovery_hashes = [
                _hash_recovery_code(item) for item in recovery_codes_plain
            ]
            self._state.last_used_at = _now()
            await self._save()
            return recovery_codes_plain

    # ---- 登录校验 ----

    async def verify_code(self, code: str) -> bool:
        """登录步骤里使用：成功会更新 last_used_at。"""
        async with self._lock:
            ok = await self._verify_code_locked(code)
            if ok:
                self._state.last_used_at = _now()
                await self._save()
            return ok

    async def consume_recovery_code(self, code: str) -> bool:
        async with self._lock:
            ok = await self._consume_recovery_code_locked(code)
            if ok:
                self._state.last_used_at = _now()
                await self._save()
            return ok

    # ---- 内部 ----

    async def _verify_code_locked(self, code: str) -> bool:
        if not self.enabled:
            return False
        try:
            import pyotp
        except ImportError as exc:
            raise RuntimeError(
                "未安装 pyotp，请先安装 requirements-totp.txt 中的依赖。"
            ) from exc
        token = "".join(ch for ch in str(code or "") if ch.isdigit())
        if len(token) < 6 or len(token) > 8:
            return False
        return bool(pyotp.TOTP(self._state.secret).verify(token, valid_window=TOTP_VERIFY_WINDOW))

    async def _consume_recovery_code_locked(self, code: str) -> bool:
        if not self.enabled or not self._state.recovery_hashes:
            return False
        target = _hash_recovery_code(code)
        if not target:
            return False
        for stored in self._state.recovery_hashes:
            if hmac.compare_digest(target, stored):
                self._state.recovery_hashes = [
                    item for item in self._state.recovery_hashes if not hmac.compare_digest(item, stored)
                ]
                await self._save()
                return True
        return False
