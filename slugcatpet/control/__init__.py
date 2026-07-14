"""手动键盘操控子包。"""
from . import moves, keymap, session  # 顶层 import：PyInstaller 静态收集保险

__all__ = ["moves", "keymap", "session"]
