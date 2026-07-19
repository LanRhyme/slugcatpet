"""Saint 种族定义与独占机制归属包。"""
from __future__ import annotations

from dataclasses import replace

from ..base import CatCaps, CatDef
from ..personality import DEFAULT_PERSONALITY, DIET_VEGETARIAN

SAINT_COLOR = (170, 241, 86)     # #AAF156
SAINT_EYE = (22, 30, 16)         # 眼 / 脸暗色


def _fsm_mount(fsm):
    """按 caps 注册 Saint 独占状态（超度/舌头系）。"""
    from .states import mount
    mount(fsm)


SAINT_DEF = CatDef(
    key="saint",
    body_color=SAINT_COLOR,
    eye_color=SAINT_EYE,
    frames={
        "head": ("msc", "HeadB"),
        "face": ("base", "FaceB"),        # 闭眼
        "face_blink": ("base", "FaceB"),
        "face_open": ("base", "FaceA"),   # 超度睁眼
        "legs_walk": ("base", "LegsA"),
        "legs_crawl": ("base", "LegsACrawling"),
        "legs_air": ("base", "LegsAAir0"),
    },
    layout_file="saint.json",
    atlas_keys=("base", "msc", "ui", "uimsc"),
    caps=CatCaps(tongue=True, ascension=True),
    # 慈悲孱弱纯素：偏静易累最耐寒，爱舌钩荡跃
    personality=replace(DEFAULT_PERSONALITY, activity=0.4, stamina=0.8, cold_gain_fac=0.5,
                        sociability=0.3, diet=DIET_VEGETARIAN,
                        toy_pref={"ceiling_play": 1.4}),
    tuning={
        "temper_ascend_gate": -0.20,          # ≤此值才可超度
        "temper_kill_cancel_saint": -0.20,    # 舌头取消杀死弹窗的好感扣减
    },
    fsm_mount=_fsm_mount,
    wip=False,
)
