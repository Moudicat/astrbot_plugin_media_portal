"""Media Portal WebUI 服务。"""

from __future__ import annotations

import asyncio
import mimetypes
import secrets
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import aiofiles
import uvicorn
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from astrbot.api import logger

try:
    from astrbot.core.utils.io import get_local_ip_addresses
except Exception:  # pragma: no cover

    def get_local_ip_addresses() -> list[str]:
        return []

from ..core.category_manager import CategoryManager
from ..core.media_manager import MediaManager, MediaRecord
from ..core.utils import (
    detect_mime_and_kind,
    generate_password,
    safe_join,
    slugify_category,
    unique_path,
)


class WebUIServer:
    def __init__(
        self,
        media_manager: MediaManager,
        category_manager: CategoryManager,
        config: dict[str, Any],
        data_root: Path,
        callback_api_base: str = "",
    ):
        self.media_manager = media_manager
        self.category_manager = category_manager
        self.config = config
        self.data_root = data_root.resolve()
        self.media_root = self.media_manager.media_root

        self.host = str(config.get("host", "0.0.0.0") or "0.0.0.0")
        self.port = int(config.get("port", 7003) or 7003)
        self.enabled = bool(config.get("enabled", True))
        self.expose_astrbot_data = bool(config.get("expose_astrbot_data", True))
        self.session_timeout = max(60, int(config.get("session_timeout", 3600) or 3600))
        self.public_base_url = str(config.get("public_base_url", "") or "").strip().rstrip("/")
        self.callback_api_base = str(callback_api_base or "").strip().rstrip("/")

        self._access_password = str(config.get("access_password", "") or "").strip()
        self._password_generated = False
        if not self._access_password:
            self._access_password = generate_password(16)
            self._password_generated = True
            logger.info("Media Portal WebUI 未配置密码，已自动生成。")

        self._readonly_token = secrets.token_urlsafe(24)
        self._tokens: dict[str, dict[str, float]] = {}
        self._failed_attempts: dict[str, list[float]] = {}
        self._token_lock = asyncio.Lock()
        self._attempt_lock = asyncio.Lock()

        self._app = FastAPI(title="Media Portal WebUI", version="1.0.0")
        self._server: uvicorn.Server | None = None
        self._server_task: asyncio.Task | None = None
        self._cleanup_task: asyncio.Task | None = None
        self._setup_routes()

    @property
    def app(self) -> FastAPI:
        return self._app

    @property
    def access_password(self) -> str:
        return self._access_password

    @property
    def readonly_token(self) -> str:
        return self._readonly_token

    @property
    def password_generated(self) -> bool:
        return self._password_generated

    async def start(self) -> None:
        if self._server_task and not self._server_task.done():
            return
        config = uvicorn.Config(
            app=self._app,
            host=self.host,
            port=self.port,
            loop="asyncio",
            lifespan="on",
            log_level="warning",
        )
        self._server = uvicorn.Server(config)
        self._server_task = asyncio.create_task(self._server.serve())
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

        for _ in range(50):
            if getattr(self._server, "started", False):
                logger.info("Media Portal WebUI 已启动: %s", self.get_preferred_base_url())
                return
            if self._server_task.done():
                error = self._server_task.exception()
                raise RuntimeError(f"WebUI 启动失败: {error}") from error
            await asyncio.sleep(0.1)

    async def stop(self) -> None:
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        if self._server:
            self._server.should_exit = True
        if self._server_task:
            await self._server_task
        self._cleanup_task = None
        self._server_task = None
        self._server = None

    async def rotate_password(self, password: str = "") -> str:
        self._access_password = password.strip() or generate_password(16)
        self._password_generated = not bool(password.strip())
        self._readonly_token = secrets.token_urlsafe(24)
        async with self._token_lock:
            self._tokens.clear()
        return self._access_password

    def get_access_urls(self) -> list[str]:
        urls: list[str] = []
        if self.public_base_url:
            urls.append(self.public_base_url)
        urls.append(f"http://localhost:{self.port}")
        urls.append(f"http://127.0.0.1:{self.port}")

        if self.host not in {"0.0.0.0", "::"} and self.host not in {"127.0.0.1", "localhost"}:
            urls.append(f"http://{self.host}:{self.port}")
        else:
            for ip in get_local_ip_addresses():
                if not ip or ip.startswith("127."):
                    continue
                urls.append(f"http://{ip}:{self.port}")

        dedup: list[str] = []
        seen: set[str] = set()
        for url in urls:
            if url in seen:
                continue
            seen.add(url)
            dedup.append(url)
        return dedup

    def get_preferred_base_url(self) -> str:
        if self.public_base_url:
            return self.public_base_url
        if self.callback_api_base:
            return self.callback_api_base
        if self.host in {"0.0.0.0", "::"}:
            for ip in get_local_ip_addresses():
                if ip and not ip.startswith("127."):
                    return f"http://{ip}:{self.port}"
            return f"http://localhost:{self.port}"
        if self.host in {"127.0.0.1", "localhost"}:
            return f"http://localhost:{self.port}"
        return f"http://{self.host}:{self.port}"

    def build_media_url(self, record: MediaRecord) -> str:
        base_url = self.get_preferred_base_url()
        return (
            f"{base_url}/files/{quote(record.category)}/{quote(record.filename)}"
            f"?token={quote(self._readonly_token)}"
        )

    async def _periodic_cleanup(self) -> None:
        while True:
            try:
                await asyncio.sleep(300)
                async with self._token_lock:
                    self._cleanup_tokens_locked()
                async with self._attempt_lock:
                    self._cleanup_attempts_locked()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("WebUI 周期清理失败: %s", exc)

    def _cleanup_tokens_locked(self) -> None:
        now = time.time()
        expired: list[str] = []
        for token, info in self._tokens.items():
            created = info.get("created_at", 0.0)
            active = info.get("last_active", 0.0)
            if now - created > 86400:
                expired.append(token)
                continue
            if now - active > self.session_timeout:
                expired.append(token)
        for token in expired:
            self._tokens.pop(token, None)

    def _cleanup_attempts_locked(self) -> None:
        now = time.time()
        ips_to_remove: list[str] = []
        for ip, records in self._failed_attempts.items():
            fresh = [item for item in records if now - item < 300]
            if fresh:
                self._failed_attempts[ip] = fresh
            else:
                ips_to_remove.append(ip)
        for ip in ips_to_remove:
            self._failed_attempts.pop(ip, None)

    async def _check_rate_limit(self, client_ip: str) -> bool:
        async with self._attempt_lock:
            self._cleanup_attempts_locked()
            records = self._failed_attempts.get(client_ip, [])
            return len(records) < 5

    async def _record_failed_attempt(self, client_ip: str) -> None:
        async with self._attempt_lock:
            self._failed_attempts.setdefault(client_ip, []).append(time.time())

    def _extract_token(self, request: Request) -> str:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        return request.headers.get("X-Auth-Token", "")

    async def _validate_token(self, token: str) -> str:
        if not token:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="缺少认证 token")
        async with self._token_lock:
            info = self._tokens.get(token)
            if not info:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="token 无效")
            now = time.time()
            created = info.get("created_at", 0.0)
            active = info.get("last_active", 0.0)
            if now - created > 86400:
                self._tokens.pop(token, None)
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="token 已过期")
            if now - active > self.session_timeout:
                self._tokens.pop(token, None)
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="会话超时")
            info["last_active"] = now
        return token

    def _auth_dependency(self):
        async def dependency(request: Request) -> str:
            token = self._extract_token(request)
            return await self._validate_token(token)

        return dependency

    async def _can_access_file(self, request: Request) -> bool:
        token = request.query_params.get("token", "")
        if token and token == self._readonly_token:
            return True
        bearer = self._extract_token(request)
        if not bearer:
            return False
        try:
            await self._validate_token(bearer)
            return True
        except HTTPException:
            return False

    def _resolve_data_path(self, raw_path: str) -> Path:
        normalized = str(raw_path or "").strip().lstrip("/")
        return safe_join(self.data_root, normalized)

    def _build_data_item(self, path: Path) -> dict[str, Any]:
        is_dir = path.is_dir()
        rel_path = path.resolve().relative_to(self.data_root).as_posix()
        if rel_path == ".":
            rel_path = ""
        size = 0 if is_dir else path.stat().st_size
        mime, kind = detect_mime_and_kind(path) if not is_dir else ("", "folder")
        return {
            "name": path.name,
            "path": rel_path,
            "is_dir": is_dir,
            "size": size,
            "mime": mime,
            "kind": kind,
        }

    def _setup_routes(self) -> None:
        static_root = Path(__file__).resolve().parent / "static"
        index_file = static_root / "index.html"

        self._app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        if static_root.exists():
            self._app.mount("/static", StaticFiles(directory=static_root), name="static")

        @self._app.get("/", response_class=HTMLResponse)
        async def index_page() -> HTMLResponse:
            if not index_file.exists():
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="前端文件不存在")
            return HTMLResponse(index_file.read_text(encoding="utf-8"))

        @self._app.get("/api/health")
        async def health() -> dict[str, Any]:
            return {"status": "ok", "service": "media_portal_webui", "version": "1.0.0"}

        @self._app.post("/api/login")
        async def login(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
            password = str(payload.get("password", "") or "").strip()
            if not password:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="密码不能为空")
            client_ip = request.client.host if request.client else "unknown"
            if not await self._check_rate_limit(client_ip):
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="尝试过于频繁，请稍后再试",
                )
            if password != self._access_password:
                await self._record_failed_attempt(client_ip)
                await asyncio.sleep(0.6)
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="认证失败")

            token = secrets.token_urlsafe(32)
            now = time.time()
            async with self._token_lock:
                self._cleanup_tokens_locked()
                self._tokens[token] = {
                    "created_at": now,
                    "last_active": now,
                }
            return {
                "token": token,
                "expires_in": self.session_timeout,
                "readonly_token": self._readonly_token,
                "base_url": self.get_preferred_base_url(),
            }

        @self._app.post("/api/logout")
        async def logout(token: str = Depends(self._auth_dependency())) -> dict[str, str]:
            async with self._token_lock:
                self._tokens.pop(token, None)
            return {"message": "ok"}

        @self._app.get("/api/config")
        async def config(token: str = Depends(self._auth_dependency())) -> dict[str, Any]:
            _ = token
            return {
                "host": self.host,
                "port": self.port,
                "public_base_url": self.get_preferred_base_url(),
                "access_urls": self.get_access_urls(),
                "readonly_token": self._readonly_token,
                "expose_astrbot_data": self.expose_astrbot_data,
                "password_generated": self._password_generated,
            }

        @self._app.get("/api/stats")
        async def stats(token: str = Depends(self._auth_dependency())) -> dict[str, Any]:
            _ = token
            return await self.media_manager.get_stats()

        @self._app.get("/api/categories")
        async def categories(token: str = Depends(self._auth_dependency())) -> dict[str, Any]:
            _ = token
            stats_payload = await self.media_manager.get_stats()
            return {"items": stats_payload.get("categories", [])}

        @self._app.post("/api/categories")
        async def create_category(
            payload: dict[str, Any], token: str = Depends(self._auth_dependency())
        ) -> dict[str, Any]:
            _ = token
            name = str(payload.get("category", "") or "").strip()
            if not name:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="category 不能为空")
            desc = str(payload.get("description", "") or "").strip()
            normalized = await self.media_manager.create_category(name, desc)
            return {"category": normalized, "description": self.category_manager.get_description(normalized)}

        @self._app.patch("/api/categories/{category}")
        async def patch_category(
            category: str,
            payload: dict[str, Any],
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            current = slugify_category(category)
            new_name = str(payload.get("new_name", "") or "").strip()
            description = payload.get("description")
            target = current
            if new_name:
                ok, result = await self.media_manager.rename_category(current, new_name)
                if not ok:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=result)
                target = result
            if description is not None:
                self.category_manager.set_description(target, str(description))
            return {"category": target, "description": self.category_manager.get_description(target)}

        @self._app.delete("/api/categories/{category}")
        async def remove_category(
            category: str,
            remove_files: bool = True,
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            return await self.media_manager.delete_category(category, remove_files=remove_files)

        @self._app.get("/api/media")
        async def list_media(
            category: str = "",
            kind: str = "",
            query: str = "",
            page: int = 1,
            page_size: int = 20,
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            return await self.media_manager.list_media(
                category=category,
                kind=kind,
                query=query,
                page=page,
                page_size=page_size,
            )

        @self._app.get("/api/media/{media_id}")
        async def get_media(
            media_id: int, token: str = Depends(self._auth_dependency())
        ) -> dict[str, Any]:
            _ = token
            record = await self.media_manager.get_by_id(media_id)
            if not record:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="媒体不存在")
            payload = record.to_dict()
            payload["public_url"] = self.build_media_url(record)
            return payload

        @self._app.patch("/api/media/{media_id}")
        async def update_media(
            media_id: int,
            payload: dict[str, Any],
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            updated = await self.media_manager.update_media(
                media_id,
                description=payload.get("description"),
                tags=payload.get("tags"),
                category=payload.get("category"),
            )
            data = updated.to_dict()
            data["public_url"] = self.build_media_url(updated)
            return data

        @self._app.delete("/api/media/{media_id}")
        async def delete_media(
            media_id: int, token: str = Depends(self._auth_dependency())
        ) -> dict[str, Any]:
            _ = token
            ok = await self.media_manager.delete_media(media_id)
            if not ok:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="媒体不存在")
            return {"deleted": True}

        @self._app.post("/api/media/save-url")
        async def save_media_by_url(
            payload: dict[str, Any], token: str = Depends(self._auth_dependency())
        ) -> dict[str, Any]:
            _ = token
            url = str(payload.get("url", "") or "").strip()
            if not url:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="url 不能为空")
            category = str(payload.get("category", "default") or "default")
            description = str(payload.get("description", "") or "")
            filename = str(payload.get("filename", "") or "")
            record = await self.media_manager.save_from_url(
                url,
                category=category,
                description=description,
                filename=filename,
            )
            data = record.to_dict()
            data["public_url"] = self.build_media_url(record)
            return data

        @self._app.post("/api/media/upload")
        async def upload_media(
            category: str = Form("default"),
            description: str = Form(""),
            files: list[UploadFile] = File(default=[]),
            token: str = Depends(self._auth_dependency()),
        ) -> dict[str, Any]:
            _ = token
            if not files:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="未提供上传文件")

            saved: list[dict[str, Any]] = []
            errors: list[str] = []
            for upload in files:
                temp_name = unique_path(
                    self.media_manager.downloader.temp_dir
                    / f"upload_{secrets.token_hex(8)}{Path(upload.filename or '').suffix}"
                )
                size = 0
                try:
                    async with aiofiles.open(temp_name, "wb") as fp:
                        while True:
                            chunk = await upload.read(1024 * 64)
                            if not chunk:
                                break
                            size += len(chunk)
                            if size > self.media_manager.max_file_size:
                                raise ValueError("文件体积超过上限")
                            await fp.write(chunk)
                    record = await self.media_manager.save_from_local_path(
                        str(temp_name),
                        category=category,
                        description=description,
                        filename=upload.filename or temp_name.name,
                        move=True,
                    )
                    item = record.to_dict()
                    item["public_url"] = self.build_media_url(record)
                    saved.append(item)
                except Exception as exc:
                    errors.append(f"{upload.filename or temp_name.name}: {exc}")
                    temp_name.unlink(missing_ok=True)
                finally:
                    await upload.close()
            return {"saved": saved, "errors": errors}

        @self._app.get("/files/{category}/{filename:path}")
        async def serve_media_file(category: str, filename: str, request: Request):
            if not await self._can_access_file(request):
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="无权访问文件")
            file_path = safe_join(self.media_root, category, filename)
            if not file_path.exists() or not file_path.is_file():
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="文件不存在")
            mime, _kind = detect_mime_and_kind(file_path)
            response = FileResponse(path=file_path, media_type=mime or None)
            response.headers["Accept-Ranges"] = "bytes"
            return response

        @self._app.get("/api/data-tree")
        async def data_tree(path: str = "", token: str = Depends(self._auth_dependency())):
            _ = token
            if not self.expose_astrbot_data:
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail="未启用 data 浏览")
            try:
                target = self._resolve_data_path(path)
            except ValueError as exc:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
            if not target.exists():
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="路径不存在")
            if not target.is_dir():
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="目标不是目录")

            children = sorted(
                target.iterdir(),
                key=lambda item: (not item.is_dir(), item.name.lower()),
            )
            items = [self._build_data_item(child) for child in children]
            rel = target.resolve().relative_to(self.data_root).as_posix()
            if rel == ".":
                rel = ""
            parent = ""
            if rel:
                parent = str(Path(rel).parent).replace("\\", "/")
                if parent == ".":
                    parent = ""
            return {"path": rel, "parent": parent, "items": items}

        @self._app.get("/api/data-file")
        async def data_file(path: str, request: Request):
            if not await self._can_access_file(request):
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="无权访问文件")
            if not self.expose_astrbot_data:
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail="未启用 data 浏览")
            try:
                target = self._resolve_data_path(path)
            except ValueError as exc:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
            if not target.exists() or not target.is_file():
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="文件不存在")
            mime, _kind = detect_mime_and_kind(target)
            response = FileResponse(path=target, media_type=mime or None)
            response.headers["Accept-Ranges"] = "bytes"
            return response
