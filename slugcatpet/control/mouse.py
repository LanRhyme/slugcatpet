"""输入层：命中测试 + 抓取-拖拽-甩出 + 动态穿透。"""
from __future__ import annotations
import sys
import math

_IS_WIN = sys.platform == "win32"

# 命中半径（逻辑 px）：三抓点圆
GRAB_RAD_HEAD = 9.0
GRAB_RAD_BODY = 9.0
GRAB_RAD_HIP = 8.0
HOVER_PAD = 4.0
GRAB_PAD = 5.0
TETHER_VEL_CAP = 14.0    # 桌宠护栏


def hit_test(body, gfx, cursor, pad=GRAB_PAD):
    """命中三抓点之一 → 返回 ('head'/'body'/'hip', 对应 chunk)；否则 (None,None)。"""
    if cursor is None:
        return None, None
    cx, cy = cursor
    hx, hy = gfx.head.x, gfx.head.y
    c0, c1 = body.chunk0, body.chunk1
    cands = [
        ("head", c0, hx, hy, GRAB_RAD_HEAD + pad),
        ("body", c0, c0.x, c0.y, GRAB_RAD_BODY + pad),
        ("hip", c1, c1.x, c1.y, GRAB_RAD_HIP + pad),
    ]
    best, bestd, bestc = None, 1e9, None
    for name, chunk, px, py, r in cands:
        d = math.hypot(cx - px, cy - py)
        if d <= r and d < bestd:
            best, bestd, bestc = name, d, chunk
    return best, bestc


def is_over(body, gfx, cursor, pad=HOVER_PAD):
    """拂过检测：光标在三抓点圆 ∪ 部件 bbox（外扩 pad）内。"""
    if cursor is None:
        return False
    name, _ = hit_test(body, gfx, cursor, pad=pad)
    if name is not None:
        return True
    cx, cy = cursor
    xs = [body.chunk0.x, body.chunk1.x, gfx.head.x]
    ys = [body.chunk0.y, body.chunk1.y, gfx.head.y]
    minx, maxx = min(xs) - 11 - pad, max(xs) + 11 + pad
    miny, maxy = min(ys) - 11 - pad, max(ys) + 14 + pad
    return minx <= cx <= maxx and miny <= cy <= maxy


class GrabController:
    """抓取-拖拽-甩出。钉对应 chunk 的 pos+vel；松手保留隐式速度。"""

    def __init__(self, body, gfx):
        self.body = body
        self.gfx = gfx
        self.point = None
        self.chunk = None
        self.frames = 0
        self._last = None          # 上帧光标位置

    @property
    def active(self):
        return self.chunk is not None

    def begin(self, cursor):
        name, chunk = hit_test(self.body, self.gfx, cursor)
        if chunk is None:
            return False
        self.point, self.chunk = name, chunk
        chunk.pinned = True
        chunk.x, chunk.y = cursor
        chunk.vx = chunk.vy = 0.0
        self._last = tuple(cursor)
        self.frames = 0
        return True

    def drag(self, cursor):
        if self.chunk is None:
            return
        cx, cy = cursor
        if self._last is not None:
            vx = cx - self._last[0]
            vy = cy - self._last[1]
            sp = math.hypot(vx, vy)
            if sp > TETHER_VEL_CAP:
                k = TETHER_VEL_CAP / sp
                vx *= k
                vy *= k
            self.chunk.vx = vx
            self.chunk.vy = vy
        self.chunk.x, self.chunk.y = cx, cy
        self._last = (cx, cy)

    def tick(self):
        """每帧推进抓住计时（按住期间）。"""
        if self.chunk is not None:
            self.frames += 1

    def end(self):
        """松手：解钉 + 限速保留速度（甩出）。返回是否曾在抓取。"""
        if self.chunk is None:
            return False
        c = self.chunk
        sp = math.hypot(c.vx, c.vy)
        if sp > TETHER_VEL_CAP:
            k = TETHER_VEL_CAP / sp
            c.vx *= k
            c.vy *= k
        c.pinned = False
        self.chunk = None
        self.point = None
        self._last = None
        return True

    def force_release(self):
        """强制脱手（飞升触发）：解钉但不保留速度。"""
        if self.chunk is not None:
            self.chunk.pinned = False
            self.chunk.vx = self.chunk.vy = 0.0
        self.chunk = None
        self.point = None
        self._last = None
        self.frames = 0


# Win32 动态穿透
if _IS_WIN:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32
    _GWL_EXSTYLE = -20
    _WS_EX_TRANSPARENT = 0x00000020
    _WS_EX_LAYERED = 0x00080000

    try:
        _GetWindowLongPtr = _user32.GetWindowLongPtrW
        _SetWindowLongPtr = _user32.SetWindowLongPtrW
        _GetWindowLongPtr.restype = ctypes.c_void_p
        _GetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int]
        _SetWindowLongPtr.restype = ctypes.c_void_p
        _SetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
    except AttributeError:  # 32-bit Python：无 Ptr 变体
        _GetWindowLongPtr = _user32.GetWindowLongW
        _SetWindowLongPtr = _user32.SetWindowLongW


def set_passthrough(hwnd: int, passthrough: bool) -> None:
    """动态切换鼠标穿透；True 穿透、False 接收。"""
    if _IS_WIN:
        if not hwnd:
            return
        ex = _GetWindowLongPtr(hwnd, _GWL_EXSTYLE)
        if ex is None:
            return
        ex = int(ex)
        new = (ex | _WS_EX_TRANSPARENT) if passthrough else (ex & ~_WS_EX_TRANSPARENT)
        new |= _WS_EX_LAYERED
        if new != ex:
            _SetWindowLongPtr(hwnd, _GWL_EXSTYLE, ctypes.c_void_p(new) if _IS_WIN else new)
    elif sys.platform.startswith("linux"):
        _set_passthrough_x11(hwnd, passthrough)

_x11_display = None
_xfixes = None
_xlib = None
_x11_init_done = False

def _init_x11():
    global _x11_display, _xfixes, _xlib, _x11_init_done
    if _x11_init_done:
        return
    _x11_init_done = True
    import ctypes
    try:
        _xlib = ctypes.cdll.LoadLibrary('libX11.so.6')
        _xfixes = ctypes.cdll.LoadLibrary('libXfixes.so.3')
        
        _xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        _xlib.XOpenDisplay.restype = ctypes.c_void_p
        
        _xfixes.XFixesCreateRegion.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
        _xfixes.XFixesCreateRegion.restype = ctypes.c_ulong
        
        _xfixes.XFixesSetWindowShapeRegion.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
        
        _xfixes.XFixesDestroyRegion.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        
        _xlib.XFlush.argtypes = [ctypes.c_void_p]
        
        _x11_display = _xlib.XOpenDisplay(None)
    except Exception as e:
        print("X11 init failed", e)

def _set_passthrough_x11(hwnd: int, passthrough: bool):
    _init_x11()
    if not _x11_display or not _xfixes or not _xlib:
        return
    import ctypes
    ShapeInput = 2
    if passthrough:
        region = _xfixes.XFixesCreateRegion(_x11_display, None, 0)
        _xfixes.XFixesSetWindowShapeRegion(_x11_display, ctypes.c_ulong(hwnd), ShapeInput, 0, 0, region)
        _xfixes.XFixesDestroyRegion(_x11_display, region)
    else:
        _xfixes.XFixesSetWindowShapeRegion(_x11_display, ctypes.c_ulong(hwnd), ShapeInput, 0, 0, 0)
    _xlib.XFlush(_x11_display)
