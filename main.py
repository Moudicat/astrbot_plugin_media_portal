"""astrbot_plugin_media_portal 主插件入口。"""

from __future__ import annotations

import asyncio
import secrets
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
    astrbot_config = None

from .core import CategoryManager, MediaDownloader, MediaManager, load_plugin_settings
from .core.utils import (
    format_duration,
    format_size,
    format_timestamp,
    parse_bool,
)
from .webui import WebUIServer


@register(
    "media_portal",
    "moudicat",
    "多媒体存储/检索/WebUI 管理插件，支持 AI 工具调用。",
    "0.3.1",
)
class MediaPortalPlugin(Star):
    def __init__(self, context: Context, config: dict[str, Any] | None = None):
        super().__init__(context)
        self.context = context
        self.plugin_data_dir = Path(StarTools.get_data_dir()).resolve()
        self.plugin_data_dir.mkdir(parents=True, exist_ok=True)
        self.settings = load_plugin_settings(config or {}, plugin_data_dir=self.plugin_data_dir)

        self.category_manager = CategoryManager(
            categories_file=self.plugin_data_dir / "categories.json",
            media_root=self.settings.media_root,
        )
        self.downloader = MediaDownloader(
            temp_dir=self.plugin_data_dir / "temp",
            max_file_size_mb=self.settings.downloader.max_file_size_mb,
            allow_local_path_source=self.settings.downloader.allow_local_path_source,
            local_path_whitelist=self.settings.downloader.local_path_whitelist,
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
        self._bootstrap_task: asyncio.Task | None = None
        self._init_lock = asyncio.Lock()
        self._initialized = False
        self._schedule_bootstrap()

    def _create_tracked_task(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)

        def _on_done(done_task: asyncio.Task) -> None:
            self._background_tasks.discard(done_task)
            if done_task is self._bootstrap_task:
                self._bootstrap_task = None
            try:
                done_task.result()
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.error("Media Portal 后台任务异常: %s", exc, exc_info=True)

        task.add_done_callback(_on_done)
        return task

    def _schedule_bootstrap(self) -> None:
        if self._initialized:
            return
        if self._bootstrap_task and not self._bootstrap_task.done():
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        self._bootstrap_task = self._create_tracked_task(self._bootstrap())

    async def on_astrbot_loaded(self) -> None:
        self._schedule_bootstrap()

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
        if astrbot_config is not None and hasattr(astrbot_config, "get"):
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
            "totp_enabled": self.settings.webui.totp_enabled,
            "totp_issuer": self.settings.webui.totp_issuer,
            "totp_account": self.settings.webui.totp_account,
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
            lines.append("当前密码为系统随机生成，建议在 WebUI 设置页或插件配置中固定一个强密码。")
        notes = self.webui_server.get_environment_notes()
        if notes:
            lines.append("部署提示：")
            for note in notes:
                lines.append(f"- {note}")
        return "\n".join(lines)

    @staticmethod
    def _compact_record(record: Any) -> str:
        if isinstance(record, dict):
            return (
                f"id={record.get('id')} 分类={record.get('category')} "
                f"文件={record.get('filename')} 类型={record.get('kind')}"
            )
        return (
            f"id={getattr(record, 'id', '')} 分类={getattr(record, 'category', '')} "
            f"文件={getattr(record, 'filename', '')} 类型={getattr(record, 'kind', '')}"
        )

    @staticmethod
    def _extract_record_fields(record: Any) -> dict[str, Any]:
        """把 ``MediaRecord`` / dict 统一拆成同一组字段，便于输出。"""
        if isinstance(record, dict):
            return {
                "id": record.get("id"),
                "category": record.get("category"),
                "filename": record.get("filename"),
                "kind": record.get("kind"),
                "size": int(record.get("size", 0) or 0),
                "created_at": float(record.get("created_at", 0) or 0),
                "duration": float(record.get("duration", 0) or 0),
            }
        return {
            "id": getattr(record, "id", None),
            "category": getattr(record, "category", ""),
            "filename": getattr(record, "filename", ""),
            "kind": getattr(record, "kind", ""),
            "size": int(getattr(record, "size", 0) or 0),
            "created_at": float(getattr(record, "created_at", 0) or 0),
            "duration": float(getattr(record, "duration", 0) or 0),
        }

    def _detailed_record(self, record: Any) -> str:
        """展示单条媒体的详细摘要：id / 分类 / 类型 / 文件 / 大小 / 时长 / 上传时间。

        时长来源于 DB 中 ``duration`` 列（保存 / 扫描时一次性探测），
        不再运行时临时读取文件，避免列表类 API 的性能抖动。
        """
        f = self._extract_record_fields(record)
        head = (
            f"id={f['id']} 分类={f['category']} 类型={f['kind']} 文件={f['filename']}"
        )
        extras: list[str] = [f"大小={format_size(int(f['size']))}"]
        duration_text = format_duration(f["duration"])
        if duration_text and f["kind"] in {"audio", "video"}:
            extras.append(f"时长={duration_text}")
        uploaded = format_timestamp(f["created_at"])
        if uploaded:
            extras.append(f"上传={uploaded}")
        return head + "\n  " + " ".join(extras)

    def _detailed_records(self, records: list[Any]) -> list[str]:
        """批量生成详细摘要。"""
        return [self._detailed_record(r) for r in records]

    @staticmethod
    def _parse_limit(value: Any, default: int) -> int:
        """将 LLM / 用户传入的 ``value`` 安全地归一为整数。

        兼容 ``int``、``float``、以及 ``"12"`` / ``"12.5"`` / ``"  "`` 等字符串形态；
        解析失败或为空时返回 ``default``。
        """
        if value is None:
            return default
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        text = str(value).strip()
        if not text:
            return default
        try:
            return int(text)
        except ValueError:
            pass
        try:
            return int(float(text))
        except (TypeError, ValueError):
            return default

    # WebChat 前端目前只渲染 Plain/Image/Record/File 组件，Video 会被其 _send
    # 静默丢弃，从而表现为工具“已调用但什么都没发”。
    _WEBCHAT_UNSUPPORTED_KINDS: frozenset[str] = frozenset({"video"})
    _WEBCHAT_IMAGE_SAFE_SUFFIXES: frozenset[str] = frozenset(
        {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".avif"}
    )

    def _convert_image_for_webchat_sync(self, source: Path) -> Path:
        temp_dir = self.plugin_data_dir / "temp" / "webchat_compat"
        temp_dir.mkdir(parents=True, exist_ok=True)
        target = temp_dir / f"webchat_{secrets.token_hex(8)}.png"
        from PIL import Image, ImageOps

        with Image.open(source) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode not in {"RGB", "RGBA"}:
                if img.mode in {"P", "LA"} or "A" in img.mode:
                    img = img.convert("RGBA")
                else:
                    img = img.convert("RGB")
            img.save(target, "PNG")
        return target

    async def _build_media_component(
        self, record, platform_name: str = ""
    ) -> tuple[Any, Path | None]:
        file_path = Path(record.abs_path)
        kind = record.kind
        platform = str(platform_name or "").strip().lower()
        if (
            platform == "webchat"
            and kind in self._WEBCHAT_UNSUPPORTED_KINDS
            and hasattr(Comp, "File")
        ):
            return Comp.File(file=str(file_path), name=file_path.name), None
        if kind == "image" and hasattr(Comp, "Image"):
            if platform != "webchat":
                return Comp.Image.fromFileSystem(str(file_path)), None
            suffix = file_path.suffix.lower()
            if suffix in self._WEBCHAT_IMAGE_SAFE_SUFFIXES:
                return Comp.Image.fromFileSystem(str(file_path)), None
            try:
                compat_path = await asyncio.to_thread(
                    self._convert_image_for_webchat_sync, file_path
                )
                logger.debug(
                    "webchat 图片兼容转换: %s -> %s", file_path.name, compat_path.name
                )
                return Comp.Image.fromFileSystem(str(compat_path)), compat_path
            except Exception as exc:
                logger.warning("webchat 图片兼容转换失败，降级文件发送: %s", exc)
                if hasattr(Comp, "File"):
                    return Comp.File(file=str(file_path), name=file_path.name), None
                return Comp.Plain(f"[图片文件] {file_path.name}"), None
        if kind == "video" and hasattr(Comp, "Video"):
            return Comp.Video.fromFileSystem(str(file_path)), None
        if kind == "audio" and hasattr(Comp, "Record"):
            return Comp.Record.fromFileSystem(str(file_path)), None
        if hasattr(Comp, "File"):
            return Comp.File(file=str(file_path), name=file_path.name), None
        return Comp.Plain(f"[文件] {file_path.name}"), None

    async def _send_chain_with_compatibility(
        self,
        event: AstrMessageEvent,
        chain: MessageChain,
        *,
        platform_name: str,
    ) -> None:
        platform = str(platform_name or "").strip().lower()
        if platform == "webchat":
            await self.context.send_message(event.unified_msg_origin, chain)
            return
        try:
            await event.send(chain)
        except Exception as inner_exc:
            logger.debug("event.send 不可用，回退 context.send_message: %s", inner_exc)
            await self.context.send_message(event.unified_msg_origin, chain)

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
        ...

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
            size_human = item.get("size_human") or format_size(int(item.get("size", 0) or 0))
            lines.append(
                f"- {item.get('category')}: {item.get('count', 0)} 个, {size_human}{suffix}"
            )
        yield event.plain_result("\n".join(lines))

    DEFAULT_LIST_LIMIT = 10
    MAX_LIST_LIMIT = 50

    @media.command("list")
    async def media_list(
        self,
        event: AstrMessageEvent,
        category: str = "",
        limit: int = 0,
        kind: str = "",
    ):
        """按分类列出媒体（默认仅展示前 10 条，可传 limit 参数扩大至 50）。"""
        ok, message = await self._ensure_ready()
        if not ok:
            yield event.plain_result(message)
            return
        requested_limit = self._parse_limit(limit, self.DEFAULT_LIST_LIMIT)
        effective_limit = max(1, min(self.MAX_LIST_LIMIT, requested_limit))

        payload = await self.media_manager.list_media(
            category=category,
            kind=kind,
            page=1,
            page_size=effective_limit,
        )
        items = payload.get("items", [])
        total = int(payload.get("total", 0) or 0)

        if not items:
            yield event.plain_result("未找到媒体。")
            return

        header_scope = f"分类 {category}" if category else "全部分类"
        header = f"媒体列表（{header_scope}，显示 {len(items)}/{total}）："
        lines = [header]
        detailed = self._detailed_records(items)
        for text in detailed:
            lines.append(f"- {text}")
        if total > len(items):
            lines.append(
                f"仅显示前 {len(items)} 条，共 {total} 条；"
                f"如需更多请加参数，例如：/media list {category or '<分类>'} 50"
            )
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
        requested_limit = self._parse_limit(limit, 5)
        records = await self.media_manager.search_media(
            query,
            limit=max(1, min(20, requested_limit)),
            category=category,
        )
        if not records:
            yield event.plain_result("没有找到匹配媒体。")
            return
        lines = [f"搜索结果（{len(records)}）："]
        for text in self._detailed_records(records):
            lines.append(f"- {text}")
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
            move(bool): 从本地路径或消息附件保存时是否移动源文件（true=mv，false=copy）；
                URL 来源不受此参数影响。
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
            size_human = item.get("size_human") or format_size(int(item.get("size", 0) or 0))
            lines.append(
                f"- {item['category']}: {item['count']} 个, {size_human}, 描述={item.get('description', '')}"
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
        """按分类列出媒体。返回字段：id/分类/类型/文件名，以及大小、上传时间；图片附分辨率、音频附时长。

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
            limit=max(1, min(50, self._parse_limit(limit, 20))),
            kind=kind,
        )
        if not records:
            return "该分类暂无媒体。"
        lines = [f"分类 {category} 的媒体："]
        for text in self._detailed_records(records):
            lines.append(f"- {text}")
        return "\n".join(lines)

    @llm_tool(name="search_media")
    async def tool_search_media(
        self,
        event: AstrMessageEvent,
        query: str,
        limit: int = 5,
        category: str = "",
    ) -> str:
        """在媒体库中搜索媒体文件。返回字段：id/分类/类型/文件名，以及大小、上传时间；图片附分辨率、音频附时长。

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
            limit=max(1, min(30, self._parse_limit(limit, 5))),
            category=category,
        )
        if not records:
            return "未找到匹配媒体。"
        lines = ["搜索结果："]
        for text in self._detailed_records(records):
            lines.append(f"- {text}")
        return "\n".join(lines)

    @llm_tool(name="get_media_url")
    async def tool_get_media_url(
        self,
        event: AstrMessageEvent,
        media_id: str,
    ) -> str:
        """从媒体库获取媒体公开访问 URL。

        Args:
            media_id(string): 媒体 ID（数字字符串，例如 "12"）。
        """
        _ = event
        ok, message = await self._ensure_ready()
        if not ok:
            return message
        try:
            resolved_id = int(str(media_id).strip())
        except (TypeError, ValueError):
            return "media_id 无效，请传入数字。"
        record = await self.media_manager.get_by_id(resolved_id)
        if not record:
            return "媒体不存在。"
        if not self.webui_server:
            return "WebUI 未启用，无法生成 URL。"
        return self.webui_server.build_media_url(record)

    @llm_tool(name="send_media")
    async def tool_send_media(
        self, event: AstrMessageEvent, media_id_or_query: str
    ) -> str:
        """向当前会话发送媒体库中的媒体 （不是通用文件发送）

        Args:
            media_id_or_query(string): 可传媒体 ID 或搜索关键词，不允许本地路径/URL。
        """
        ok, message = await self._ensure_ready()
        if not ok:
            return message
        record = await self._resolve_record_from_input(media_id_or_query)
        if not record:
            return "未找到可发送的媒体。"
        file_path = Path(record.abs_path)
        if not file_path.exists():
            logger.warning("媒体文件缺失: %s", file_path)
            if self.webui_server:
                return (
                    "媒体文件已丢失，建议 /media scan。"
                    f" 可尝试 URL: {self.webui_server.build_media_url(record)}"
                )
            return "媒体文件已丢失，建议执行 /media scan 修复索引。"

        share_url = self.webui_server.build_media_url(record) if self.webui_server else ""
        platform_name = ""
        try:
            platform_name = str(event.get_platform_name() or "")
        except Exception:
            platform_name = ""
        try:
            component, temp_cleanup_path = await self._build_media_component(
                record, platform_name=platform_name
            )
            chain = MessageChain([component])
            try:
                await self._send_chain_with_compatibility(
                    event, chain, platform_name=platform_name
                )
            finally:
                if temp_cleanup_path and temp_cleanup_path.exists():
                    temp_cleanup_path.unlink(missing_ok=True)

            summary = f"已发送媒体: {self._compact_record(record)}"
            if share_url:
                summary += f"\n备用直链: {share_url}"
            return summary
        except Exception as exc:
            logger.warning("发送媒体失败，降级返回 URL: %s", exc)
            if share_url:
                return f"发送失败，改用 URL: {share_url}"
            return f"发送失败: {exc}"

    @llm_tool(name="move_media")
    async def tool_move_media(
        self,
        event: AstrMessageEvent,
        media_ids: str,
        category: str,
    ) -> str:
        """将一个或多个媒体重分类到目标分类。

        Args:
            media_ids(string): 媒体 ID，多个使用英文逗号分隔，例如 "12" 或 "12,15,20"。
            category(string): 目标分类名，不存在时会自动创建。
        """
        _ = event
        ok, message = await self._ensure_ready()
        if not ok:
            return message
        target = str(category or "").strip()
        if not target:
            return "请提供目标分类。"
        raw_ids = str(media_ids or "").strip()
        if not raw_ids:
            return "请提供至少一个 media_id。"
        tokens = [tok for tok in raw_ids.replace("，", ",").split(",") if tok.strip()]
        moved: list[str] = []
        errors: list[str] = []
        for token in tokens:
            try:
                mid = int(token.strip())
            except ValueError:
                errors.append(f"{token}: 非法 ID")
                continue
            try:
                record = await self.media_manager.move_media(mid, target)
                moved.append(self._compact_record(record))
            except Exception as exc:
                errors.append(f"{token}: {exc}")
        lines: list[str] = []
        if moved:
            lines.append(f"已移动 {len(moved)} 个媒体到分类 {target}：")
            lines.extend(moved)
        if errors:
            lines.append("失败：")
            lines.extend(errors[:10])
            if len(errors) > 10:
                lines.append(f"... 还有 {len(errors) - 10} 条错误未展示")
        return "\n".join(lines) if lines else "未处理任何媒体。"

    @llm_tool(name="update_media")
    async def tool_update_media(
        self,
        event: AstrMessageEvent,
        media_id: str,
        category: str = "",
        description: str = "",
        tags: str = "",
        filename: str = "",
    ) -> str:
        """更新媒体的分类 / 描述 / 标签 / 文件名。任一留空即表示不修改该字段。

        Args:
            media_id(string): 媒体 ID。
            category(string): 新分类名（留空则不变；指定不存在的分类会自动创建并搬移文件）。
            description(string): 新描述（留空不变）。
            tags(string): 新标签，英文逗号分隔；传入 "-" 表示清空。
            filename(string): 新文件名（留空不变）；未带扩展名时自动沿用旧后缀，改名会让旧直链失效。
        """
        _ = event
        ok, message = await self._ensure_ready()
        if not ok:
            return message
        try:
            mid = int(str(media_id).strip())
        except (TypeError, ValueError):
            return "media_id 无效。"

        new_category: str | None = category.strip() or None
        new_description: str | None = None
        if description:
            new_description = description.strip()
        new_tags: list[str] | None = None
        tags_raw = (tags or "").strip()
        if tags_raw:
            if tags_raw == "-":
                new_tags = []
            else:
                new_tags = [
                    item.strip()
                    for item in tags_raw.replace("，", ",").split(",")
                    if item.strip()
                ]
        new_filename: str | None = None
        filename_raw = (filename or "").strip()
        if filename_raw:
            new_filename = filename_raw

        if (
            new_category is None
            and new_description is None
            and new_tags is None
            and new_filename is None
        ):
            return "未指定任何可更新字段。"

        try:
            record = await self.media_manager.update_media(
                mid,
                description=new_description,
                tags=new_tags,
                category=new_category,
                filename=new_filename,
            )
        except Exception as exc:
            return f"更新失败: {exc}"
        return f"已更新: {self._compact_record(record)}"

    async def terminate(self):
        pending = [task for task in self._background_tasks if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self._background_tasks.clear()
        await self._stop_webui()
        try:
            await self.media_manager.close()
        except Exception as exc:
            logger.warning("关闭 MediaManager 失败: %s", exc)
