from __future__ import annotations
from dataclasses import replace
from .base import CatCaps, CatDef
from .personality import DEFAULT_PERSONALITY, DIET_CARNIVORE
from .stats import DEFAULT_STATS

HUNTER_DEF = CatDef(
    key="hunter",
    body_color=(255, 115, 115),   # Red #FF7373
    eye_color=(22, 30, 16),
    frames={
        "head": ("base", "HeadA"),
        "face": ("base", "FaceA"),
        "face_blink": ("base", "FaceB"),
        "legs_walk": ("base", "LegsA"),
        "legs_crawl": ("base", "LegsACrawling"),
        "legs_air": ("base", "LegsAAir0"),
    },
    layout_file="hunter.json",
    atlas_keys=("base",),
    caps=CatCaps(tongue=False, ascension=False),
    stats=replace(DEFAULT_STATS, runspeed_fac=1.2, pole_fac=1.25, weight_fac=1.12,
                  max_food=9, food_hibernate=6),
    personality=replace(DEFAULT_PERSONALITY, activity=0.65, stamina=1.05,
                        sociability=0.3, diet=DIET_CARNIVORE),
    tuning={},
    fsm_mount=None,
    wip=False,
)
