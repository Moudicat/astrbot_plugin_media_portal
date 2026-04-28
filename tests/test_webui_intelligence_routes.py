"""WebUI 中 ``/api/intelligence/**`` 路由的集成测试。

通过最小可运行的 ``WebUIServer`` 实例 + ``TestClient``，校验：
- ``/api/config`` 暴露 ``intelligence`` 摘要；
- 列表 / 启动 / 取消 / 删除路由的鉴权与基本行为；
- 服务端在 ``intelligence_manager=None`` 时返回 503。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from astrbot_plugin_media_portal.core.intelligence import IntelligenceManager
from astrbot_plugin_media_portal.core.intelligence.models import ModelFile, ModelSpec
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


def _make_dummy_spec() -> ModelSpec:
    return ModelSpec(
        key="dummy-model",
        capability="clip",
        display_name="Dummy",
        description="测试用",
        files=(
            ModelFile(
                relative_path="x.bin",
                url="https://huggingface.co/x.bin",
                size_bytes=4,
            ),
        ),
    )


def _login(client: TestClient) -> str:
    resp = client.post("/api/login", json={"password": "pw-intelligence"})
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def _build_server(
    tmp_path: Path, *, with_intelligence: bool
) -> tuple[WebUIServer, IntelligenceManager | None]:
    media_root = (tmp_path / "media").resolve()
    plugin_data_dir = (tmp_path / "plugin_data").resolve()
    data_root = (tmp_path / "astrbot_data").resolve()
    for p in (media_root, plugin_data_dir, data_root):
        p.mkdir(parents=True, exist_ok=True)

    manager: IntelligenceManager | None = None
    if with_intelligence:
        manager = IntelligenceManager(
            plugin_data_dir=plugin_data_dir,
            feature_enabled=True,
            clip_enabled=True,
            face_enabled=False,
            hf_mirror_url="",
            models=[_make_dummy_spec()],
        )

    server = WebUIServer(
        media_manager=_MediaManager(media_root, plugin_data_dir),
        category_manager=_CategoryManager(),
        config={
            "enabled": True,
            "host": "127.0.0.1",
            "port": 7003,
            "access_password": "pw-intelligence",
            "session_timeout": 3600,
            "public_base_url": "",
            "expose_astrbot_data": False,
            "allowed_origins": [],
            "readonly_token_ttl": 3600,
            "share_url_ttl": 3600,
            "data_token_ttl": 3600,
        },
        data_root=data_root,
        intelligence_manager=manager,
    )
    return server, manager


def test_config_reports_intelligence_summary(tmp_path: Path) -> None:
    server, _ = _build_server(tmp_path, with_intelligence=True)
    client = TestClient(server.app)
    token = _login(client)
    resp = client.get("/api/config", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    payload = resp.json()
    intel = payload.get("intelligence")
    assert intel is not None
    assert intel["feature_enabled"] is True
    assert intel["clip_enabled"] is True
    assert intel["face_enabled"] is False
    assert intel["clip_ready"] is False  # 模型尚未下载


def test_config_without_manager_disables_intelligence(tmp_path: Path) -> None:
    server, _ = _build_server(tmp_path, with_intelligence=False)
    client = TestClient(server.app)
    token = _login(client)
    resp = client.get("/api/config", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    intel = resp.json()["intelligence"]
    assert intel["feature_enabled"] is False
    assert intel["clip_enabled"] is False


def test_intelligence_models_list_and_404(tmp_path: Path) -> None:
    server, _ = _build_server(tmp_path, with_intelligence=True)
    client = TestClient(server.app)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/api/intelligence/models", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["feature_enabled"] is True
    keys = [m["key"] for m in body["models"]]
    assert "dummy-model" in keys

    resp404 = client.post(
        "/api/intelligence/models/not-exist/download", headers=headers
    )
    assert resp404.status_code == 404


def test_intelligence_routes_503_without_manager(tmp_path: Path) -> None:
    server, _ = _build_server(tmp_path, with_intelligence=False)
    client = TestClient(server.app)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/api/intelligence/models", headers=headers)
    assert resp.status_code == 503


def test_face_routes_503_when_disabled(tmp_path: Path) -> None:
    server, _ = _build_server(tmp_path, with_intelligence=True)
    client = TestClient(server.app)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/api/intelligence/face/status", headers=headers)
    assert resp.status_code in (200, 503)
    body = resp.json()
    if resp.status_code == 200:
        assert body["face_count"] == 0
        assert body["person_count"] == 0
        assert body["engine_ready"] is False

    # 列出 persons 在未启用时应返回 503
    resp_list = client.get("/api/intelligence/face/persons", headers=headers)
    assert resp_list.status_code == 503

    # recluster / merge 在未启用时同样 503
    resp_recluster = client.post(
        "/api/intelligence/face/recluster", headers=headers
    )
    assert resp_recluster.status_code == 503


def test_face_routes_when_enabled(tmp_path: Path) -> None:
    """启用 face_enabled 后路由应返回 200，但因模型未就绪 engine_ready=False。"""

    server, manager = _build_server(tmp_path, with_intelligence=True)
    assert manager is not None
    manager.update_settings(face_enabled=True)
    assert manager.face_enabled is True

    client = TestClient(server.app)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/api/intelligence/face/status", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["engine_ready"] is False
    assert body["face_count"] == 0
    assert body["person_count"] == 0

    # 列表（store 会被惰性创建，返回空列表）
    resp_list = client.get("/api/intelligence/face/persons", headers=headers)
    assert resp_list.status_code == 200
    assert resp_list.json()["persons"] == []

    # 缺失 target_id 应返回 400
    resp_merge = client.post(
        "/api/intelligence/face/persons/merge",
        headers=headers,
        json={},
    )
    assert resp_merge.status_code == 400

    # 缺失 face_ids 应返回 400
    resp_split = client.post(
        "/api/intelligence/face/persons/1/split",
        headers=headers,
        json={"face_ids": []},
    )
    assert resp_split.status_code == 400

    # 不存在的 person 详情
    resp_404 = client.get(
        "/api/intelligence/face/persons/9999", headers=headers
    )
    assert resp_404.status_code == 404





def test_intelligence_patch_settings(tmp_path: Path) -> None:
    server, manager = _build_server(tmp_path, with_intelligence=True)
    assert manager is not None
    client = TestClient(server.app)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.patch(
        "/api/intelligence/settings",
        headers=headers,
        json={
            "feature_enabled": False,
            "clip_enabled": False,
            "face_enabled": True,
            "hf_mirror_url": "https://hf-mirror.com",
            "max_concurrent_downloads": 2,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["feature_enabled"] is False
    # 由于关闭了总开关，子能力的「真正可用」应当也回退。
    assert body["clip_enabled"] is False
    # face_enabled=True 但 feature_enabled=False，因此 manager.face_enabled 仍为 False
    assert body["face_enabled"] is False
    assert body["hf_mirror_url"] == "https://hf-mirror.com"

    # 取消下载（没有任务也应该返回 cancelled=False，而不是 500）
    resp_cancel = client.post(
        "/api/intelligence/models/dummy-model/cancel", headers=headers
    )
    assert resp_cancel.status_code == 200
    assert resp_cancel.json()["cancelled"] is False


def test_intelligence_settings_persist_to_plugin_data(tmp_path: Path) -> None:
    plugin_data_dir = (tmp_path / "plugin_data").resolve()
    models = [_make_dummy_spec()]
    manager = IntelligenceManager(
        plugin_data_dir=plugin_data_dir,
        feature_enabled=False,
        clip_enabled=False,
        face_enabled=False,
        hf_mirror_url="",
        models=models,
    )
    manager.update_settings(
        feature_enabled=True,
        clip_enabled=True,
        face_enabled=True,
        hf_mirror_url="https://hf-mirror.com",
        max_concurrent_downloads=2,
        face_min_det_score=0.72,
        face_min_face_size=88,
        face_min_blur_var=42.5,
    )

    restored = IntelligenceManager(
        plugin_data_dir=plugin_data_dir,
        feature_enabled=False,
        clip_enabled=False,
        face_enabled=False,
        hf_mirror_url="",
        models=models,
    )

    assert restored.feature_enabled is True
    assert restored.clip_enabled is True
    assert restored.face_enabled is True
    assert restored.hf_mirror_url == "https://hf-mirror.com"
    assert restored.face_quality_thresholds == {
        "min_det_score": 0.72,
        "min_face_size": 88.0,
        "min_blur_var": 42.5,
    }
