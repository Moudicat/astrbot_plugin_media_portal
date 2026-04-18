from __future__ import annotations

from pathlib import Path

import pytest

from core.utils import (
    detect_mime_and_kind,
    file_sha256,
    format_size,
    generate_password,
    guess_filename_from_url,
    is_container_environment,
    is_kind_allowed,
    is_docker_bridge_ip,
    parse_bool,
    safe_join,
    sanitize_filename,
    slugify_category,
    unique_path,
)


def test_safe_join_rejects_path_traversal(tmp_path: Path) -> None:
    base = tmp_path / "media"
    base.mkdir()

    normal_path = safe_join(base, "cats", "a.jpg")
    assert normal_path == (base / "cats" / "a.jpg").resolve()

    with pytest.raises(ValueError):
        safe_join(base, "..", "outside.txt")


def test_sanitize_filename_and_guess_from_url() -> None:
    assert sanitize_filename("../bad<>name?.JPG") == "bad_name.jpg"

    guessed = guess_filename_from_url("https://example.com/files/%E5%9B%BE%20.png?x=1")
    assert guessed.endswith(".png")
    assert guessed


def test_detect_mime_and_kind_uses_extension_fallback() -> None:
    mime, kind = detect_mime_and_kind(Path("demo.mp3"))
    assert kind == "audio"
    assert mime.startswith("audio/")

    fallback_mime, fallback_kind = detect_mime_and_kind(Path("unknown.bin"))
    assert fallback_kind == "other"
    assert fallback_mime in {"application/octet-stream", "application/macbinary"}


def test_parse_bool_supports_common_inputs() -> None:
    assert parse_bool(None, default=True) is True
    assert parse_bool("on") is True
    assert parse_bool("off", default=True) is False
    assert parse_bool(0) is False


def test_is_docker_bridge_ip() -> None:
    assert is_docker_bridge_ip("172.17.0.1") is True
    assert is_docker_bridge_ip("172.31.255.254") is True
    assert is_docker_bridge_ip("172.16.0.1") is False
    assert is_docker_bridge_ip("192.168.1.10") is False
    assert is_docker_bridge_ip("::1") is False


def test_slugify_category_and_kind_allowed() -> None:
    slug = slugify_category("  My / Album  ")
    assert "/" not in slug
    assert slug.startswith("My_")
    assert "Album" in slug
    assert slugify_category("", default="default_cat") == "default_cat"
    assert is_kind_allowed("Image", ["image", "audio"]) is True
    assert is_kind_allowed("video", ["image", "audio"]) is False


def test_unique_path_file_sha_and_format_size(tmp_path: Path) -> None:
    original = tmp_path / "demo.txt"
    original.write_text("abc", encoding="utf-8")
    duplicate_candidate = unique_path(original)

    assert duplicate_candidate.name == "demo_1.txt"
    assert file_sha256(original) == file_sha256(original)
    assert format_size(1023) == "1023B"
    assert format_size(1024) == "1.0KB"
    assert format_size(1024 * 1024) == "1.0MB"


def test_generate_password_length_constraints() -> None:
    short = generate_password(6)
    normal = generate_password(18)

    assert len(short) == 6
    assert len(normal) == 18
    assert short != normal


def test_is_container_environment_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.0.0.1")
    assert is_container_environment() is True
