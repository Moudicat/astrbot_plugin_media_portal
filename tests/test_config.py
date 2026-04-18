from __future__ import annotations

from pathlib import Path

import core.config as config_mod


def test_load_plugin_settings_defaults_to_plugin_data_mode(
    tmp_path: Path, monkeypatch
) -> None:
    astrbot_data = (tmp_path / "astrbot_data").resolve()
    monkeypatch.setattr(config_mod, "get_astrbot_data_path", lambda: str(astrbot_data))

    settings = config_mod.load_plugin_settings({})

    expected_plugin_data = (
        astrbot_data / "plugin_data" / "astrbot_plugin_media_portal"
    ).resolve()
    assert settings.plugin_data_dir == expected_plugin_data
    assert settings.media_root == (expected_plugin_data / "media").resolve()
    assert settings.media_location_mode == "plugin_data"
    assert settings.media_root.exists()


def test_load_plugin_settings_invalid_location_mode_falls_back(
    tmp_path: Path, monkeypatch
) -> None:
    astrbot_data = (tmp_path / "astrbot_data").resolve()
    monkeypatch.setattr(config_mod, "get_astrbot_data_path", lambda: str(astrbot_data))

    plugin_data_dir = (tmp_path / "custom_plugin_data").resolve()
    settings = config_mod.load_plugin_settings(
        {"storage": {"location_mode": "invalid"}},
        plugin_data_dir=plugin_data_dir,
    )

    assert settings.media_location_mode == "plugin_data"
    assert settings.media_root == (plugin_data_dir / "media").resolve()


def test_load_plugin_settings_supports_astrbot_data_mode(
    tmp_path: Path, monkeypatch
) -> None:
    astrbot_data = (tmp_path / "astrbot_data").resolve()
    monkeypatch.setattr(config_mod, "get_astrbot_data_path", lambda: str(astrbot_data))

    settings = config_mod.load_plugin_settings(
        {"storage": {"location_mode": "astrbot_data"}},
        plugin_data_dir=tmp_path / "plugin_data",
    )

    assert settings.media_location_mode == "astrbot_data"
    assert settings.media_root == (astrbot_data / "media").resolve()


def test_load_plugin_settings_normalizes_webui_and_downloader_values(
    tmp_path: Path, monkeypatch
) -> None:
    astrbot_data = (tmp_path / "astrbot_data").resolve()
    monkeypatch.setattr(config_mod, "get_astrbot_data_path", lambda: str(astrbot_data))

    settings = config_mod.load_plugin_settings(
        {
            "webui": {
                "enabled": "yes",
                "host": "  ",
                "port": "0",
                "session_timeout": 10,
                "public_base_url": "https://example.com/media/",
                "allowed_origins": "https://a.example; https://b.example",
                "readonly_token_ttl": 1,
            },
            "downloader": {
                "max_file_size_mb": "0",
                "allowed_kinds": ["image", "other"],
                "default_move_local": "off",
            },
        },
        plugin_data_dir=tmp_path / "plugin_data",
    )

    assert settings.webui.enabled is True
    assert settings.webui.host == "0.0.0.0"
    assert settings.webui.port == 1
    assert settings.webui.session_timeout == 60
    assert settings.webui.public_base_url == "https://example.com/media"
    assert settings.webui.allowed_origins == ["https://a.example", "https://b.example"]
    assert settings.webui.readonly_token_ttl == 60

    assert settings.downloader.max_file_size_mb == 1
    assert settings.downloader.allowed_kinds == {"image"}
    assert settings.downloader.default_move_local is False


def test_load_plugin_settings_supports_legacy_webui_port(
    tmp_path: Path, monkeypatch
) -> None:
    astrbot_data = (tmp_path / "astrbot_data").resolve()
    monkeypatch.setattr(config_mod, "get_astrbot_data_path", lambda: str(astrbot_data))

    settings = config_mod.load_plugin_settings(
        {"webui_port": 7788},
        plugin_data_dir=tmp_path / "plugin_data",
    )

    assert settings.webui.port == 7788
    assert settings.webui.enabled is False


def test_load_plugin_settings_downloader_allowed_kinds_string(
    tmp_path: Path, monkeypatch
) -> None:
    astrbot_data = (tmp_path / "astrbot_data").resolve()
    monkeypatch.setattr(config_mod, "get_astrbot_data_path", lambda: str(astrbot_data))

    settings = config_mod.load_plugin_settings(
        {"downloader": {"allowed_kinds": "image;video"}},
        plugin_data_dir=tmp_path / "plugin_data",
    )

    assert settings.downloader.allowed_kinds == {"image", "video"}
