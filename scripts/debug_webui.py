"""独立调试 Media Portal WebUI。

支持在不启动 AstrBot 主程序的情况下，单独运行 WebUI 前后端。

典型用法（在插件根目录下执行）::

    # 1) 最常见 —— 默认 127.0.0.1:7003 / 密码 admin123
    python scripts/debug_webui.py

    # 2) 自定义端口、密码、开放局域网、打开 data 只读浏览
    python scripts/debug_webui.py --host 0.0.0.0 --port 8080 --password mypass --expose-data

    # 3) 开启 Python 代码热重载（需要 pip install watchfiles）
    python scripts/debug_webui.py --reload

    # 4) 指定开发用数据目录（默认 ./.devdata 下）
    python scripts/debug_webui.py --data-dir D:/tmp/mp-dev/plugin --astrbot-data D:/tmp/mp-dev/astrbot

    # 5) 关闭 TOTP（默认开启，方便本地直接体验「设置 → 账号安全」绑定流程）
    python scripts/debug_webui.py --no-totp

说明：
- 前端静态资源（index.html / app.js / styles.css / components/*）均按请求从磁盘读取，
  修改后**刷新浏览器即可生效**，无需重启服务。
- 仅 Python 代码改动需要重启（或使用 ``--reload``）。
- 调试数据默认落在 ``./.devdata/``（已在 .gitignore 排除）；可随时删除。
- 调试模式下 ``webui.totp_enabled`` 默认开启；首次启用 TOTP 前需要 ``pip install -r requirements-totp.txt``。
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import socket
import sys
import types
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 路径解析 —— 保证无论从哪里被加载，都能以
# ``astrbot_plugin_media_portal.*`` 的包路径正确导入本插件模块。
# ---------------------------------------------------------------------------

_THIS_FILE = Path(__file__).resolve()
PLUGIN_ROOT: Path = _THIS_FILE.parent.parent
PACKAGE_PARENT: Path = PLUGIN_ROOT.parent
PACKAGE_NAME: str = PLUGIN_ROOT.name

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))


# ---------------------------------------------------------------------------
# astrbot shim —— 在真正导入插件模块之前，必须先安装最小可用的 ``astrbot.*``
# 占位模块，否则 ``from astrbot.api import logger`` 等语句会直接抛 ImportError。
# ---------------------------------------------------------------------------


def _install_astrbot_shims() -> None:
    existing_api = sys.modules.get("astrbot.api")
    if existing_api is not None and hasattr(existing_api, "logger"):
        return

    debug_logger = logging.getLogger("astrbot.media_portal.debug")
    if not debug_logger.handlers:
        handler = logging.StreamHandler(stream=sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        debug_logger.addHandler(handler)
    debug_logger.setLevel(
        logging.DEBUG if os.environ.get("MP_DEBUG_VERBOSE") == "1" else logging.INFO
    )
    debug_logger.propagate = False

    def _mk(name: str) -> types.ModuleType:
        mod = sys.modules.get(name)
        if mod is None:
            mod = types.ModuleType(name)
            sys.modules[name] = mod
        return mod

    astrbot = _mk("astrbot")
    astrbot_api = _mk("astrbot.api")
    astrbot_api.logger = debug_logger  # type: ignore[attr-defined]
    astrbot.api = astrbot_api  # type: ignore[attr-defined]

    astrbot_core = _mk("astrbot.core")
    astrbot.core = astrbot_core  # type: ignore[attr-defined]

    core_utils = _mk("astrbot.core.utils")
    astrbot_core.utils = core_utils  # type: ignore[attr-defined]

    io_mod = _mk("astrbot.core.utils.io")

    def _get_local_ip_addresses() -> list[str]:
        ips: list[str] = []
        try:
            hostname = socket.gethostname()
            for info in socket.getaddrinfo(hostname, None):
                addr = info[4][0]
                if not addr or addr in ips:
                    continue
                if addr.startswith("127.") or addr == "::1":
                    continue
                ips.append(addr)
        except Exception:
            return []
        return ips

    io_mod.get_local_ip_addresses = _get_local_ip_addresses  # type: ignore[attr-defined]
    core_utils.io = io_mod  # type: ignore[attr-defined]

    path_mod = _mk("astrbot.core.utils.astrbot_path")

    def _get_astrbot_data_path() -> str:
        override = os.environ.get("MP_DEBUG_ASTRBOT_DATA", "").strip()
        if override:
            return str(Path(override).expanduser().resolve())
        return str((PLUGIN_ROOT / ".devdata" / "astrbot").resolve())

    path_mod.get_astrbot_data_path = _get_astrbot_data_path  # type: ignore[attr-defined]
    core_utils.astrbot_path = path_mod  # type: ignore[attr-defined]


_install_astrbot_shims()


# ---------------------------------------------------------------------------
# Shim 安装完成后才能安全地导入插件代码
# ---------------------------------------------------------------------------

from astrbot_plugin_media_portal.core import (  # noqa: E402  (必须后置)
    CategoryManager,
    MediaDownloader,
    MediaManager,
    load_plugin_settings,
)
from astrbot_plugin_media_portal.core.intelligence import (  # noqa: E402
    IntelligenceManager,
)
from astrbot_plugin_media_portal.webui import WebUIServer  # noqa: E402


# ---------------------------------------------------------------------------
# 配置装配
# ---------------------------------------------------------------------------


def _build_raw_config(
    *,
    host: str,
    port: int,
    password: str,
    session_timeout: int,
    public_base_url: str,
    expose_data: bool,
    allowed_origins: list[str],
    totp_enabled: bool,
    totp_issuer: str,
    totp_account: str,
    intelligence_enabled: bool,
    clip_enabled: bool,
    face_enabled: bool,
    hf_mirror_url: str,
    max_concurrent_downloads: int,
) -> dict[str, Any]:
    return {
        "webui": {
            "enabled": True,
            "host": host,
            "port": port,
            "access_password": password,
            "session_timeout": session_timeout,
            "public_base_url": public_base_url,
            "expose_astrbot_data": expose_data,
            "allowed_origins": allowed_origins,
            "readonly_token_ttl": max(session_timeout, 3600),
            "share_url_ttl": max(session_timeout, 3600),
            "data_token_ttl": max(session_timeout, 3600),
            "totp_enabled": totp_enabled,
            "totp_issuer": totp_issuer,
            "totp_account": totp_account,
        },
        "storage": {"location_mode": "plugin_data"},
        "downloader": {
            "max_file_size_mb": 500,
            "allowed_kinds": ["image", "video", "audio"],
            "default_move_local": True,
        },
        "intelligence": {
            "enabled": intelligence_enabled,
            "clip_enabled": clip_enabled,
            "face_enabled": face_enabled,
            "hf_mirror_url": hf_mirror_url,
            "max_concurrent_downloads": max_concurrent_downloads,
        },
    }


def _resolve_dev_paths(data_dir: str, astrbot_data: str) -> tuple[Path, Path]:
    plugin_data = Path(data_dir).expanduser().resolve() if data_dir else (
        PLUGIN_ROOT / ".devdata" / "plugin"
    ).resolve()
    astrbot_data_path = (
        Path(astrbot_data).expanduser().resolve()
        if astrbot_data
        else (PLUGIN_ROOT / ".devdata" / "astrbot").resolve()
    )
    plugin_data.mkdir(parents=True, exist_ok=True)
    astrbot_data_path.mkdir(parents=True, exist_ok=True)
    (astrbot_data_path / "media").mkdir(parents=True, exist_ok=True)
    return plugin_data, astrbot_data_path


def _build_server(
    args: argparse.Namespace,
) -> tuple[WebUIServer, MediaManager, IntelligenceManager]:
    plugin_data, astrbot_data = _resolve_dev_paths(args.data_dir, args.astrbot_data)
    os.environ["MP_DEBUG_ASTRBOT_DATA"] = str(astrbot_data)

    raw_config = _build_raw_config(
        host=args.host,
        port=args.port,
        password=args.password,
        session_timeout=args.session_timeout,
        public_base_url=args.public_base_url,
        expose_data=bool(args.expose_data),
        allowed_origins=[o for o in (args.allowed_origins or "").split(",") if o.strip()],
        totp_enabled=bool(getattr(args, "totp_enabled", True)),
        totp_issuer=str(getattr(args, "totp_issuer", "Media Portal (Debug)")),
        totp_account=str(getattr(args, "totp_account", "debug-admin")),
        intelligence_enabled=bool(getattr(args, "intelligence_enabled", False)),
        clip_enabled=bool(getattr(args, "clip_enabled", False)),
        face_enabled=bool(getattr(args, "face_enabled", False)),
        hf_mirror_url=str(getattr(args, "hf_mirror", "") or ""),
        max_concurrent_downloads=int(getattr(args, "max_concurrent_downloads", 1) or 1),
    )
    settings = load_plugin_settings(raw_config, plugin_data_dir=plugin_data)

    category_manager = CategoryManager(
        categories_file=settings.plugin_data_dir / "categories.json",
        media_root=settings.media_root,
    )
    downloader = MediaDownloader(
        temp_dir=settings.plugin_data_dir / "temp",
        max_file_size_mb=settings.downloader.max_file_size_mb,
    )
    media_manager = MediaManager(
        media_root=settings.media_root,
        plugin_data_dir=settings.plugin_data_dir,
        category_manager=category_manager,
        downloader=downloader,
        allowed_kinds=settings.downloader.allowed_kinds,
        max_file_size_mb=settings.downloader.max_file_size_mb,
        default_move_local=settings.downloader.default_move_local,
    )
    intelligence_manager = IntelligenceManager(
        plugin_data_dir=settings.plugin_data_dir,
        feature_enabled=settings.intelligence.enabled,
        clip_enabled=settings.intelligence.clip_enabled,
        face_enabled=settings.intelligence.face_enabled,
        hf_mirror_url=settings.intelligence.hf_mirror_url,
        max_concurrent_downloads=settings.intelligence.max_concurrent_downloads,
    )
    server = WebUIServer(
        media_manager=media_manager,
        category_manager=category_manager,
        config=raw_config["webui"],
        data_root=settings.astrbot_data_dir,
        intelligence_manager=intelligence_manager,
    )
    return server, media_manager, intelligence_manager


async def _prepare_server(media_manager: MediaManager) -> None:
    await media_manager.initialize()
    await media_manager.ensure_scanned()


def _print_banner(server: WebUIServer, args: argparse.Namespace) -> None:
    bar = "=" * 64
    print(bar)
    print("  Media Portal WebUI  (standalone debug)")
    print(bar)
    print(f"  Local URL      : http://{args.host}:{args.port}")
    for url in server.get_access_urls():
        if url.endswith(f":{args.port}") and url not in {
            f"http://{args.host}:{args.port}"
        }:
            print(f"  LAN URL        : {url}")
    print(f"  Password       : {server.access_password}")
    if server.password_generated:
        print("                   (auto-generated; use --password to pin)")
    print(f"  Media root     : {server.media_root}")
    print(f"  Plugin data    : {server.media_manager.plugin_data_dir}")
    print(f"  AstrBot data   : {server.data_root}")
    print(f"  Expose data    : {server.expose_astrbot_data}")
    totp_state = "on" if server.totp_feature_enabled else "off"
    if server.totp_feature_enabled:
        if server.totp_active:
            totp_state = "on (bound)"
        else:
            totp_state = "on (not yet bound — open Settings → Account security)"
    print(f"  TOTP feature   : {totp_state}")
    if server.totp_feature_enabled:
        try:
            import pyotp  # noqa: F401
            import qrcode  # noqa: F401
        except ImportError:
            print(
                "  [warn]         pyotp / qrcode missing — run "
                "`pip install -r requirements-totp.txt` to enable bind / verify."
            )
    print(bar)
    print("  Ctrl+C to stop. Frontend edits hot-reload without restart.")
    print(bar)


# ---------------------------------------------------------------------------
# 运行模式 1：直连 —— 复用 WebUIServer.start() 的原生生命周期
# ---------------------------------------------------------------------------


async def _run_forever(args: argparse.Namespace) -> None:
    server, media_manager, intelligence_manager = _build_server(args)
    await _prepare_server(media_manager)
    _print_banner(server, args)
    await server.start()
    stop_event = asyncio.Event()
    try:
        await stop_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        await server.stop()
        with contextlib.suppress(Exception):
            await intelligence_manager.shutdown()
        await media_manager.close()


# ---------------------------------------------------------------------------
# 运行模式 2：uvicorn --reload 工厂 —— 供 ``--reload`` 使用
# ---------------------------------------------------------------------------


def _args_from_env() -> argparse.Namespace:
    return argparse.Namespace(
        host=os.environ.get("MP_DEBUG_HOST", "127.0.0.1"),
        port=int(os.environ.get("MP_DEBUG_PORT", "7003")),
        password=os.environ.get("MP_DEBUG_PASSWORD", "admin123"),
        data_dir=os.environ.get("MP_DEBUG_DATA_DIR", ""),
        astrbot_data=os.environ.get("MP_DEBUG_ASTRBOT_DATA_ARG", ""),
        expose_data=os.environ.get("MP_DEBUG_EXPOSE_DATA", "0") == "1",
        session_timeout=int(os.environ.get("MP_DEBUG_SESSION_TIMEOUT", "86400")),
        public_base_url=os.environ.get("MP_DEBUG_PUBLIC_BASE_URL", ""),
        allowed_origins=os.environ.get("MP_DEBUG_ALLOWED_ORIGINS", ""),
        totp_enabled=os.environ.get("MP_DEBUG_TOTP_ENABLED", "1") == "1",
        totp_issuer=os.environ.get("MP_DEBUG_TOTP_ISSUER", "Media Portal (Debug)"),
        totp_account=os.environ.get("MP_DEBUG_TOTP_ACCOUNT", "debug-admin"),
        intelligence_enabled=os.environ.get("MP_DEBUG_INTELLIGENCE_ENABLED", "0") == "1",
        clip_enabled=os.environ.get("MP_DEBUG_CLIP_ENABLED", "0") == "1",
        face_enabled=os.environ.get("MP_DEBUG_FACE_ENABLED", "0") == "1",
        hf_mirror=os.environ.get("MP_DEBUG_HF_MIRROR", ""),
        max_concurrent_downloads=int(
            os.environ.get("MP_DEBUG_INTELLIGENCE_MAX_CONCURRENT", "1") or "1"
        ),
    )


def create_app():
    """uvicorn 工厂函数，供 ``--reload`` 模式使用。"""
    args = _args_from_env()
    server, media_manager, intelligence_manager = _build_server(args)

    app = server.app
    _print_banner(server, args)

    previous_lifespan = app.router.lifespan_context

    @contextlib.asynccontextmanager
    async def _lifespan(_app):
        async with previous_lifespan(_app):
            await _prepare_server(media_manager)
            server._cleanup_task = asyncio.create_task(server._periodic_cleanup())
            try:
                yield
            finally:
                task = getattr(server, "_cleanup_task", None)
                if task and not task.done():
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await task
                with contextlib.suppress(Exception):
                    await intelligence_manager.shutdown()
                await media_manager.close()

    app.router.lifespan_context = _lifespan

    return app


def _run_with_reload(args: argparse.Namespace) -> None:
    try:
        import uvicorn  # noqa: F401
    except ImportError as exc:
        print(f"[debug_webui] uvicorn 未安装: {exc}")
        sys.exit(1)

    try:
        import watchfiles  # noqa: F401
    except ImportError:
        print(
            "[debug_webui] 未检测到 watchfiles，无法启用 --reload。\n"
            "              请先执行: pip install watchfiles"
        )
        sys.exit(1)

    os.environ["MP_DEBUG_HOST"] = args.host
    os.environ["MP_DEBUG_PORT"] = str(args.port)
    os.environ["MP_DEBUG_PASSWORD"] = args.password
    os.environ["MP_DEBUG_DATA_DIR"] = args.data_dir or ""
    os.environ["MP_DEBUG_ASTRBOT_DATA_ARG"] = args.astrbot_data or ""
    os.environ["MP_DEBUG_EXPOSE_DATA"] = "1" if args.expose_data else "0"
    os.environ["MP_DEBUG_SESSION_TIMEOUT"] = str(args.session_timeout)
    os.environ["MP_DEBUG_PUBLIC_BASE_URL"] = args.public_base_url or ""
    os.environ["MP_DEBUG_ALLOWED_ORIGINS"] = args.allowed_origins or ""
    os.environ["MP_DEBUG_TOTP_ENABLED"] = "1" if args.totp_enabled else "0"
    os.environ["MP_DEBUG_TOTP_ISSUER"] = args.totp_issuer or "Media Portal (Debug)"
    os.environ["MP_DEBUG_TOTP_ACCOUNT"] = args.totp_account or "debug-admin"
    os.environ["MP_DEBUG_INTELLIGENCE_ENABLED"] = (
        "1" if getattr(args, "intelligence_enabled", False) else "0"
    )
    os.environ["MP_DEBUG_CLIP_ENABLED"] = (
        "1" if getattr(args, "clip_enabled", False) else "0"
    )
    os.environ["MP_DEBUG_FACE_ENABLED"] = (
        "1" if getattr(args, "face_enabled", False) else "0"
    )
    os.environ["MP_DEBUG_HF_MIRROR"] = str(getattr(args, "hf_mirror", "") or "")
    os.environ["MP_DEBUG_INTELLIGENCE_MAX_CONCURRENT"] = str(
        int(getattr(args, "max_concurrent_downloads", 1) or 1)
    )
    existing_pythonpath = os.environ.get("PYTHONPATH", "")
    parent_str = str(PACKAGE_PARENT)
    if parent_str not in existing_pythonpath.split(os.pathsep):
        os.environ["PYTHONPATH"] = (
            parent_str + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
        )

    import uvicorn

    uvicorn.run(
        f"{PACKAGE_NAME}.scripts.debug_webui:create_app",
        host=args.host,
        port=args.port,
        factory=True,
        reload=True,
        reload_dirs=[
            str(PLUGIN_ROOT / "webui"),
            str(PLUGIN_ROOT / "core"),
            str(PLUGIN_ROOT / "scripts"),
        ],
        log_level="info",
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="debug_webui",
        description="独立调试 Media Portal WebUI（无需 AstrBot 主程序）",
    )
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认 127.0.0.1")
    parser.add_argument("--port", type=int, default=7003, help="监听端口，默认 7003")
    parser.add_argument(
        "--password",
        default="admin123",
        help="访问密码，默认 admin123（仅用于本地调试，勿用于生产）",
    )
    parser.add_argument(
        "--data-dir",
        default="",
        help="插件数据目录，默认 ./.devdata/plugin",
    )
    parser.add_argument(
        "--astrbot-data",
        default="",
        help="模拟的 AstrBot 数据根目录，默认 ./.devdata/astrbot",
    )
    parser.add_argument(
        "--expose-data",
        action="store_true",
        help="开启 /data 只读浏览（用于测试 Data 页面）",
    )
    parser.add_argument(
        "--public-base-url",
        default="",
        help="外部访问基础 URL（可选），设置后会参与生成分享链接",
    )
    parser.add_argument(
        "--session-timeout",
        type=int,
        default=86400,
        help="会话超时秒数，默认 86400（调试期使用长会话，方便反复刷新）",
    )
    parser.add_argument(
        "--allowed-origins",
        default="",
        help="允许的 CORS Origin，逗号分隔",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="启用 Python 代码热重载（需 watchfiles；修改 core/webui 的 .py 后自动重启）",
    )
    totp_group = parser.add_mutually_exclusive_group()
    totp_group.add_argument(
        "--totp",
        dest="totp_enabled",
        action="store_true",
        default=True,
        help="启用 TOTP 双因素登录开关（默认开启，可在「设置 → 账号安全」中绑定）",
    )
    totp_group.add_argument(
        "--no-totp",
        dest="totp_enabled",
        action="store_false",
        help="关闭 TOTP 双因素登录开关（仅密码登录）",
    )
    parser.add_argument(
        "--totp-issuer",
        default="Media Portal (Debug)",
        help="TOTP otpauth:// 发行方名称（写入二维码）",
    )
    parser.add_argument(
        "--totp-account",
        default="debug-admin",
        help="TOTP otpauth:// 账号名（在 Authenticator 中显示）",
    )
    intel_group = parser.add_mutually_exclusive_group()
    intel_group.add_argument(
        "--intelligence",
        dest="intelligence_enabled",
        action="store_true",
        default=False,
        help="启用智能能力总开关（CLIP / 人脸子能力仍需各自开启）",
    )
    intel_group.add_argument(
        "--no-intelligence",
        dest="intelligence_enabled",
        action="store_false",
        help="关闭智能能力总开关（默认）",
    )
    parser.add_argument(
        "--clip",
        dest="clip_enabled",
        action="store_true",
        default=False,
        help="启用 CLIP 子能力（仅决定 UI 标记，模型仍需手动下载）",
    )
    parser.add_argument(
        "--face",
        dest="face_enabled",
        action="store_true",
        default=False,
        help="启用人脸子能力（仅决定 UI 标记，模型仍需手动下载）",
    )
    parser.add_argument(
        "--hf-mirror",
        dest="hf_mirror",
        default="",
        help="HuggingFace 镜像 URL（空表示直连，例如 https://hf-mirror.com）",
    )
    parser.add_argument(
        "--intelligence-max-concurrent",
        dest="max_concurrent_downloads",
        type=int,
        default=1,
        help="智能模型并发下载数（1~3，默认 1）",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.reload:
        _run_with_reload(args)
        return
    try:
        asyncio.run(_run_forever(args))
    except KeyboardInterrupt:
        print("\n[debug_webui] interrupted, bye.")


if __name__ == "__main__":
    main()
