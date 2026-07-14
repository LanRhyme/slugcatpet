"""界面文案中英两套 + 运行期取串。语言由 env / exe 名定，两个打包 exe 各自定死。"""
from __future__ import annotations
import os
import sys
from pathlib import Path


def _detect_lang() -> str:
    env = os.environ.get("SLUGCATPET_LANG", "").strip().lower()
    if env in ("zh", "en"):
        return env
    if getattr(sys, "frozen", False) and Path(sys.executable).stem.lower().endswith("-en"):
        return "en"
    return "zh"


LANG = _detect_lang()

_STR = {
    # —— 通用 / 产品名 ——
    "app_title":      {"zh": "蛞蝓猫桌宠", "en": "Slugcat Pet"},

    # —— setup_panel：首次导入面板 ——
    "setup_importing":   {"zh": "正在导入素材…", "en": "Importing assets…"},
    "setup_hint_init":   {"zh": "首次启动需从你的游戏读取画面，请稍候",
                          "en": "First launch needs to read the picture from your game, please wait"},
    "setup_hint_busy":   {"zh": "首次启动需从你的游戏读取素材，请稍候。未来不再需要读取",
                          "en": "First launch needs to read assets from your game, please wait. Won't be needed again in the future"},
    "setup_hint_error":  {"zh": "点【选择 RainWorld 文件夹】手动指定：选中的文件夹里应能看到 RainWorld.exe 和 RainWorld_Data 文件夹",
                          "en": "Click [Select RainWorld folder] to specify manually: the chosen folder should contain RainWorld.exe and the RainWorld_Data folder"},
    "setup_quit":        {"zh": "退出", "en": "Quit"},
    "setup_pick":        {"zh": "选择 RainWorld 文件夹", "en": "Select RainWorld folder"},
    "setup_unexpected":  {"zh": "导入时发生意外错误：{e}", "en": "Unexpected error during import: {e}"},

    # —— tabbar：图标盘 tooltip ——
    "tip_vpole":   {"zh": "放竖杆", "en": "Place vertical pole"},
    "tip_hpole":   {"zh": "放横杆", "en": "Place horizontal pole"},
    "tip_fruit":   {"zh": "放果子", "en": "Place fruit"},
    "tip_stone":   {"zh": "放石头", "en": "Place stone"},
    "tip_lamp":    {"zh": "放灯笼", "en": "Place lantern"},
    "tip_slimemold": {"zh": "放黏菌", "en": "Place slime mold"},
    "tip_batfly":  {"zh": "放蝙蝠", "en": "Place batfly"},
    "tip_clear":   {"zh": "清除可交互实体", "en": "Clear placed items"},


    # —— tabbar：toast ——
    "toast_max_fruit":  {"zh": "场上最多 3 个果子", "en": "At most 3 fruits on the field"},
    "toast_max_stone":  {"zh": "场上最多 3 个石头", "en": "At most 3 stones on the field"},
    "toast_max_slimemold": {"zh": "场上最多 3 个黏菌", "en": "At most 3 slime molds on the field"},
    "toast_max_batfly": {"zh": "场上最多 3 只蝙蝠", "en": "At most 3 batflies on the field"},
    "toast_max_vpole":  {"zh": "场上最多 2 根竖杆", "en": "At most 2 vertical poles on the field"},
    "toast_max_hpole":  {"zh": "场上最多 2 根横杆", "en": "At most 2 horizontal poles on the field"},
    "toast_no_object":  {"zh": "场上没有物体", "en": "No objects on the field"},

    # —— tabbar：动作按钮 ——
    "btn_quit_app":  {"zh": "退出程序", "en": "Quit program"},

    # —— 杀死确认弹窗（猫菜单「杀死该猫」复用）——
    "dlg_confirm_title":  {"zh": "确认", "en": "Confirm"},
    "dlg_kill_text":      {"zh": "确定要杀死 {name} 吗？", "en": "Are you sure you want to kill {name}?"},
    "dlg_kill_yes":       {"zh": "杀死", "en": "Kill"},
    "dlg_kill_no":        {"zh": "取消", "en": "Cancel"},

    # —— hud：状态面板字段名 ——
    "hud_karma":    {"zh": "业力", "en": "Karma"},
    "hud_stamina":  {"zh": "体力", "en": "Stamina"},
    "hud_satiety":  {"zh": "饱食", "en": "Satiety"},
    "hud_affection":{"zh": "好感", "en": "Affection"},
    "hud_cold":     {"zh": "寒冷", "en": "Cold"},
    "hud_op_hint":  {"zh": "右键蛞蝓猫或点击此行可操作",
                     "en": "Right-click the slugcat or click this row to operate"},

    # —— 皮名（variant 显示名） ——
    "variant_saint":    {"zh": "圣徒", "en": "Saint"},
    "variant_rivulet":  {"zh": "溪流", "en": "Rivulet"},
    "variant_survivor": {"zh": "白猫", "en": "Survivor"},
    "variant_monk":     {"zh": "黄猫", "en": "Monk"},
    "variant_artificer": {"zh": "工匠", "en": "Artificer"},
    "variant_wip_note": {"zh": "（外观差异待后续）", "en": "(appearance differences TBD)"},

    # —— 猫菜单 ——
    "menu_kill_pet":       {"zh": "杀掉该猫", "en": "Kill this cat"},
    "menu_reset_pet":      {"zh": "重置该猫", "en": "Reset this cat"},
    "menu_reincarnating":  {"zh": "转世中…", "en": "Reincarnating…"},
    "menu_open_settings":  {"zh": "打开设置", "en": "Open settings"},
    "menu_control_pet":    {"zh": "控制该猫", "en": "Control this cat"},
    "menu_exit_control":   {"zh": "退出控制", "en": "Exit control"},

    # —— 控制 HUD ——
    "ctrlhud_title":        {"zh": "控制中：{name}", "en": "Controlling: {name}"},
    "ctrlhud_paused":       {"zh": "已暂停 · 点击继续", "en": "Paused · click to resume"},
    "ctrlhud_exit":         {"zh": "退出控制 (Esc)", "en": "Exit control (Esc)"},
    "ctrlhud_keys":         {"zh": "{move} 移动，{jump} 跳跃",
                             "en": "{move} to move, {jump} to jump"},

    # —— 设置窗 ——
    "settings_title":        {"zh": "设置", "en": "Settings"},
    "settings_cats_section": {"zh": "蛞蝓猫", "en": "Slugcats"},
    "settings_add":          {"zh": "添加", "en": "Add"},
    "settings_remove":       {"zh": "移除", "en": "Remove"},
    "settings_max_pets":     {"zh": "最多 3 只", "en": "At most 3 cats"},
    "settings_min_pets":     {"zh": "至少保留 1 只", "en": "Keep at least 1 cat"},
    "settings_remove_confirm": {"zh": "确定移除 {name}？", "en": "Remove {name}?"},
    "settings_env_section":  {"zh": "环境", "en": "Environment"},
    "settings_env_none":     {"zh": "无", "en": "None"},
    "settings_snow":         {"zh": "暴风雪", "en": "Blizzard"},
    "settings_zerog":        {"zh": "无重力", "en": "Zero gravity"},
    "settings_water":        {"zh": "涨水", "en": "Flood"},
    "settings_show_hud":     {"zh": "显示状态面板", "en": "Show status panel"},
    "settings_pick_title":   {"zh": "选择皮", "en": "Pick a variant"},
    "settings_pick_cat":     {"zh": "选择要添加的蛞蝓猫", "en": "Choose a slugcat to add"},
    "settings_ok":           {"zh": "确定", "en": "OK"},
    "settings_cancel":       {"zh": "取消", "en": "Cancel"},

    # —— tabbar：打开设置 ——
    "btn_open_settings": {"zh": "打开设置", "en": "Open settings"},

    # —— main：单实例 ——
    "already_running": {"zh": "蛞蝓猫桌宠已在运行", "en": "Slugcat Pet is already running"},

    # —— main：托盘菜单 / 通知 ——
    "tray_settings": {"zh": "设置", "en": "Settings"},
    "tray_hud":     {"zh": "显示/隐藏状态面板 (Ctrl+Alt+H)", "en": "Show/Hide status panel (Ctrl+Alt+H)"},
    "tray_quit":    {"zh": "退出程序", "en": "Quit program"},
    "tray_abort":   {"zh": "中止光标劫持 (Ctrl+Alt+Q)", "en": "Abort cursor hijack (Ctrl+Alt+Q)"},
    "tray_started": {"zh": "已启动。被超度的光标按 Ctrl+Alt+Q 解除；Ctrl+Alt+X 退出程序。",
                     "en": "Launched. Press Ctrl+Alt+Q to release a salvaged cursor; Ctrl+Alt+X to quit the program."},

    # —— gameassets：导入报错（显示在 setup 面板） ——
    "err_atlas_missing":  {"zh": "未找到游戏图集文件：{res}\n请选择 RainWorld 文件夹（其中应有 RainWorld.exe 和 RainWorld_Data 文件夹）。",
                           "en": "Game atlas file not found: {res}\nPlease select the RainWorld folder (which should contain RainWorld.exe and the RainWorld_Data folder)."},
    "err_no_unitypy":     {"zh": "缺少依赖 UnityPy，请先运行：pip install UnityPy",
                           "en": "Missing dependency UnityPy, please run first: pip install UnityPy"},
    "err_base_fail":      {"zh": "基础图集 rainWorld 提取失败，游戏文件可能损坏或版本不兼容。",
                           "en": "Base atlas rainWorld extraction failed; game files may be corrupted or the version incompatible."},
    "err_msc_missing":    {"zh": "未找到 rainworldmsc 图集——Saint 属于 Downpour(More Slugcats) DLC，需要在 Steam 拥有该 DLC 才能导入。",
                           "en": "rainworldmsc atlas not found — Saint belongs to the Downpour (More Slugcats) DLC; you need to own that DLC on Steam to import."},
    "err_ui_fail":        {"zh": "UI 图集 uiSprites 提取失败，游戏文件可能损坏或版本不兼容。",
                           "en": "UI atlas uiSprites extraction failed; game files may be corrupted or the version incompatible."},
    "err_uimsc_missing":  {"zh": "未找到 uispritesmsc 图集——业力图标需 Downpour(More Slugcats) DLC。",
                           "en": "uispritesmsc atlas not found — the karma icons need the Downpour (More Slugcats) DLC."},
    "err_no_install":     {"zh": "未能自动定位 Rain World 安装。\n请点下方按钮，手动选择你的 RainWorld 文件夹。",
                           "en": "Could not automatically locate the Rain World installation.\nPlease click the button below to manually select your RainWorld folder."},
}


def t(key: str, **kw) -> str:
    e = _STR.get(key)
    if e is None:
        return key
    s = e.get(LANG) or e.get("zh") or key
    return s.format(**kw) if kw else s
