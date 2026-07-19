"""启动应用，管理 PetWindow、TabBar、托盘、全局热键。"""
from __future__ import annotations
import sys
import os
import json
import signal
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QPixmap, QAction, QColor, QPainter
from PySide6.QtCore import QTimer

if sys.platform.startswith("linux"):
    os.environ["QT_QPA_PLATFORM"] = "xcb"

from .cats import default_def
from .window import PetWindow
from .ui.tabbar import TabBar
from .ui.hud import HudPanel
from .ui.settings import SettingsWindow
from .control.hotkey import HotkeyFilter, MOD_CONTROL, MOD_ALT, HK_PLACE_ESC
from .platform import cursorfx
from ._paths import user_dir
from .i18n import t

VK_Q = 0x51
VK_X = 0x58
VK_H = 0x48
HK_ABORT = 1
HK_QUIT = 2
HK_HUD = 3
_APP_PARAMS = user_dir() / "app.json"
SCHEMA_VERSION = 2   # pets[] 分猫存档
AUTOSAVE_MS = 60_000


def _tray_icon() -> QIcon:
    pm = QPixmap(32, 32)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setBrush(QColor(*default_def().body_color))
    p.setPen(QColor(40, 80, 20))
    p.drawEllipse(4, 4, 24, 24)
    p.end()
    return QIcon(pm)


def _migrate_params(params: dict) -> dict:
    """旧 schema 迁移为 v2 pets[] 格式。"""
    if params.get("schema_version") == SCHEMA_VERSION and isinstance(params.get("pets"), list):
        return params
    from .behavior import tuning
    old_keys = ("energy", "temper", "food", "karma", "cold", "dead")
    if any(k in params for k in old_keys) or not params.get("pets"):
        pet_state = {
            "id": "pet-0",
            "variant": "saint",
            "energy": params.pop("energy", 1.0),
            "temper": params.pop("temper", 0.0),
            "food": params.pop("food", tuning.FOOD_INIT),
            "karma": params.pop("karma", tuning.KARMA_INIT),
            "cold": params.pop("cold", 0.0),
            "dead": params.pop("dead", False),
        }
        params["pets"] = [pet_state]
    params["schema_version"] = SCHEMA_VERSION
    return params


def _load_params(path: Path | None = None) -> dict:
    p = path or _APP_PARAMS
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    return _migrate_params(raw)


def _save_params(params: dict, path: Path | None = None):
    """原子写盘，失败重试。"""
    p = path or _APP_PARAMS
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(params, ensure_ascii=False, indent=2), encoding="utf-8")
        for attempt in range(5):
            try:
                os.replace(tmp, p)
                break
            except OSError:
                if attempt == 4:
                    raise
                time.sleep(0.01)
    except Exception as e:
        print("[slugcatpet] save failed:", ascii(e), file=sys.stderr)


def setup_signal_handling(app):
    def _h(sig, frame):
        app.quit()
    signal.signal(signal.SIGINT, _h)
    t = QTimer()
    t.timeout.connect(lambda: None)
    t.start(500)   # 唤醒让 CPython 跑 SIGINT handler
    return t


def _ensure_assets_interactive() -> bool:
    """确保图集就绪，引导用户导入，返回是否成功。"""
    from .gameassets import atlases_present
    from ._paths import assets_dir
    if atlases_present(assets_dir()):
        return True
    from .ui.setup_panel import SetupPanel
    return SetupPanel().run()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    from .platform.singleton import SingleInstance
    si = SingleInstance()
    if not si.acquire():
        si.notify_primary()
        return
    app._singleton = si                            # 保持引用

    _sig = setup_signal_handling(app)            # noqa: 保持引用

    params = _load_params()

    if not _ensure_assets_interactive():
        return

    pet = PetWindow(params=params)
    pet.show()

    hud = HudPanel(pet, params)
    if params.get("hud_visible"):
        hud.toggle_visible()

    tab = TabBar(pet, app, params)
    tab.show()

    def _write_state():
        """序列化状态并写盘。"""
        params["tab_y"] = tab._y
        params["tab_expanded"] = tab.expanded
        params["hud_x"] = hud.x()
        params["hud_y"] = hud.y()
        params["pets"] = [
            {"id": p.id, "variant": p.variant,
             "energy": p.body.energy, "temper": p.body.temper,
             "food": p.body.food, "karma": p.body.karma, "cold": p.body.cold,
             "dead": p.behavior is not None and p.behavior.is_truly_dead()}
            for p in pet.pets
        ]
        params["schema_version"] = SCHEMA_VERSION
        _save_params(params)

    settings = SettingsWindow(pet, hud, _write_state)
    pet._hud = hud                       # 供增删猫后 rebuild_rows
    pet._pets_changed_cb = _write_state  # 增删猫后写盘
    pet._open_settings_cb = settings.open  # 设置入口共用
    app._settings = settings             # 保持引用

    if params.get("tab_expanded", True):
        tab.toggle()

    tray = QSystemTrayIcon(_tray_icon())
    tray.setToolTip(t("app_title"))
    menu = QMenu()
    act_settings = QAction(t("tray_settings"))
    act_settings.triggered.connect(settings.open)
    act_hud = QAction(t("tray_hud"))
    act_hud.triggered.connect(hud.toggle_visible)
    act_quit = QAction(t("tray_quit"))
    act_quit.triggered.connect(app.quit)
    act_abort = QAction(t("tray_abort"))
    act_abort.triggered.connect(cursorfx.abort_all)
    menu.addAction(act_settings)
    menu.addAction(act_hud)
    menu.addAction(act_abort)
    menu.addSeparator()
    menu.addAction(act_quit)
    tray.setContextMenu(menu)
    tray.show()
    tray.showMessage(t("app_title"), t("tray_started"),
                     QSystemTrayIcon.MessageIcon.Information, 4000)

    si.on_secondary_attempt = lambda: tray.showMessage(     # 后启实例触发提示
        t("app_title"), t("already_running"),
        QSystemTrayIcon.MessageIcon.Information, 4000)

    hotkey = HotkeyFilter()
    app.installNativeEventFilter(hotkey)
    hotkey.register(HK_ABORT, MOD_CONTROL | MOD_ALT, VK_Q)
    hotkey.register(HK_QUIT, MOD_CONTROL | MOD_ALT, VK_X)
    hotkey.register(HK_HUD, MOD_CONTROL | MOD_ALT, VK_H)
    pet._hotkey_filter = hotkey          # 放置模式临时挂/摘 Esc

    def _on_hotkey(hk_id):
        if hk_id == HK_QUIT:
            app.quit()
        elif hk_id == HK_HUD:
            hud.toggle_visible()
        elif hk_id == HK_PLACE_ESC:
            pet._exit_place_mode()
        else:
            cursorfx.abort_all()
    hotkey.triggered.connect(_on_hotkey)
    app._hotkey = hotkey                          # 保持引用

    autosave = QTimer()
    autosave.timeout.connect(_write_state)
    autosave.start(AUTOSAVE_MS)
    app._autosave = autosave                      # 保持引用

    from .platform.envwatch import EnvironmentWatcher
    envwatch = EnvironmentWatcher([pet, tab, hud, settings], pet)
    envwatch.start()
    app._envwatch = envwatch                       # 保持引用

    def _cleanup():
        app.removeNativeEventFilter(hotkey)   # 关停期需先摘 filter，防虚方法 dispatch 崩溃
        cursorfx.abort_all()
        try:
            from .control.mouse import set_passthrough
            if pet._hwnd:
                set_passthrough(pet._hwnd, False)
        except Exception:
            pass
        envwatch.stop()
        autosave.stop()
        _write_state()
        hotkey.unregister_all()
    app.aboutToQuit.connect(_cleanup)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
