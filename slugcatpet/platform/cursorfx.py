"""光标劫持：落体→底边锁定，替换系统光标为"忙"样式。"""
from __future__ import annotations
import sys
import atexit

_IS_WIN = sys.platform == "win32"

# 计时单位为 tick（40Hz）；坐标为 Win32 物理像素
T_FALL_GRAV = 1.6
T_CURSOR_LOCK = 200
WATCHDOG_MAX = 400

_ACTIVE = []             # 活动劫持列表

if _IS_WIN:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32

    class _RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    def _clip(x, y):
        r = _RECT(int(x), int(y), int(x) + 1, int(y) + 1)
        return bool(_user32.ClipCursor(ctypes.byref(r)))

    def _unclip():
        _user32.ClipCursor(None)

    def _setpos(x, y):
        _user32.SetCursorPos(int(x), int(y))

    _OCR_IDS = (32512, 32513, 32649)   # OCR_NORMAL/IBEAM/HAND
    _IDC_APPSTARTING = 32650           # 系统"忙"光标
    _SPI_SETCURSORS = 0x0057

    _user32.LoadCursorW.restype = ctypes.c_void_p
    _user32.LoadCursorW.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    _user32.CopyIcon.restype = ctypes.c_void_p
    _user32.CopyIcon.argtypes = (ctypes.c_void_p,)
    _user32.SetSystemCursor.restype = wintypes.BOOL
    _user32.SetSystemCursor.argtypes = (ctypes.c_void_p, wintypes.DWORD)
    _user32.SystemParametersInfoW.restype = wintypes.BOOL
    _user32.SystemParametersInfoW.argtypes = (wintypes.UINT, wintypes.UINT,
                                              ctypes.c_void_p, wintypes.UINT)

    def _set_busy_cursor():
        """替换系统箭头/文本/链接光标为"忙"样式；需 CopyIcon 因 SetSystemCursor 取走所有权。"""
        src = _user32.LoadCursorW(None, _IDC_APPSTARTING)
        if not src:
            return False
        ok = False
        for ocr in _OCR_IDS:
            h = _user32.CopyIcon(src)
            if h and _user32.SetSystemCursor(h, ocr):
                ok = True
        return ok

    def _restore_cursors():
        """从注册表重载全部系统光标恢复默认（幂等）。"""
        _user32.SystemParametersInfoW(_SPI_SETCURSORS, 0, None, 0)
else:
    def _clip(x, y):
        return False

    def _unclip():
        pass

    def _setpos(x, y):
        pass

    def _set_busy_cursor():
        return False

    def _restore_cursors():
        pass


class CursorHijack:
    """光标抛物线落体 + 底边锁定 5s。坐标 = Win32 物理像素（屏幕全局，已由 window 按 dpr 换算）。"""

    def __init__(self, dev_x, dev_y, screen_w, screen_h, screen_x=0, screen_y=0, mock=False,
                 lock_ticks=T_CURSOR_LOCK):
        self.mock = mock or not _IS_WIN
        self.x = float(dev_x)
        self.y = float(dev_y)
        self.vy = 0.0
        self.W = screen_w
        self.H = screen_h
        self.x0 = screen_x
        self.y0 = screen_y
        self.bottom = screen_y + screen_h - 2
        self.phase = "fall"         # fall → lock → done
        self.lock_ticks = int(lock_ticks)
        self.lock_t = 0
        self.watchdog = 0
        self.use_setpos = False     # ClipCursor 失败降级标志
        self.active = True
        _ACTIVE.append(self)
        if not self.mock:
            _set_busy_cursor()

    def update(self) -> bool:
        """推进一帧。返回是否仍活动。"""
        if not self.active:
            return False
        self.watchdog += 1
        if self.watchdog >= WATCHDOG_MAX:
            self.release()
            return False

        if self.phase == "fall":
            self.vy += T_FALL_GRAV
            self.y += self.vy
            if self.y >= self.bottom:
                self.y = self.bottom
                self.vy = 0.0
                self.phase = "lock"
                self.lock_t = 0
        elif self.phase == "lock":
            self.lock_t += 1
            if self.lock_t >= self.lock_ticks:
                self.release()
                return False

        self._apply()
        return True

    def _apply(self):
        if self.mock:
            return
        x = min(max(self.x, self.x0), self.x0 + self.W - 1)
        y = min(max(self.y, self.y0), self.y0 + self.H - 1)
        if not self.use_setpos:
            ok = False
            try:
                ok = _clip(x, y)           # 失败则降级 SetCursorPos
            except Exception:
                ok = False
            if not ok:
                try:
                    _unclip()                      # 先释放旧 clip
                except Exception:
                    pass
                self.use_setpos = True
        if self.use_setpos:
            try:
                _setpos(x, y)
            except Exception:
                pass

    def release(self):
        """释放 ClipCursor。幂等。"""
        if not self.active:
            return
        self.active = False
        self.phase = "done"
        if not self.mock:
            try:
                _unclip()
            except Exception:
                pass
            try:
                _restore_cursors()
            except Exception:
                pass
        try:
            _ACTIVE.remove(self)
        except ValueError:
            pass


def abort_all():
    """释放所有活动劫持。"""
    for h in list(_ACTIVE):
        h.release()
    if _IS_WIN:
        try:
            _unclip()                              # 兜底
        except Exception:
            pass
        try:
            _restore_cursors()                     # 兜底
        except Exception:
            pass


atexit.register(abort_all)
