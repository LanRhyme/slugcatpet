"""控制 HUD：受控猫键盘输入窗，失焦暂停。"""
from __future__ import annotations
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QLayout
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication

from ..i18n import t
from ..control.input import InputPackage
from ..control.keymap import load_keymap, key_display_name
from .catmenu import pet_label

WATCH_MS = 200
BOTTOM_MARGIN = 24

_PANEL_QSS = (
    "#ctrlPanel{background:rgba(30,34,40,235);border-radius:10px;border:1px solid #4a5a3a;}"
    "#ctrlTitle{color:#aef156;font-size:13px;font-weight:bold;}"
    "#ctrlKeys{color:#cfe8b8;font-size:11px;}"
    "QPushButton{background:transparent;color:#9fc080;border:1px solid #4a5a3a;"
    "border-radius:8px;font-size:12px;padding:5px 12px;}"
    "QPushButton:hover{background:rgba(120,150,100,40);}")

_PAUSED_QSS = "color:#e8c86a;font-weight:bold;"


class ControlHud(QWidget):
    """受控会话键盘入口窗，current_input() 供 session provider。"""

    def __init__(self, window, pet):
        super().__init__()
        self._window = window
        self.pet = pet
        self._held = set()      # 当前按住的按键
        self._paused = False
        self._drag = None
        self._keymap = load_keymap()

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)   # 勿设 WA_ShowWithoutActivating，键盘唯一入口

        self._build()
        self._place()

        self._watch = QTimer(self)
        self._watch.timeout.connect(self._check_session)
        self._watch.start(WATCH_MS)

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        panel = QWidget()
        panel.setObjectName("ctrlPanel")
        panel.setStyleSheet(_PANEL_QSS)
        box = QVBoxLayout(panel)
        box.setContentsMargins(14, 10, 14, 10)
        box.setSpacing(6)

        title = QLabel(t("ctrlhud_title", name=pet_label(self.pet, list(self._window.pets))))
        title.setObjectName("ctrlTitle")
        box.addWidget(title)

        k = {a: key_display_name(a).upper() for a in ("left", "right", "up", "down", "jump")}
        self._keys_text = t("ctrlhud_keys",
                            move=k["up"] + k["left"] + k["down"] + k["right"],
                            jump=k["jump"])
        self._keys = QLabel(self._keys_text)
        self._keys.setObjectName("ctrlKeys")
        box.addWidget(self._keys)

        btn = QPushButton(t("ctrlhud_exit"))
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # 防空格触发按钮
        btn.clicked.connect(lambda: self._window.stop_control())
        box.addWidget(btn)
        outer.addWidget(panel)

    def _place(self):
        # 默认屏底中央
        self.layout().activate()
        size = self.sizeHint()
        screen = QGuiApplication.primaryScreen().availableGeometry()
        x = screen.x() + (screen.width() - size.width()) // 2
        y = screen.y() + screen.height() - size.height() - BOTTOM_MARGIN
        self.move(x, y)

    # 输入 provider（暂停返零包防冻结）
    def current_input(self) -> InputPackage:
        if self._paused:
            return InputPackage()
        km, held = self._keymap, self._held

        def down(action):
            k = km.get(action)
            return k is not None and k in held

        x = (1 if down("right") else 0) - (1 if down("left") else 0)
        y = (1 if down("up") else 0) - (1 if down("down") else 0)
        return InputPackage(x=x, y=y, jmp=down("jump"),
                            pckp=down("grab"), thrw=down("throw"))

    def _check_session(self):
        # 会话失效则自关
        if not getattr(self.pet, "controlled", False) or self.pet not in self._window.pets:
            self._window.stop_control()

    def _set_paused(self, paused: bool):
        if paused == self._paused:
            return
        self._paused = paused
        self._held.clear()
        self._keys.setText(t("ctrlhud_paused") if paused else self._keys_text)
        self._keys.setStyleSheet(_PAUSED_QSS if paused else "")
        self.setWindowOpacity(0.7 if paused else 1.0)

    # 焦点：show 即抢焦（需同步栈内）
    def showEvent(self, e):
        super().showEvent(e)
        self.activateWindow()
        self.raise_()
        self.setFocus()

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self._set_paused(False)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self._set_paused(True)

    def keyPressEvent(self, e):
        if e.isAutoRepeat():
            return
        if e.key() == Qt.Key.Key_Escape:
            self._window.stop_control()
            return
        self._held.add(int(e.key()))

    def keyReleaseEvent(self, e):
        if e.isAutoRepeat():
            return
        self._held.discard(int(e.key()))

    # 拖动（钳屏内），点击恢焦
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.activateWindow()
            self.setFocus()
            ev.accept()

    def mouseMoveEvent(self, ev):
        if self._drag is not None and ev.buttons() & Qt.MouseButton.LeftButton:
            screen = QGuiApplication.primaryScreen().availableGeometry()
            p = ev.globalPosition().toPoint() - self._drag
            x = max(screen.x(), min(screen.x() + screen.width() - self.width(), p.x()))
            y = max(screen.y(), min(screen.y() + screen.height() - self.height(), p.y()))
            self.move(x, y)
            ev.accept()

    def mouseReleaseEvent(self, ev):
        self._drag = None
        ev.accept()
