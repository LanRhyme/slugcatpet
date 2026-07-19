"""Monk（黄猫）种族定义：白猫的黄色版，HeadA 脸型、无舌无超度、无独占可视机制。"""
from __future__ import annotations

from dataclasses import replace

from .base import CatCaps, CatDef
from .personality import DEFAULT_PERSONALITY
from .stats import DEFAULT_STATS

MONK_DEF = CatDef(
    key="monk",
    body_color=(255, 255, 115),   # Yellow
    eye_color=(22, 30, 16),       # 脸暗色，非种族相关
    frames={
        "head": ("base", "HeadA"),        # 仅 Saint→HeadB，其余→HeadA
        "face": ("base", "FaceA"),
        "face_blink": ("base", "FaceB"),
        "legs_walk": ("base", "LegsA"),
        "legs_crawl": ("base", "LegsACrawling"),
        "legs_air": ("base", "LegsAAir0"),
    },
    layout_file="monk.json",
    atlas_keys=("base",),
    caps=CatCaps(tongue=False, ascension=False),   # 舌/超度 Saint 独占
    stats=replace(DEFAULT_STATS, weight_fac=0.95, max_food=5, food_hibernate=3,
                  lungs_fac=1.2),
    # 温和体弱最亲人：偏懒易累爱黏人
    personality=replace(DEFAULT_PERSONALITY, activity=0.4, stamina=0.8, sociability=0.9),
    tuning={},
    fsm_mount=None,
    wip=False,
)
