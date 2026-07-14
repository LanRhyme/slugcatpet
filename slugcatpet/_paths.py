"""Resolve asset and writable data paths across dev and frozen (PyInstaller) contexts."""
from __future__ import annotations
import sys
from pathlib import Path


def base_dir() -> Path:
    """Frozen unpacked root / dev repository root."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    """Read-only resource root (assets, layouts)."""
    if getattr(sys, "frozen", False):
        return base_dir() / "slugcatpet" / "resources"
    return Path(__file__).resolve().parent / "resources"


def user_dir() -> Path:
    """User writable data directory (~/.slugcatpet); migrates legacy ~/.saintpet if present."""
    d = Path.home() / ".slugcatpet"
    old = Path.home() / ".saintpet"
    if not d.exists() and old.is_dir():
        try:
            old.rename(d)
        except Exception:
            pass
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return d


def assets_dir() -> Path:
    """用户导入的图集目录（~/.slugcatpet/assets）。"""
    return user_dir() / "assets"


def bundled_assets_dir() -> Path:
    """仓库内资产目录（开发降级用）。"""
    return resource_dir() / "assets"
