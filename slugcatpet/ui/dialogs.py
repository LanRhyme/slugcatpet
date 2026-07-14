"""自绘卡片弹窗：show()=非模态，open()=WindowModal，不走 exec。"""
from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QRadioButton, QButtonGroup)
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QGuiApplication

# 壳级 QSS：防父窗样式渗透
_CARD_QSS = (
    "#cardShell{background:transparent;}"
    "#cardRoot{background:rgba(28,32,38,238);border-radius:14px;border:1px solid #4a5a3a;}"
    "#cardTitle{color:#cfe8b8;font-size:15px;font-weight:600;background:transparent;}"
    "#cardText{color:#e8f5d8;font-size:13px;background:transparent;}"
    "QLabel{background:transparent;}"
    "QPushButton{font-size:12px;padding:6px 14px;border-radius:8px;}"
    "#btnPrimary{background:#6aa34a;color:#0f1a08;font-weight:600;border:none;}"
    "#btnPrimary:hover{background:#7cb45a;}"
    "#btnGhost{background:transparent;color:#9fc080;border:1px solid #4a5a3a;}"
    "#btnGhost:hover{background:rgba(120,150,100,40);}"
    "#btnDanger{background:#8c3b3b;color:#f5ded8;font-weight:600;border:none;}"
    "#btnDanger:hover{background:#a34848;}"
    "QRadioButton{color:#e8f5d8;font-size:12px;spacing:8px;background:transparent;}"
    "QRadioButton::indicator{width:13px;height:13px;border-radius:7px;"
    "border:1px solid #4a5a3a;background:#2d3428;}"
    "QRadioButton::indicator:checked{background:#7cb45a;border-color:#7cb45a;}")

_BTN_KIND = {"primary": "btnPrimary", "ghost": "btnGhost", "danger": "btnDanger"}


class CardDialog(QDialog):
    """透明壳+卡片弹窗基类，空白区可拖动。"""

    def __init__(self, title: str, parent=None, width: int = 300):
        super().__init__(parent)
        self.setObjectName("cardShell")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._drag_off = None
        self._finished = False
        self._card = QWidget(self)
        self._card.setObjectName("cardRoot")
        self._card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._card.setFixedWidth(width)
        col = QVBoxLayout(self._card)
        col.setContentsMargins(24, 20, 24, 18)
        col.setSpacing(12)
        lbl = QLabel(title)
        lbl.setObjectName("cardTitle")
        col.addWidget(lbl)
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        col.addLayout(self.body)
        self._btn_row = QHBoxLayout()
        self._btn_row.setSpacing(10)
        self._btn_row.addStretch(1)
        col.addLayout(self._btn_row)
        self.setStyleSheet(_CARD_QSS)

    def done(self, result):
        if self._finished:               # 防二次发射 finished
            return
        self._finished = True
        super().done(result)

    def add_button(self, text: str, kind: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName(_BTN_KIND[kind])
        self._btn_row.addWidget(btn)
        return btn

    def place_center(self, host=None, offset: QPoint | None = None):
        """居中于 host（无则主屏），钳入屏内。"""
        self._card.adjustSize()
        size = self._card.size()
        self.resize(size)
        self._card.setGeometry(0, 0, size.width(), size.height())
        if host is not None:
            g = host.frameGeometry()
            x = g.x() + (g.width() - size.width()) // 2
            y = g.y() + (g.height() - size.height()) // 2
        else:
            scr = QGuiApplication.primaryScreen().availableGeometry()
            x = scr.x() + (scr.width() - size.width()) // 2
            y = scr.y() + (scr.height() - size.height()) // 3
        if offset is not None:
            x += offset.x()
            y += offset.y()
        self.move(self._clamped(QPoint(x, y)))

    def _clamped(self, pos: QPoint) -> QPoint:
        scr = QGuiApplication.primaryScreen().availableGeometry()
        x = max(scr.x(), min(pos.x(), scr.x() + scr.width() - self.width()))
        y = max(scr.y(), min(pos.y(), scr.y() + scr.height() - self.height()))
        return QPoint(x, y)

    # 卡片空白区拖动
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag_off = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._drag_off is not None and (ev.buttons() & Qt.MouseButton.LeftButton):
            self.move(self._clamped(ev.globalPosition().toPoint() - self._drag_off))
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._drag_off = None
        super().mouseReleaseEvent(ev)


class ConfirmDialog(CardDialog):
    """确认弹窗（Accepted=确认）；cancel_btn 供外部程序化点击。"""

    def __init__(self, title: str, text: str, confirm_text: str, cancel_text: str,
                 parent=None, width: int = 300):
        super().__init__(title, parent, width)
        lbl = QLabel(text)
        lbl.setObjectName("cardText")
        lbl.setWordWrap(True)
        self.body.addWidget(lbl)
        self.confirm_btn = self.add_button(confirm_text, "danger")
        self.confirm_btn.clicked.connect(self.accept)
        self.cancel_btn = self.add_button(cancel_text, "primary")
        self.cancel_btn.setDefault(True)
        self.cancel_btn.clicked.connect(self.reject)

    def showEvent(self, ev):
        super().showEvent(ev)
        self.cancel_btn.setFocus()      # 默认焦点在取消上


class PickDialog(CardDialog):
    """选择弹窗；Accepted 后读 selected_index()。"""

    def __init__(self, title: str, label: str, items: list, ok_text: str, cancel_text: str,
                 parent=None, current: int = 0, width: int = 320):
        super().__init__(title, parent, width)
        lbl = QLabel(label)
        lbl.setObjectName("cardText")
        lbl.setWordWrap(True)
        self.body.addWidget(lbl)
        self._group = QButtonGroup(self)
        for i, item in enumerate(items):
            rb = QRadioButton(item)
            rb.setChecked(i == current)
            self._group.addButton(rb, i)
            self.body.addWidget(rb)
        self.cancel_btn = self.add_button(cancel_text, "ghost")
        self.cancel_btn.clicked.connect(self.reject)
        self.ok_btn = self.add_button(ok_text, "primary")
        self.ok_btn.setDefault(True)
        self.ok_btn.clicked.connect(self.accept)

    def selected_index(self) -> int:
        return max(0, self._group.checkedId())
