"""共享猫菜单构造器（右键猫身/左键 HUD 行共用）。"""
from __future__ import annotations
from PySide6.QtWidgets import QMenu

from ..cats import REGISTRY
from ..i18n import t

_MENU_QSS = (
    "QMenu{background:rgba(30,34,40,245);border:1px solid #4a5a3a;border-radius:6px;"
    "color:#e8f5d8;font-size:12px;padding:4px;}"
    "QMenu::item{padding:5px 18px;border-radius:4px;}"
    "QMenu::item:selected{background:rgba(80,100,70,255);}"
    "QMenu::item:disabled{color:#8a9a7a;}"
    "QMenu::separator{height:1px;background:rgba(120,150,100,90);margin:4px 6px;}")


def variant_label(variant: str) -> str:
    """皮肤显示名。"""
    return t(f"variant_{variant}") if variant in REGISTRY else variant


def pet_label(pet, pets) -> str:
    """猫的显示名，同皮加序号。"""
    base = variant_label(pet.variant)
    same = [p for p in pets if p.variant == pet.variant]
    if len(same) > 1:
        return f"{base} #{same.index(pet) + 1}"
    return base


def build_cat_menu(pet, pets=None, open_settings=None, parent=None) -> QMenu:
    """按猫状态构建右键菜单。"""
    pets = pets if pets is not None else list(getattr(pet.window, "pets", [pet]))
    label = pet_label(pet, pets)
    menu = QMenu(parent)
    menu.setTitle(label)
    menu.setStyleSheet(_MENU_QSS)
    header = menu.addAction(label)
    header.setEnabled(False)
    menu.addSeparator()

    beh = pet.behavior
    reinc = beh is not None and beh.is_reincarnating()
    dead = beh is not None and beh.is_truly_dead()
    blocked = beh is not None and beh.blocks_interaction()   # 独占特效期禁杀
    if getattr(pet, "controlled", False):
        # 受控猫仅退出控制；闭包现查防重入
        exit_act = menu.addAction(t("menu_exit_control"))
        exit_act.triggered.connect(
            lambda: pet.window.stop_control() if getattr(pet, "controlled", False) else None)
    elif reinc:
        menu.addAction(t("menu_reincarnating")).setEnabled(False)
    elif dead:
        menu.addAction(t("menu_reset_pet")).triggered.connect(lambda: pet.respawn())
    else:
        act = menu.addAction(t("menu_kill_pet"))
        # 飞升/挂确认期置灰
        act.setEnabled(not blocked and pet._kill_dialog is None)
        act.triggered.connect(lambda: pet.window.request_kill(pet))
        ctl = menu.addAction(t("menu_control_pet"))
        # 同上门禁，控他猫即切换
        ctl.setEnabled(not blocked and pet._kill_dialog is None)
        ctl.triggered.connect(lambda: pet.window.start_control(pet))

    s = menu.addAction(t("menu_open_settings"))
    if open_settings is not None:
        s.triggered.connect(lambda: open_settings())
    return menu
