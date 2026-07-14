"""Windows 全局热键注册/分发，非 Win 平台降级。"""
from __future__ import annotations
import sys
from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN = 0x0001, 0x0002, 0x0004, 0x0008
MOD_NOREPEAT = 0x4000
VK_ESCAPE = 0x1B
HK_PLACE_ESC = 4   # 放置模式 Esc 热键 id，1/2/3 见 main.py

_IS_WIN = sys.platform == "win32"
if _IS_WIN:
    import ctypes
    from ctypes import wintypes
    _user32 = ctypes.windll.user32


class HotkeyFilter(QObject, QAbstractNativeEventFilter):
    """装到 QApplication 上，命中热键 emit triggered(id)。
    多继承需单一 super().__init__()，退出需 removeNativeEventFilter，否则报错。"""
    triggered = Signal(int)

    def __init__(self):
        super().__init__()
        self._ids: list[int] = []

    def register(self, hk_id: int, mods: int, vk: int) -> bool:
        """注册系统级热键，组合键被占返回 False。"""
        if not _IS_WIN:
            return False
        if _user32.RegisterHotKey(None, hk_id, mods | MOD_NOREPEAT, vk):
            self._ids.append(hk_id)
            return True
        return False

    def unregister(self, hk_id: int) -> None:
        """注销单个热键；未注册的 id 忽略。"""
        if not _IS_WIN or hk_id not in self._ids:
            return
        _user32.UnregisterHotKey(None, hk_id)
        self._ids.remove(hk_id)

    def unregister_all(self) -> None:
        if not _IS_WIN:
            return
        for hk_id in self._ids:
            _user32.UnregisterHotKey(None, hk_id)
        self._ids.clear()

    def nativeEventFilter(self, eventType, message):
        # PySide6 约定返回 (handled: bool, result: int)
        if _IS_WIN and eventType == b"windows_generic_MSG":
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            if msg.message == WM_HOTKEY:
                self.triggered.emit(int(msg.wParam))
        return False, 0
