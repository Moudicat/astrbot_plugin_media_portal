from __future__ import annotations

import asyncio
import logging
import sys
import types
from pathlib import Path
from types import SimpleNamespace


def _install_main_import_shims() -> None:
    # astrbot.api
    astrbot_module = sys.modules.get("astrbot")
    if astrbot_module is None:
        astrbot_module = types.ModuleType("astrbot")
        sys.modules["astrbot"] = astrbot_module

    api_module = sys.modules.get("astrbot.api")
    if api_module is None:
        api_module = types.ModuleType("astrbot.api")
        sys.modules["astrbot.api"] = api_module
        setattr(astrbot_module, "api", api_module)
    if not hasattr(api_module, "logger"):
        api_module.logger = logging.getLogger("astrbot.test.main")
    if not hasattr(api_module, "llm_tool"):
        api_module.llm_tool = lambda *args, **kwargs: (  # type: ignore[attr-defined]
            lambda func: func
        )

    # astrbot.api.message_components
    comp_module = sys.modules.get("astrbot.api.message_components")
    if comp_module is None:
        comp_module = types.ModuleType("astrbot.api.message_components")
        sys.modules["astrbot.api.message_components"] = comp_module

        class Plain:
            def __init__(self, text: str):
                self.text = text

        class File:
            def __init__(self, file: str, name: str = ""):
                self.file = file
                self.name = name

        class Image:
            @staticmethod
            def fromFileSystem(path: str):
                return {"kind": "image", "path": path}

        class Video:
            @staticmethod
            def fromFileSystem(path: str):
                return {"kind": "video", "path": path}

        class Record:
            @staticmethod
            def fromFileSystem(path: str):
                return {"kind": "audio", "path": path}

        comp_module.Plain = Plain
        comp_module.File = File
        comp_module.Image = Image
        comp_module.Video = Video
        comp_module.Record = Record

    # astrbot.api.event
    event_module = sys.modules.get("astrbot.api.event")
    if event_module is None:
        event_module = types.ModuleType("astrbot.api.event")
        sys.modules["astrbot.api.event"] = event_module

        class AstrMessageEvent:
            pass

        class _GroupDecorator:
            def __init__(self, func):
                self.func = func

            def __call__(self, *args, **kwargs):
                return self.func(*args, **kwargs)

            def command(self, _name: str):
                def deco(func):
                    return func

                return deco

        class _Filter:
            class PermissionType:
                ADMIN = "ADMIN"

            @staticmethod
            def command_group(_name: str):
                def deco(func):
                    return _GroupDecorator(func)

                return deco

            @staticmethod
            def permission_type(_perm):
                def deco(func):
                    return func

                return deco

        event_module.AstrMessageEvent = AstrMessageEvent
        event_module.filter = _Filter()

    # astrbot.api.star
    star_module = sys.modules.get("astrbot.api.star")
    if star_module is None:
        star_module = types.ModuleType("astrbot.api.star")
        sys.modules["astrbot.api.star"] = star_module

        class Context:
            pass

        class Star:
            def __init__(self, context):
                self.context = context

        class StarTools:
            @staticmethod
            def get_data_dir() -> str:
                return str((Path.cwd() / ".tmp_test_data").resolve())

        def register(*_args, **_kwargs):
            def deco(cls):
                return cls

            return deco

        star_module.Context = Context
        star_module.Star = Star
        star_module.StarTools = StarTools
        star_module.register = register

    # astrbot.core and message chain
    core_module = sys.modules.get("astrbot.core")
    if core_module is None:
        core_module = types.ModuleType("astrbot.core")
        core_module.astrbot_config = {}
        sys.modules["astrbot.core"] = core_module
        setattr(astrbot_module, "core", core_module)
    elif not hasattr(core_module, "astrbot_config"):
        core_module.astrbot_config = {}

    result_module = sys.modules.get("astrbot.core.message.message_event_result")
    if result_module is None:
        result_module = types.ModuleType("astrbot.core.message.message_event_result")
        sys.modules["astrbot.core.message.message_event_result"] = result_module

        class MessageChain(list):
            pass

        result_module.MessageChain = MessageChain


_install_main_import_shims()

from astrbot_plugin_media_portal.main import MediaPortalPlugin  # noqa: E402


def test_compact_record_and_webui_access_message() -> None:
    plugin = MediaPortalPlugin.__new__(MediaPortalPlugin)
    plugin.webui_server = None
    assert plugin._build_webui_access_message() == "WebUI 未启动。"

    plugin.webui_server = SimpleNamespace(
        get_access_urls=lambda: ["http://localhost:7003", "http://127.0.0.1:7003"],
        access_password="secret",
        password_generated=True,
        get_environment_notes=lambda: ["建议配置 public_base_url"],
    )
    message = plugin._build_webui_access_message()
    compact = plugin._compact_record(
        SimpleNamespace(id=7, category="cat", filename="demo.png", kind="image")
    )

    assert "可访问地址" in message
    assert "访问密码：secret" in message
    assert "建议配置 public_base_url" in message
    assert compact == "id=7 分类=cat 文件=demo.png 类型=image"


def test_resolve_record_from_input_by_id_and_query() -> None:
    class _Manager:
        async def get_by_id(self, media_id: int):
            return SimpleNamespace(id=media_id)

        async def search_media(self, query: str, limit: int = 1):
            _ = limit
            return [SimpleNamespace(id=99, query=query)] if query else []

    async def scenario() -> None:
        plugin = MediaPortalPlugin.__new__(MediaPortalPlugin)
        plugin.media_manager = _Manager()

        by_id = await plugin._resolve_record_from_input(" 12 ")
        by_query = await plugin._resolve_record_from_input("cat")
        empty = await plugin._resolve_record_from_input("   ")

        assert by_id.id == 12
        assert by_query.id == 99
        assert empty is None

    asyncio.run(scenario())


def test_send_chain_with_compatibility_paths() -> None:
    class _Context:
        def __init__(self):
            self.sent = []

        async def send_message(self, origin, chain):
            self.sent.append((origin, chain))

    class _Event:
        def __init__(self, should_fail: bool = False):
            self.unified_msg_origin = "origin"
            self.sent = []
            self.should_fail = should_fail

        async def send(self, chain):
            if self.should_fail:
                raise RuntimeError("fail")
            self.sent.append(chain)

    async def scenario() -> None:
        plugin = MediaPortalPlugin.__new__(MediaPortalPlugin)
        plugin.context = _Context()

        webchat_event = _Event()
        await plugin._send_chain_with_compatibility(
            webchat_event,
            chain=["x"],
            platform_name="webchat",
        )
        assert plugin.context.sent == [("origin", ["x"])]

        normal_event = _Event()
        await plugin._send_chain_with_compatibility(
            normal_event,
            chain=["y"],
            platform_name="qq",
        )
        assert normal_event.sent == [["y"]]

        fail_event = _Event(should_fail=True)
        await plugin._send_chain_with_compatibility(
            fail_event,
            chain=["z"],
            platform_name="qq",
        )
        assert plugin.context.sent[-1] == ("origin", ["z"])

    asyncio.run(scenario())


def test_build_media_component_fallbacks(tmp_path: Path) -> None:
    async def scenario() -> None:
        plugin = MediaPortalPlugin.__new__(MediaPortalPlugin)
        plugin.plugin_data_dir = tmp_path

        image_file = tmp_path / "a.png"
        image_file.write_bytes(b"img")
        video_file = tmp_path / "v.mp4"
        video_file.write_bytes(b"vid")
        unknown_file = tmp_path / "u.bin"
        unknown_file.write_bytes(b"bin")

        image_record = SimpleNamespace(abs_path=str(image_file), kind="image")
        video_record = SimpleNamespace(abs_path=str(video_file), kind="video")
        unknown_record = SimpleNamespace(abs_path=str(unknown_file), kind="other")

        image_component, image_temp = await plugin._build_media_component(
            image_record, platform_name="qq"
        )
        video_component, video_temp = await plugin._build_media_component(
            video_record, platform_name="webchat"
        )
        unknown_component, unknown_temp = await plugin._build_media_component(
            unknown_record, platform_name="qq"
        )

        assert image_component["kind"] == "image"
        assert image_temp is None
        assert hasattr(video_component, "file")
        assert video_temp is None
        assert hasattr(unknown_component, "file")
        assert unknown_temp is None

    asyncio.run(scenario())


def test_tool_get_media_url_branches() -> None:
    class _Manager:
        async def get_by_id(self, media_id: int):
            if media_id == 1:
                return SimpleNamespace(id=1, rel_path="cat/a.png", category="cat", filename="a.png")
            return None

    async def _ready():
        return True, ""

    async def scenario() -> None:
        plugin = MediaPortalPlugin.__new__(MediaPortalPlugin)
        plugin._ensure_ready = _ready
        plugin.media_manager = _Manager()
        plugin.webui_server = None

        invalid = await plugin.tool_get_media_url(None, "abc")
        missing = await plugin.tool_get_media_url(None, "2")
        no_webui = await plugin.tool_get_media_url(None, "1")

        plugin.webui_server = SimpleNamespace(build_media_url=lambda _r: "http://x/files/cat/a.png")
        ok = await plugin.tool_get_media_url(None, "1")

        assert "media_id 无效" in invalid
        assert missing == "媒体不存在。"
        assert no_webui == "WebUI 未启用，无法生成 URL。"
        assert ok == "http://x/files/cat/a.png"

    asyncio.run(scenario())


def test_tool_move_media_and_update_media_text_paths() -> None:
    class _Manager:
        async def move_media(self, media_id: int, target: str):
            if media_id == 1:
                return SimpleNamespace(id=1, category=target, filename="a.png", kind="image")
            raise RuntimeError("boom")

        async def update_media(self, media_id: int, **kwargs):
            _ = kwargs
            if media_id == 9:
                raise RuntimeError("fail")
            return SimpleNamespace(id=media_id, category="c", filename="f.png", kind="image")

    async def _ready():
        return True, ""

    async def scenario() -> None:
        plugin = MediaPortalPlugin.__new__(MediaPortalPlugin)
        plugin._ensure_ready = _ready
        plugin.media_manager = _Manager()

        moved = await plugin.tool_move_media(None, "1,abc,2", "dest")
        invalid_id = await plugin.tool_update_media(None, "x")
        no_fields = await plugin.tool_update_media(None, "1", category="", description="", tags="")
        failed = await plugin.tool_update_media(None, "9", description="x")
        updated = await plugin.tool_update_media(None, "8", category="n", tags="-")

        assert "已移动 1 个媒体到分类 dest" in moved
        assert "abc: 非法 ID" in moved
        assert "2: boom" in moved
        assert "media_id 无效" in invalid_id
        assert "未指定任何可更新字段" in no_fields
        assert "更新失败" in failed
        assert "已更新: id=8" in updated

    asyncio.run(scenario())


def test_tool_send_media_branches(tmp_path: Path) -> None:
    async def _ready():
        return True, ""

    class _Event:
        unified_msg_origin = "origin"

        @staticmethod
        def get_platform_name():
            return "qq"

    async def scenario() -> None:
        plugin = MediaPortalPlugin.__new__(MediaPortalPlugin)
        plugin._ensure_ready = _ready
        event = _Event()

        async def _resolve_none(_value: str):
            return None

        plugin._resolve_record_from_input = _resolve_none
        not_found = await plugin.tool_send_media(event, "x")
        assert not_found == "未找到可发送的媒体。"

        missing_record = SimpleNamespace(
            id=1, category="cat", filename="a.png", kind="image", abs_path=str(tmp_path / "missing.png")
        )

        async def _resolve_missing(_value: str):
            return missing_record

        plugin._resolve_record_from_input = _resolve_missing
        plugin.webui_server = SimpleNamespace(build_media_url=lambda _r: "http://x/missing")
        missing = await plugin.tool_send_media(event, "1")
        assert "媒体文件已丢失" in missing and "http://x/missing" in missing

        sent_file = tmp_path / "ok.png"
        sent_file.write_bytes(b"ok")
        ok_record = SimpleNamespace(
            id=2, category="cat", filename="ok.png", kind="image", abs_path=str(sent_file)
        )

        async def _resolve_ok(_value: str):
            return ok_record

        async def _build_component(_record, platform_name: str = ""):
            _ = platform_name
            return {"kind": "image"}, None

        async def _send_chain(_event, _chain, platform_name: str):
            _ = platform_name
            return None

        plugin._resolve_record_from_input = _resolve_ok
        plugin._build_media_component = _build_component
        plugin._send_chain_with_compatibility = _send_chain
        plugin.webui_server = SimpleNamespace(build_media_url=lambda _r: "http://x/ok")
        ok = await plugin.tool_send_media(event, "2")
        assert "已发送媒体: id=2" in ok and "备用直链: http://x/ok" in ok

        async def _build_fail(_record, platform_name: str = ""):
            _ = platform_name
            raise RuntimeError("send-error")

        plugin._build_media_component = _build_fail
        failed = await plugin.tool_send_media(event, "2")
        assert failed == "发送失败，改用 URL: http://x/ok"

    asyncio.run(scenario())


def test_tool_save_media_branches() -> None:
    class _Event:
        @staticmethod
        def get_sender_id():
            return "u1"

    async def _ready():
        return True, ""

    class _Manager:
        async def save_from_event(self, *args, **kwargs):
            _ = (args, kwargs)
            return {
                "saved": [SimpleNamespace(id=1, category="c", filename="a.png", kind="image")],
                "errors": [],
            }

        async def save_from_url(self, *args, **kwargs):
            _ = (args, kwargs)
            return SimpleNamespace(id=2, category="c", filename="u.png", kind="image")

        async def save_from_local_path(self, *args, **kwargs):
            _ = (args, kwargs)
            return SimpleNamespace(id=3, category="c", filename="l.png", kind="image")

    class _Downloader:
        @staticmethod
        def parse_source(text: str):
            if text.startswith("http"):
                return SimpleNamespace(source_type="url", value=text, filename_hint="")
            return SimpleNamespace(source_type="local", value=text, filename_hint="local.png")

    async def scenario() -> None:
        plugin = MediaPortalPlugin.__new__(MediaPortalPlugin)
        plugin._ensure_ready = _ready
        plugin.media_manager = _Manager()
        plugin.downloader = _Downloader()
        plugin.settings = SimpleNamespace(
            downloader=SimpleNamespace(default_move_local=True),
        )

        by_event = await plugin.tool_save_media(_Event(), source="")
        by_url = await plugin.tool_save_media(_Event(), source="https://example.com/a.png")
        by_local = await plugin.tool_save_media(_Event(), source="/tmp/a.png")

        assert "已保存 1 个媒体" in by_event
        assert "已保存: id=2" in by_url
        assert "已保存: id=3" in by_local

    asyncio.run(scenario())


def test_plugin_init_defers_bootstrap_until_async_context(
    tmp_path: Path, monkeypatch
) -> None:
    from astrbot.api.star import Context, StarTools

    monkeypatch.setattr(
        StarTools,
        "get_data_dir",
        staticmethod(lambda: str((tmp_path / "plugin_data").resolve())),
    )
    plugin = MediaPortalPlugin(Context(), config={})
    assert plugin._bootstrap_task is None

    async def fake_bootstrap():
        plugin._initialized = True

    plugin._bootstrap = fake_bootstrap  # type: ignore[assignment]

    async def scenario() -> None:
        await plugin.on_astrbot_loaded()
        await asyncio.sleep(0)
        assert plugin._initialized is True
        assert plugin._bootstrap_task is None or plugin._bootstrap_task.done()

    asyncio.run(scenario())
