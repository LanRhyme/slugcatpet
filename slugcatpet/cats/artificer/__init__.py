"""Artificer（工匠）种族定义：暗红体色、疤脸族 FaceC/FaceD + 面罩疤精灵、脸不染暗色。"""
from __future__ import annotations

from dataclasses import replace

from ..base import CatCaps, CatDef
from ..personality import DEFAULT_PERSONALITY, DIET_CARNIVORE
from ..stats import DEFAULT_STATS


def _fsm_mount(fsm):
    """按 caps 注册工匠独占状态（燃料 ticker + 爆跳撒欢）。"""
    from .states import mount
    mount(fsm)


ARTIFICER_DEF = CatDef(
    key="artificer",
    body_color=(112, 35, 60),     # Artificer
    eye_color=(255, 255, 255),    # 强制白=正片叠底原图
    frames={
        "head": ("base", "HeadA"),           # 仅 Saint→HeadB，其余→HeadA
        "face": ("msc", "FaceC"),            # 疤脸非眨眼族
        "face_mirror": ("msc", "FaceD"),     # 镜像朝向→FaceD；疤不随翻转换边
        "face_open": ("msc", "FaceC"),       # 睁眼槽仅超度用，工匠无超度占位同 FaceC
        "face_scar": ("base", "MushroomA"),  # 面罩疤复用蘑菇贴图元素
        "legs_walk": ("base", "LegsA"),
        "legs_crawl": ("base", "LegsACrawling"),
        "legs_air": ("base", "LegsAAir0"),
    },
    layout_file="artificer.json",
    atlas_keys=("base", "msc"),
    caps=CatCaps(tongue=False, ascension=False, pyro=True),   # 舌/超度关；招牌爆跳独占
    stats=replace(DEFAULT_STATS,
                  runspeed_fac=1.2, pole_fac=1.25, weight_fac=1.12,   # 快而重
                  max_food=9, food_hibernate=6,
                  swim_boost_force=6.0, swim_boost_cost=0.015,        # 强冲刺低耗
                  is_artificer=True,
                  drown_threshold=0.5,                                # 憋气极短，挣扎门提前留逃生时间
                  karma_cap=0),                                       # 业力锁 1 级（无 Echo 可升）
    # 复仇爆破手：好动强健、极不亲人
    personality=replace(DEFAULT_PERSONALITY, activity=0.75, stamina=1.1,
                        sociability=0.2, diet=DIET_CARNIVORE,
                        toy_pref={"pyro_romp": 1.4}),
    tuning={"pyro_heat_cap": 5},   # = pyro.WARN_AT，AI 永不至眩晕/自爆
    fsm_mount=_fsm_mount,
    wip=False,
)
