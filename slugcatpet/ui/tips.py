"""自绘 hover 提示（原生 QToolTip 在此类窗口不弹）。"""
from __future__ import annotations
from typing import Callable
from PySide6.QtWidgets import QLabel, QWidget
from PySide6.QtCore import Qt, QTimer, QEvent, QObject, QPoint
from PySide6.QtGui import QGuiApplication

SHOW_DELAY_MS = 600


class HoverTip(QObject):
    """多控件共享的 hover 提示，Enter 延时弹卡，Leave/按下即藏。"""

    def __init__(self, delay_ms: int = SHOW_DELAY_MS):
        super().__init__()
        self._delay = delay_ms
        self._texts: dict[QWidget, str | Callable[[], str]] = {}
        self._pending: QWidget | None = None
        self._lbl = QLabel("", None)
        self._lbl.setWindowFlags(Qt.WindowType.FramelessWindowHint
                                 | Qt.WindowType.WindowStaysOnTopHint
                                 | Qt.WindowType.ToolTip)
        self._lbl.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._lbl.setStyleSheet(
            "QLabel{color:#fff;background:rgba(20,22,26,235);border-radius:6px;"
            "padding:5px 9px;font-size:12px;}")
        self._lbl.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._show_now)

    def install(self, w: QWidget, text: str | Callable[[], str]) -> None:
        """给控件挂提示；text 可为串或无参 callable。"""
        if w not in self._texts:
            w.installEventFilter(self)
            w.destroyed.connect(lambda _=None, w=w: self._drop(w))
        self._texts[w] = text

    def eventFilter(self, obj, ev):
        try:
            et = ev.type()
        except Exception:
            return False                       # 关停期对象半拆卸，异常一律放行

        if et == QEvent.Type.Enter and obj in self._texts:
            self._pending = obj
            if self._delay <= 0:
                self._show_now()
            else:
                self._timer.start(self._delay)
        elif et in (QEvent.Type.Leave, QEvent.Type.MouseButtonPress, QEvent.Type.Hide):
            self._hide()
        return False

    def _show_now(self):
        # 弹在控件下方，放不下则翻上方
        w = self._pending
        if w is None:
            return
        txt = self._texts.get(w)
        if callable(txt):
            txt = txt()
        if not txt:
            return
        self._lbl.setText(str(txt))
        self._lbl.adjustSize()
        scr = (w.screen() or QGuiApplication.primaryScreen()).availableGeometry()
        pos = w.mapToGlobal(QPoint(0, w.height() + 6))
        x = max(scr.x(), min(pos.x(), scr.x() + scr.width() - self._lbl.width()))
        y = pos.y()
        if y + self._lbl.height() > scr.y() + scr.height():
            y = w.mapToGlobal(QPoint(0, 0)).y() - self._lbl.height() - 6
        self._lbl.move(x, max(scr.y(), y))
        self._lbl.show()
        self._lbl.raise_()

    def _hide(self):
        self._timer.stop()
        self._pending = None
        self._lbl.hide()

    def _drop(self, w):
        self._texts.pop(w, None)
        if self._pending is w:
            self._hide()


_shared: HoverTip | None = None


def install(w: QWidget, text: str | Callable[[], str]) -> HoverTip:
    """模块级共享实例：一行给控件挂提示。"""
    global _shared
    if _shared is None:
        _shared = HoverTip()
    _shared.install(w, text)
    return _shared
