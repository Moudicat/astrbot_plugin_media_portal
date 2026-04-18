from __future__ import annotations

import logging
import sys
import types
from pathlib import Path


def _ensure_package_parent_on_syspath() -> None:
    """Allow importing as ``astrbot_plugin_media_portal.*`` in tests."""
    repo_root = Path(__file__).resolve().parent.parent
    package_parent = repo_root.parent
    parent_text = str(package_parent)
    if parent_text not in sys.path:
        sys.path.insert(0, parent_text)


def _install_astrbot_shim() -> None:
    """Provide a minimal astrbot.api.logger shim for unit tests."""
    api_module = sys.modules.get("astrbot.api")
    if api_module is not None:
        if not hasattr(api_module, "logger"):
            setattr(api_module, "logger", logging.getLogger("astrbot.test"))
        return

    astrbot_module = sys.modules.get("astrbot")
    if astrbot_module is None:
        astrbot_module = types.ModuleType("astrbot")
        sys.modules["astrbot"] = astrbot_module

    api_module = types.ModuleType("astrbot.api")
    api_module.logger = logging.getLogger("astrbot.test")
    setattr(astrbot_module, "api", api_module)
    sys.modules["astrbot.api"] = api_module


_install_astrbot_shim()
_ensure_package_parent_on_syspath()
