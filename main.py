"""astrbot_plugin_media_portal 主插件入口。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import astrbot.api.message_components as Comp
from astrbot.api import llm_tool, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core.message.message_event_result import MessageChain

try:
    from astrbot.core import astrbot_config
except Exception:  # pragma: no cover
    astrbot_config = {}

from .core import CategoryManager, MediaDownloader, MediaManager, load_plugin_settings
from .core.utils import parse_bool
from .webui import WebUIServer


@register(
    "media_portal",
    "moudicat",
    "多媒体存储/检索/WebUI 管理插件，支持 AI 工具调用。",
    "0.1.1",
)
class MediaPortalPlugin(Star):
    def __init__(self, context: Context, config: dict[str, Any] | None = None):
        super().__init__(context)
        self.context = context
        self.plugin_data_dir = Path(str(StarTools.get_data_dir())).resolve()
        self.plugin_data_dir.mkdir(parents=True, exist_ok=True)
        self.settings = load_plugin_settings(config or {}, plugin_data_dir=self.plugin_data_dir)

        self.category_manager = CategoryManager(
            categories_file=self.plugin_data_dir / "categories.json",
            media_root=self.settings.media_root,
        )
        self.downloader = MediaDownloader(
            temp_dir=self.plugin_data_dir / "temp",
            max_file_size_mb=self.settings.downloader.max_file_size_mb,
        )
        self.media_manager = MediaManager(
            media_root=self.settings.media_root,
            plugin_data_dir=self.plugin_data_dir,
            category_manager=self.category_manager,
            downloader=self.downloader,
            allowed_kinds=self.settings.downloader.allowed_kinds,
            max_file_size_mb=self.settings.downloader.max_file_size_mb,
            default_move_local=self.settings.downloader.default_move_local,
        )
        self.webui_server: WebUIServer | None = None

        self._background_tasks: set[asyncio.Task] = set()
        self._init_lock = asyncio.Lock()
        self._initialized = False
        self._create_tracked_task(self._bootstrap())

    def _create_tracked_task(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def _bootstrap(self) -> None:
        async with self._init_lock:
            if self._initialized:
                return
            await self.media_manager.initialize()
            await self.media_manager.ensure_scanned()
            if self.settings.webui.enabled:
                await self._start_webui()
            self._initialized = True

    async def _ensure_ready(self) -> tuple[bool, str]:
        if self._initialized:
            return True, ""
        try:
            await self._bootstrap()
            return True, ""
        except Exception as exc:
            logger.error("Media Portal 初始化失败: %s", exc, exc_info=True)
            return False, f"插件初始化失败: {exc}"

    async def _start_webui(self) -> None:
        if self.webui_server:
            return
        callback_api_base = ""
        if hasattr(astrbot_config, "get"):
            callback_api_base = str(astrbot_config.get("callback_api_base", "") or "").strip()
        config = {
            "enabled": self.settings.webui.enabled,
            "host": self.settings.webui.host,
            "port": self.settings.webui.port,
            "access_password": self.settings.webui.access_password,
            "session_timeout": self.settings.webui.session_timeout,
            "public_base_url": self.settings.webui.public_base_url,
            "expose_astrbot_data": self.settings.webui.expose_astrbot_data,
            "allowed_origins": self.settings.webui.allowed_origins,
            "readonly_token_ttl": self.settings.webui.readonly_token_ttl,
            "share_url_ttl": self.settings.webui.share_url_ttl,
            "data_token_ttl": self.settings.webui.data_token_ttl,
        }
        self.webui_server = WebUIServer(
            media_manager=self.media_manager,
            category_manager=self.category_manager,
            config=config,
            data_root=self.settings.astrbot_data_dir,
            callback_api_base=callback_api_base,
        )
        await self.webui_server.start()

    async def _stop_webui(self) -> None:
        if not self.webui_server:
            return
        await self.webui_server.stop()
        self.webui_server = None

    def _build_webui_access_message(self) -> str:
        if not self.webui_server:
            return "WebUI 未启动。"
        urls = self.webui_server.get_access_urls()
        lines = ["Media Portal WebUI 已启动。", "可访问地址："]
        for url in urls:
            lines.append(f"- {url}")
        lines.append(f"访问密码：{self.webui_server.access_password}")
        if self.webui_server.password_generated:
            lines.append("当前密码为系统随机生成，建议通过 /media password set <密码> 进行固定。")
        return "\n".join(lines)

    @staticmethod
    def _compact_record(record) -> str:
        return f"id={record.id} 分类={record.category} 文件={record.filename} 类型={record.kind}"

    def _build_media_component(self, record) -> Any:
        file_path = Path(record.abs_path)
        if record.kind == "image" and hasattr(Comp, "Image"):
            return Comp.Image.fromFileSystem(str(file_path))
        if record.kind == "video" and hasattr(Comp, "Video"):
            return Comp.Video.fromFileSystem(str(file_path))
        if record.kind == "audio" and hasattr(Comp, "Record"):
            return Comp.Record.fromFileSystem(str(file_path))
        if hasattr(Comp, "File"):
            return Comp.File(file=str(file_path), name=file_path.name)
        return Comp.Plain(f"[文件] {file_path.name}")

    async def _resolve_record_from_input(self, media_id_or_query: str):
        value = str(media_id_or_query or "").strip()
        if not value:
            return None
        if value.isdigit():
            return await self.media_manager.get_by_id(int(value))
        results = await self.media_manager.search_media(value, limit=1)
        return results[0] if results else None

    # ------------------ 命令组 ------------------

    @filter.command_group("media")
    def media(self):
        """多媒体管理命令组。"""
        pass

    @filter.permission_type(filter.PermissionType.ADMIN)
    @media.command("webui")
    async def media_webui(self, event: AstrMessageEvent):
        """查看 WebUI 访问信息。"""
        ok, message = await self._ensure_ready()
        if not ok:
            yield event.plain_result(message)
            return
        if not self.webui_server:
            yield event.plain_result("WebUI 未启用。请在配置中开启 webui.enabled。")
            return
        yield event.plain_result(self._build_webui_access_message())

    @filter.permission_type(filter.PermissionType.ADMIN)
    @media.command("password")
    async def media_password(
        self,
        event: AstrMessageEvent,
        action: str = "show",
        value: str = "",
    ):
        """管理 WebUI 密码。"""
        ok, message = await self._ensure_ready()
        if not ok:
            yield event.plain_result(message)
            return
        if not self.webui_server:
            yield event.plain_result("WebUI 未启用。")
            return
        normalized_action = (action or "show").strip().lower()
        if normalized_action in {"show", "查看"}:
            yield event.plain_result(self._build_webui_access_message())
            return
        if normalized_action in {"regen", "reset", "随机"}:
            password = await self.webui_server.rotate_password("")
            yield event.plain_result(f"密码已重置（随机）：{password}")
            return
        if normalized_action in {"set", "指定"}:
            if not value.strip():
                yield event.plain_result("请提供新密码，例如：/media password set mypass123")
                return
            password = await self.webui_server.rotate_password(value.strip())
            yield event.plain_result(f"密码已更新：{password}")
            return
        yield event.plain_result("用法：/media password show|regen|set <密码>")

    @media.command("categories")
    async def media_categories(self, event: AstrMessageEvent):
        """查看分类列表。"""
        ok, message = await self._ensure_ready()
        if not ok:
            yield event.plain_result(message)
            return
        stats = await self.media_manager.get_stats()
        items = stats.get("categories", [])
        if not items:
            yield event.plain_result("当前没有分类。")
            return
        lines = ["分类列表："]
        for item in items:
            desc = str(item.get("description", "") or "")
            suffix = f" - {desc}" if desc else ""
            lines.append(
                f"- {item.get('category')}: {item.get('count', 0)} 个, {item.get('size', 0)} B{suffix}"
            )
        yield event.plain_result("\n".join(lines))

    @media.command("list")
    async def media_list(
        self,
        event: AstrMessageEvent,
        category: str = "",
        limit: int = 20,
        kind: str = "",
    ):
        """按分类列出媒体。"""
        ok, message = await self._ensure_ready()
        if not ok:
            yield event.plain_result(message)
            return
        limit = max(1, min(50, int(limit)))
        if category:
            records = await self.media_manager.list_recent_in_category(
                category,
                limit=limit,
                kind=kind,
            )
        else:
            payload = await self.media_manager.list_media(
                kind=kind,
                page=1,
                page_size=limit,
            )
            records = payload.get("items", [])
            if records and isinstance(records[0], dict):
                lines = ["媒体列表："]
                for row in records:
                    lines.append(
                        f"- id={row['id']} 分类={row['category']} 文件={row['filename']} 类型={row['kind']}"
                    )
                yield event.plain_result("\n".join(lines))
                return
        if not records:
            yield event.plain_result("未找到媒体。")
            return
        lines = ["媒体列表："]
        for record in records:
            lines.append(f"- {self._compact_record(record)}")
        yield event.plain_result("\n".join(lines))

    @media.command("search")
    async def media_search(
        self,
        event: AstrMessageEvent,
        query: str = "",
        limit: int = 5,
        category: str = "",
    ):
        """搜索媒体。"""
        ok, message = await self._ensure_ready()
        if not ok:
            yield event.plain_result(message)
            return
        if not query.strip():
            yield event.plain_result("请输入关键词，例如：/media search 猫咪")
            return
        records = await self.media_manager.search_media(
            query,
            limit=max(1, min(20, int(limit))),
            category=category,
        )
        if not records:
            yield event.plain_result("没有找到匹配媒体。")
            return
        lines = [f"搜索结果（{len(records)}）："]
        for record in records:
            lines.append(f"- {self._compact_record(record)}")
        yield event.plain_result("\n".join(lines))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @media.command("scan")
    async def media_scan(self, event: AstrMessageEvent):
        """扫描目录并修复索引。"""
        ok, message = await self._ensure_ready()
        if not ok:
            yield event.plain_result(message)
            return
        result = await self.media_manager.ensure_scanned()
        yield event.plain_result(
            f"扫描完成：新增 {result['indexed']}，清理失效记录 {result['removed']}，跳过 {result['skipped']}。"
        )

    # ------------------ LLM 工具 ------------------

    @llm_tool(name="save_media")
    async def tool_save_media(
        self,
        event: AstrMessageEvent,
        source: str = "",
        category: str = "default",
        description: str = "",
        filename: str = "",
        move: bool = True,
    ) -> str:
        """保存媒体到媒体库。

        Args:
            source(str): 媒体来源；支持 URL、本地文件路径。留空时从当前消息附件提取。
            category(str): 分类名。
            description(str): 描述。
            filename(str): 自定义文件名（可选）。
            move(bool): source 为本地路径时是否移动（true=mv，false=copy）。
        """

        ok, message = await self._ensure_ready()
        if not ok:
            return message
        sender_id = str(event.get_sender_id() or "")
        move_local = parse_bool(move, default=self.settings.downloader.default_move_local)

        source_text = str(source or "").strip()
        if not source_text:
            result = await self.media_manager.save_from_event(
                event,
                category=category,
                description=description,
                move=move_local,
                sender_id=sender_id,
            )
            saved = result.get("saved", [])
            errors = result.get("errors", [])
            if not saved:
                return "未保存成功。错误：" + ("; ".join(errors) if errors else "未发现可用媒体。")
            lines = [f"已保存 {len(saved)} 个媒体："]
            for record in saved:
                lines.append(self._compact_record(record))
            if errors:
                lines.append("部分失败：")
                lines.extend(errors[:5])
            return "\n".join(lines)

        parsed = self.downloader.parse_source(source_text)
        if parsed.source_type == "url":
            record = await self.media_manager.save_from_url(
                parsed.value,
                category=category,
                description=description,
                filename=filename or parsed.filename_hint,
                sender_id=sender_id,
            )
        else:
            record = await self.media_manager.save_from_local_path(
                parsed.value,
                category=category,
                description=description,
                filename=filename or parsed.filename_hint,
                move=move_local,
                sender_id=sender_id,
            )
        return f"已保存: {self._compact_record(record)}"

    @llm_tool(name="list_media_categories")
    async def tool_list_media_categories(self, event: AstrMessageEvent) -> str:
        """列出所有媒体分类及统计。"""
        _ = event
        ok, message = await self._ensure_ready()
        if not ok:
            return message
        stats = await self.media_manager.get_stats()
        categories = stats.get("categories", [])
        if not categories:
            return "暂无媒体分类。"
        lines = ["媒体分类："]
        for item in categories:
            lines.append(
                f"- {item['category']}: {item['count']} 个, {item['size']} B, 描述={item.get('description', '')}"
            )
        return "\n".join(lines)

    @llm_tool(name="list_media_in_category")
    async def tool_list_media_in_category(
        self,
        event: AstrMessageEvent,
        category: str,
        limit: int = 20,
        kind: str = "",
    ) -> str:
        """按分类列出媒体。

        Args:
            category(str): 分类名。
            limit(int): 返回数量上限。
            kind(str): 可选过滤 image/video/audio。
        """
        _ = event
        ok, message = await self._ensure_ready()
        if not ok:
            return message
        records = await self.media_manager.list_recent_in_category(
            category,
            limit=max(1, min(50, int(limit))),
            kind=kind,
        )
        if not records:
            return "该分类暂无媒体。"
        lines = [f"分类 {category} 的媒体："]
        for record in records:
            lines.append(f"- {self._compact_record(record)}")
        return "\n".join(lines)

    @llm_tool(name="search_media")
    async def tool_search_media(
        self,
        event: AstrMessageEvent,
        query: str,
        limit: int = 5,
        category: str = "",
    ) -> str:
        """搜索媒体文件。

        Args:
            query(str): 文件名/描述关键词。
            limit(int): 返回数量。
            category(str): 可选分类过滤。
        """
        _ = event
        ok, message = await self._ensure_ready()
        if not ok:
            return message
        records = await self.media_manager.search_media(
            query,
            limit=max(1, min(30, int(limit))),
            category=category,
        )
        if not records:
            return "未找到匹配媒体。"
        lines = ["搜索结果："]
        for record in records:
            lines.append(f"- {self._compact_record(record)}")
        return "\n".join(lines)

    @llm_tool(name="get_media_url")
    async def tool_get_media_url(self, event: AstrMessageEvent, media_id: int) -> str:
        """获取媒体公开访问 URL。"""
        _ = event
        ok, message = await self._ensure_ready()
        if not ok:
            return message
        record = await self.media_manager.get_by_id(int(media_id))
        if not record:
            return "媒体不存在。"
        if not self.webui_server:
            return "WebUI 未启用，无法生成 URL。"
        return self.webui_server.build_media_url(record)

    @llm_tool(name="send_media")
    async def tool_send_media(
        self, event: AstrMessageEvent, media_id_or_query: str
    ) -> str:
        """向当前会话发送媒体。

        Args:
            media_id_or_query(str): 可传媒体 ID 或搜索关键词。
        """
        ok, message = await self._ensure_ready()
        if not ok:
            return message
        record = await self._resolve_record_from_input(media_id_or_query)
        if not record:
            return "未找到可发送的媒体。"
        try:
            component = self._build_media_component(record)
            await self.context.send_message(
                event.unified_msg_origin,
                MessageChain([component]),
            )
            return f"已发送媒体: {self._compact_record(record)}"
        except Exception as exc:
            logger.warning("发送媒体失败，降级返回 URL: %s", exc)
            if self.webui_server:
                return f"发送失败，改用 URL: {self.webui_server.build_media_url(record)}"
            return f"发送失败: {exc}"

    async def terminate(self):
        for task in list(self._background_tasks):
            if task.done():
                continue
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._background_tasks.clear()
        await self._stop_webui()
        await self.media_manager.close()
