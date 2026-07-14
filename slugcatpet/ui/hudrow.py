"""HUD 单猫行：体征 + 左键弹菜单/拖动移 HUD。"""
from __future__ import annotations
from PySide6.QtWidgets import QWidget, QLabel, QGridLayout, QFrame
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QColor, QPainter

from ..behavior import tuning
from ..i18n import t
from .catmenu import pet_label
from .tips import install as install_tip

# 体征行尺寸常量
KARMA_ICON = 22
BAR_W, BAR_H = 88, 10
PIP = 12
_DRAG_THRESH = 3         # 小于此判定点击而非拖动

_BAR_BG = QColor(45, 52, 40)
_BAR_FG = QColor(120, 180, 90)
_ICY = QColor(120, 200, 235)


class _Bar(QWidget):
    def __init__(self, fg=None):
        super().__init__()
        self.setFixedSize(BAR_W, BAR_H)
        self._ratio = 0.0
        self._fg = fg if fg is not None else _BAR_FG

    def set_ratio(self, r):
        r = max(0.0, min(1.0, float(r)))
        if r != self._ratio:
            self._ratio = r
            self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_BAR_BG)
        p.drawRoundedRect(0, 0, BAR_W, BAR_H, 4, 4)
        w = int(BAR_W * self._ratio)
        if w > 0:
            p.setBrush(self._fg)
            p.drawRoundedRect(0, 0, max(w, 4), BAR_H, 4, 4)
        p.end()


class _Pips(QWidget):
    def __init__(self, total):
        super().__init__()
        self._total = int(total)
        self._filled = 0
        gap = 4
        self.setFixedSize(self._total * PIP + (self._total - 1) * gap, PIP)
        self._gap = gap

    def set_filled(self, n):
        n = max(0, min(self._total, int(n)))
        if n != self._filled:
            self._filled = n
            self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        x = 0
        for i in range(self._total):
            p.setBrush(_BAR_FG if i < self._filled else _BAR_BG)
            p.drawRoundedRect(x, 0, PIP, PIP, 3, 3)
            x += PIP + self._gap
        p.end()


class PetRow(QFrame):
    """一只猫的体征行（可拖动/弹菜单/hover 提示）。"""

    def __init__(self, pet, hud):
        super().__init__()
        self.pet = pet          # PetUnit
        self.hud = hud          # HudPanel
        self.setObjectName("hudRow")
        self._drag_from = None
        self._start_tl = None
        self._moved = False
        self._build()
        self.refresh()

    def _build(self):
        grid = QGridLayout(self)
        grid.setContentsMargins(4, 3, 4, 3)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        def name_lbl(text):
            l = QLabel(text)
            l.setObjectName("hudName")
            return l

        self.name = QLabel()
        self.name.setObjectName("hudRowName")
        grid.addWidget(self.name, 0, 0, 1, 3)

        self.karma_icon = QLabel()
        self.karma_icon.setFixedSize(KARMA_ICON, KARMA_ICON)
        self.karma_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.karma_val = QLabel()
        self.karma_val.setObjectName("hudVal")
        grid.addWidget(name_lbl(t("hud_karma")), 1, 0)
        grid.addWidget(self.karma_icon, 1, 1)
        grid.addWidget(self.karma_val, 1, 2)

        self.stam_bar = _Bar()
        grid.addWidget(name_lbl(t("hud_stamina")), 2, 0)
        grid.addWidget(self.stam_bar, 2, 1)

        self.food_pips = _Pips(self.pet.body.food_max)   # 格数按种族上限
        grid.addWidget(name_lbl(t("hud_satiety")), 3, 0)
        grid.addWidget(self.food_pips, 3, 1)

        self.temper_bar = _Bar()
        grid.addWidget(name_lbl(t("hud_affection")), 4, 0)
        grid.addWidget(self.temper_bar, 4, 1)

        self.cold_lbl = name_lbl(t("hud_cold"))
        self.cold_bar = _Bar(fg=_ICY)
        grid.addWidget(self.cold_lbl, 5, 0)
        grid.addWidget(self.cold_bar, 5, 1)
        self._cold_visible = False
        self._karma_frame = None    # 已显示帧名，去重防重复渲染
        self.cold_lbl.setVisible(False)
        self.cold_bar.setVisible(False)

        # hover 提示（随寒冷行显隐现算）
        install_tip(self, self._tip_text)

    def _tip_text(self):
        parts = [t("hud_karma"), t("hud_stamina"), t("hud_satiety"), t("hud_affection")]
        if self._cold_visible:
            parts.append(t("hud_cold"))
        return " · ".join(parts) + "\n" + t("hud_op_hint")

    def refresh(self) -> bool:
        """刷新本行，返回寒冷条显隐是否变化。"""
        pets = list(getattr(self.pet.window, "pets", [self.pet]))
        self.name.setText(pet_label(self.pet, pets))
        body = self.pet.body

        k = int(body.karma)
        frame = f"smallKarma{k}" if k <= 4 else f"smallKarma{k}-9"
        if frame != self._karma_frame:
            pm = self._karma_sprite(frame)
            if pm is not None and not pm.isNull():
                self.karma_icon.setPixmap(pm)
                self._karma_frame = frame
        kmax = int(getattr(body, "karma_max", tuning.KARMA_MAX))   # 随种族不同
        self.karma_val.setText(f"{k + 1}/{kmax + 1}")

        self.stam_bar.set_ratio(max(0.0, min(1.0, float(body.energy))))
        self.food_pips.set_filled(max(0, min(body.food_max, int(body.food))))
        self.temper_bar.set_ratio((max(-1.0, min(1.0, float(body.temper))) + 1.0) * 0.5)

        cold = float(getattr(body, "cold", 0.0))
        show_cold = cold > 0.001 or bool(getattr(self.pet.window, "blizzard_on", False))
        changed = show_cold != self._cold_visible
        if changed:
            self._cold_visible = show_cold
            self.cold_lbl.setVisible(show_cold)
            self.cold_bar.setVisible(show_cold)
        if show_cold:
            self.cold_bar.set_ratio(max(0.0, min(1.0, cold)))
        return changed

    def _karma_sprite(self, frame):
        atlas = getattr(self.pet.window, "atlas", None)
        if atlas is None:
            return None
        try:
            pm = atlas.sprite("ui", frame)
        except Exception:
            return None
        if pm.isNull():
            return pm
        if pm.width() > KARMA_ICON or pm.height() > KARMA_ICON:
            pm = pm.scaled(KARMA_ICON, KARMA_ICON,
                           Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
        return pm

    # 把手：拖动移 HUD，点击弹菜单
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag_from = ev.globalPosition().toPoint()
            self._start_tl = self.hud.frameGeometry().topLeft()
            self._moved = False
            ev.accept()

    def mouseMoveEvent(self, ev):
        if self._drag_from is None or not (ev.buttons() & Qt.MouseButton.LeftButton):
            return
        delta = ev.globalPosition().toPoint() - self._drag_from
        if not self._moved and delta.manhattanLength() <= _DRAG_THRESH:
            return
        self._moved = True
        screen = QGuiApplication.primaryScreen().availableGeometry()
        p = self._start_tl + delta
        x = max(screen.x(), min(screen.x() + screen.width() - self.hud.width(), p.x()))
        y = max(screen.y(), min(screen.y() + screen.height() - self.hud.height(), p.y()))
        self.hud.move(x, y)
        self.hud.params["hud_x"] = x
        self.hud.params["hud_y"] = y
        ev.accept()

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self._drag_from is not None:
            moved = self._moved
            self._drag_from = None
            if not moved:
                self.pet.window.open_cat_menu(self.pet, ev.globalPosition().toPoint())
            ev.accept()
