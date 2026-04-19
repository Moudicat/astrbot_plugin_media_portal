from __future__ import annotations

import asyncio

import astrbot_plugin_media_portal.scripts.debug_webui as debug_mod


def test_create_app_defers_async_initialization_to_startup(
    tmp_path, monkeypatch
) -> None:
    calls: list[str] = []

    monkeypatch.setenv("MP_DEBUG_DATA_DIR", str((tmp_path / "plugin").resolve()))
    monkeypatch.setenv("MP_DEBUG_ASTRBOT_DATA_ARG", str((tmp_path / "astrbot").resolve()))
    monkeypatch.setattr(debug_mod, "_print_banner", lambda *_args, **_kwargs: None)

    async def fake_initialize(self) -> None:
        _ = self
        calls.append("initialize")

    async def fake_scan(self) -> dict[str, int]:
        _ = self
        calls.append("scan")
        return {"indexed": 0, "removed": 0, "skipped": 0, "pruned_categories": 0}

    async def fake_close(self) -> None:
        _ = self
        calls.append("close")

    async def fake_cleanup(self) -> None:
        _ = self
        calls.append("cleanup")
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            calls.append("cleanup_cancelled")
            raise

    monkeypatch.setattr(debug_mod.MediaManager, "initialize", fake_initialize, raising=False)
    monkeypatch.setattr(debug_mod.MediaManager, "ensure_scanned", fake_scan, raising=False)
    monkeypatch.setattr(debug_mod.MediaManager, "close", fake_close, raising=False)
    monkeypatch.setattr(debug_mod.WebUIServer, "_periodic_cleanup", fake_cleanup, raising=False)

    app = debug_mod.create_app()
    assert calls == []

    async def scenario() -> None:
        async with app.router.lifespan_context(app):
            await asyncio.sleep(0)

    asyncio.run(scenario())

    assert calls[:2] == ["initialize", "scan"]
    assert "close" in calls
