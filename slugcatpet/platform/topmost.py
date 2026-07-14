"""置顶保持：保住各窗 WS_EX_TOPMOST，前台变更事件即时重申 + 轮询兜底，只补丢失不越置顶同侪。"""
from __future__ import annotations
import sys

_IS_WIN = sys.platform == "win32"

HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
WS_EX_TOPMOST = 0x00000008
GWL_EXSTYLE = -20
EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0002

if _IS_WIN:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32

    # WinEvent 回调签名（win32 参数名）
    WINEVENTPROC = ctypes.WINFUNCTYPE(
        None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
        wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD,
    )

    try:
        _GetWindowLongPtr = _user32.GetWindowLongPtrW
        _GetWindowLongPtr.restype = ctypes.c_void_p
        _GetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int]
    except AttributeError:  # 32位无 Ptr 变体
        _GetWindowLongPtr = _user32.GetWindowLongW

    _user32.SetWindowPos.restype = wintypes.BOOL
    _user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    _user32.SetWinEventHook.restype = wintypes.HANDLE
    _user32.SetWinEventHook.argtypes = [
        wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE, WINEVENTPROC,
        wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
    ]
    _user32.UnhookWinEvent.restype = wintypes.BOOL
    _user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]

    def _win_get_exstyle(hwnd: int) -> int:
        v = _GetWindowLongPtr(wintypes.HWND(hwnd), GWL_EXSTYLE)
        return int(v) if v is not None else 0

    def _win_set_topmost(hwnd: int) -> None:
        # NOACTIVATE：置顶但不抢前台
        _user32.SetWindowPos(wintypes.HWND(hwnd), wintypes.HWND(HWND_TOPMOST),
                             0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def _win_install_hook(callback):
        # 保活 proc 防 GC；SKIPOWNPROCESS 屏蔽自家窗
        proc = WINEVENTPROC(callback)
        hook = _user32.SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND, None, proc, 0, 0,
            WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS)
        return proc, (int(hook) if hook else 0)

    def _win_remove_hook(hook) -> None:
        _user32.UnhookWinEvent(wintypes.HANDLE(hook))


class TopmostKeeper:
    """维持一组窗置顶，仅在丢失样式时重申。"""

    def __init__(self, windows, is_suspended=None, *,
                 get_exstyle=None, set_topmost=None, install_hook=None, remove_hook=None):
        self._windows = list(windows)
        self._is_suspended = is_suspended or (lambda: False)
        if get_exstyle is None or set_topmost is None:
            if _IS_WIN:
                get_exstyle = get_exstyle or _win_get_exstyle
                set_topmost = set_topmost or _win_set_topmost
            else:                                   # 非 Windows：恒真，reassert 空转
                get_exstyle = get_exstyle or (lambda h: WS_EX_TOPMOST)
                set_topmost = set_topmost or (lambda h: None)
        self._get_exstyle = get_exstyle
        self._set_topmost = set_topmost
        self._install_hook = install_hook or (_win_install_hook if _IS_WIN else None)
        self._remove_hook = remove_hook or (_win_remove_hook if _IS_WIN else None)
        self._proc = None
        self._hook = None

    def reassert(self):
        """逐窗补置顶，暂停时跳过。"""
        if self._is_suspended():
            return
        for w in self._windows:
            try:
                if not w.isVisible():
                    continue
                hwnd = int(w.winId())
                if not hwnd:
                    continue
                if not (self._get_exstyle(hwnd) & WS_EX_TOPMOST):
                    self._set_topmost(hwnd)
            except Exception:
                pass

    def start(self):
        """装前台变更钩子；非 Win 靠外部轮询。"""
        if self._hook is not None or self._install_hook is None:
            return
        try:
            self._proc, self._hook = self._install_hook(self._on_foreground)
        except Exception:
            self._proc = self._hook = None

    def stop(self):
        if self._hook and self._remove_hook is not None:
            try:
                self._remove_hook(self._hook)
            except Exception:
                pass
        self._proc = None
        self._hook = None

    def _on_foreground(self, *args):
        # ctypes 回调需吞异常
        try:
            self.reassert()
        except Exception:
            pass
