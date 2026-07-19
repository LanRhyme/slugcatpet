"""猫种族注册表：variant key → CatDef；未知 variant 回落 saint。"""
from __future__ import annotations

from .artificer import ARTIFICER_DEF
from .base import CatDef
from .hunter import HUNTER_DEF
from .monk import MONK_DEF
from .rivulet import RIVULET_DEF
from .saint import SAINT_DEF
from .survivor import SURVIVOR_DEF

DEFAULT_VARIANT = "saint"

# 六个种族
REGISTRY: dict[str, CatDef] = {
    "saint": SAINT_DEF,
    "rivulet": RIVULET_DEF,
    "survivor": SURVIVOR_DEF,
    "monk": MONK_DEF,
    "hunter": HUNTER_DEF,
    "artificer": ARTIFICER_DEF,
}


def get(variant) -> CatDef:
    """按 variant 取定义；未知回落 saint。"""
    d = REGISTRY.get(variant)
    return d if d is not None else REGISTRY[DEFAULT_VARIANT]


def default_def() -> CatDef:
    return REGISTRY[DEFAULT_VARIANT]
