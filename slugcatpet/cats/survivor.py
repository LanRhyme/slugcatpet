"""Survivor（白猫）种族定义：纯白体色、HeadA 脸型、无舌无超度，走跳/竖杆/捡落地果。"""
from __future__ import annotations

from dataclasses import replace

from .base import CatCaps, CatDef
from .personality import DEFAULT_PERSONALITY
from .stats import DEFAULT_STATS

SURVIVOR_DEF = CatDef(
    key="survivor",
    body_color=(255, 255, 255),   # White
    eye_color=(22, 30, 16),       # 脸暗色，非种族相关
    frames={
        "head": ("base", "HeadA"),        # 非 Saint 用 HeadA
        "face": ("base", "FaceB"),        # 脸族无种族门控
        "face_open": ("base", "FaceA"),
        "legs_walk": ("base", "LegsA"),
        "legs_crawl": ("base", "LegsACrawling"),
        "legs_air": ("base", "LegsAAir0"),
    },
    layout_file="survivor.json",
    atlas_keys=("base",),
    caps=CatCaps(tongue=False, ascension=False),   # 舌/超度 Saint 独占
    stats=replace(DEFAULT_STATS, max_food=7, food_hibernate=4),
    personality=DEFAULT_PERSONALITY,   # 中性基准
    tuning={},
    # 预留位：暂无独占机制，未来专属行动挂 fsm_mount
    fsm_mount=None,
    wip=False,
)
