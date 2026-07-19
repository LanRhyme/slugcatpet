"""设置窗：猫增删/环境单选/HUD 开关，关窗即写盘。"""
from __future__ import annotations
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QCheckBox, QRadioButton, QButtonGroup, QFrame, QDialog)
from PySide6.QtCore import Qt

from ..cats import REGISTRY
from ..i18n import t
from .._paths import resource_dir
from ..window import MAX_PETS
from .catmenu import variant_label, pet_label
from .dialogs import ConfirmDialog, PickDialog

_VARIANTS = tuple(REGISTRY)

_CHECK = (resource_dir() / "icons" / "check.svg").as_posix()   # 缺 QtSvg 时退化为高亮块

_QSS = (
    "QWidget{background:rgba(30,34,40,245);color:#e8f5d8;font-size:12px;}"
    "QLabel{color:#e8f5d8;}"
    "#secHeader{color:#aef156;font-size:13px;font-weight:bold;}"
    "#dim{color:#9fc080;}"
    "QPushButton{color:#e8f5d8;background:rgba(60,70,55,255);border:1px solid #4a5a3a;"
    "border-radius:5px;padding:4px 12px;}"
    "QPushButton:enabled:hover{background:rgba(80,100,70,255);}"
    "QPushButton:disabled{color:#777;background:rgba(45,48,52,255);}"
    "QCheckBox{color:#e8f5d8;}"
    "QRadioButton{color:#e8f5d8;spacing:8px;}"
    "QRadioButton::indicator{width:16px;height:16px;border-radius:8px;"
    "border:1px solid #52633f;background:#262b22;}"
    "QRadioButton::indicator:hover{border-color:#7c9a52;}"
    f"QRadioButton::indicator:checked{{border:2px solid #aef156;background:#aef156;"
    f"image:url({_CHECK});}}")


class SettingsWindow(QWidget):
    def __init__(self, window, hud, write_state):
        super().__init__()
        self._window = window
        self._hud = hud
        self._write_state = write_state
        window._settings_panel = self    # 供 window 反向同步世界态
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle(t("settings_title"))
        self.setStyleSheet(_QSS)
        self.setMinimumWidth(280)
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(16, 14, 16, 14)
        self._outer.setSpacing(10)
        self._body = None
        self._dlg = None                 # 弹窗单例守卫
        self._rebuild()

    def open(self):
        self._rebuild()
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, ev):
        self._write_state()
        super().closeEvent(ev)

    # 内容重建
    def _rebuild(self):
        if self._body is not None:
            self._outer.removeWidget(self._body)
            self._body.setParent(None)
            self._body.deleteLater()
        self._body = QWidget()
        v = QVBoxLayout(self._body)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        self._section_cats(v)
        v.addWidget(self._divider())
        self._section_env(v)
        v.addWidget(self._divider())
        self._section_hud(v)
        self._outer.addWidget(self._body)
        self.adjustSize()

    @staticmethod
    def _header(text):
        l = QLabel(text)
        l.setObjectName("secHeader")
        return l

    @staticmethod
    def _divider():
        f = QFrame()
        f.setFixedHeight(1)
        f.setStyleSheet("background:rgba(120,150,100,90);border:none;")
        return f

    def _section_cats(self, v):
        v.addWidget(self._header(t("settings_cats_section")))
        pets = list(self._window.pets)
        can_remove = len(pets) > 1
        for pet in pets:
            row = QHBoxLayout()
            row.setSpacing(8)
            name = QLabel(pet_label(pet, pets))
            row.addWidget(name)
            row.addStretch(1)
            rm = QPushButton(t("settings_remove"))
            rm.setEnabled(can_remove)
            if not can_remove:
                rm.setToolTip(t("settings_min_pets"))
            rm.clicked.connect(lambda _c, p=pet: self._on_remove(p))
            row.addWidget(rm)
            v.addLayout(row)
        add = QPushButton(t("settings_add"))
        full = len(pets) >= MAX_PETS
        add.setEnabled(not full)
        if full:
            add.setToolTip(t("settings_max_pets"))
        add.clicked.connect(self._on_add)
        v.addWidget(add)

    def _section_env(self, v):
        v.addWidget(self._header(t("settings_env_section")))
        grp = QButtonGroup(self._body)
        self._env_group = grp
        self._env_radios = {}
        current = self._current_env()
        for key, label_key in (("none", "settings_env_none"), ("blizzard", "settings_snow"),
                               ("zerog", "settings_zerog"), ("water", "settings_water")):
            rb = QRadioButton(t(label_key))
            rb.setChecked(key == current)
            rb.toggled.connect(lambda checked, k=key: checked and self._on_env_selected(k))
            grp.addButton(rb)
            v.addWidget(rb)
            self._env_radios[key] = rb

    def _current_env(self):
        """从 window 环境态推导当前单选项。"""
        w = self._window
        if getattr(w, "blizzard_on", False):
            return "blizzard"
        if getattr(w, "zerog_on", False):
            return "zerog"
        if getattr(w, "water_on", False):
            return "water"
        return "none"

    def _on_env_selected(self, key):
        """选中 key 对应环境，互斥关其余（none=全关）。"""
        w = self._window
        if key != "blizzard" and getattr(w, "blizzard_on", False):
            w.blizzard_on = False
            w.blizzard_timer = 0
        if key != "zerog" and getattr(w, "zerog_on", False):
            w.set_zerog(False)
        if key != "water" and getattr(w, "water_on", False):
            w.set_water(False)
        if key == "blizzard" and not w.blizzard_on:
            w.blizzard_on = True
            w.blizzard_timer = 0
        elif key == "zerog" and not w.zerog_on:
            w.set_zerog(True)
        elif key == "water" and not w.water_on:
            w.set_water(True)

    def _section_hud(self, v):
        chk = QCheckBox(t("settings_show_hud"))
        chk.setChecked(self._hud.isVisible())
        chk.toggled.connect(self._on_hud_toggled)
        v.addWidget(chk)

    # 增删走卡片弹窗（open()=WindowModal，不 exec）
    def _on_add(self):
        if self._dlg is not None:
            return
        labels = []
        for variant in _VARIANTS:
            lbl = variant_label(variant)
            if REGISTRY[variant].wip:
                lbl += t("variant_wip_note")     # 占位种族挂提示
            labels.append(lbl)
        dlg = PickDialog(t("settings_pick_title"), t("settings_pick_cat"), labels,
                         t("settings_ok"), t("settings_cancel"), parent=self)
        dlg.finished.connect(lambda r, d=dlg: self._add_finished(d, r))
        self._dlg = dlg
        dlg.place_center(self)
        dlg.open()

    def _add_finished(self, dlg, result):
        self._dlg = None
        dlg.deleteLater()
        if result == QDialog.DialogCode.Accepted:
            self._window.add_pet(_VARIANTS[dlg.selected_index()])   # 内部刷 HUD+写盘
            self._rebuild()

    def _on_remove(self, pet):
        if self._dlg is not None:
            return
        name = pet_label(pet, list(self._window.pets))
        dlg = ConfirmDialog(t("settings_remove"), t("settings_remove_confirm", name=name),
                            t("settings_remove"), t("settings_cancel"), parent=self)
        dlg.finished.connect(lambda r, p=pet, d=dlg: self._remove_finished(p, d, r))
        self._dlg = dlg
        dlg.place_center(self)
        dlg.open()

    def _remove_finished(self, pet, dlg, result):
        self._dlg = None
        dlg.deleteLater()
        if result == QDialog.DialogCode.Accepted and self._window.remove_pet(pet):
            self._rebuild()

    def _on_hud_toggled(self, checked):
        if checked != self._hud.isVisible():
            self._hud.toggle_visible()

    def refresh_env(self):
        """同步单选钮到真实环境态（未开窗跳过）。"""
        if not self.isVisible():
            return
        radios = getattr(self, "_env_radios", None)
        if not radios:
            return
        rb = radios.get(self._current_env())
        if rb is not None and not rb.isChecked():
            rb.setChecked(True)   # 互斥自动清其余，幂等
