"""Rivulet（溪流）种族定义与独占器官（鳃）归属包。"""
from __future__ import annotations

from dataclasses import replace

from ..base import CatCaps, CatDef
from ..personality import DEFAULT_PERSONALITY
from ..stats import DEFAULT_STATS


def _fsm_mount(fsm):
    """按 caps 注册溪流独占状态（高后空翻撒欢）。"""
    from .states import mount
    mount(fsm)

# 溪流数值：快而轻 + 全套动作专属高冲量
RIVULET_STATS = replace(
    DEFAULT_STATS,
    runspeed_fac=1.75, pole_fac=1.8, weight_fac=0.95,
    max_food=6, food_hibernate=5,
    jump_head=-6.0, jump_feet=-5.0,
    flip_head=-12.0, flip_feet=-10.0, flip_boost=9.0,
    roll_rocket_vx_mult=1.5,
    backflip_vx=11.0, backflip_c0_vy=-12.0, backflip_c1_vy=-13.0,
    belly_rocket_vx=18.0, belly_rocket_vy=10.0,
    pounce_super=12.0,
    belly_slide_spd=25.0, belly_no_kick=True,
    belly_jump_cancel_window=6, skid_init_thresh=5,
    pole_jump_head_vx=9.0, pole_jump_head_vy=-9.0,
    pole_jump_feet_vx=7.0, pole_jump_feet_vy=-8.0,
    buoyancy=0.9,
    lungs_fac=0.075,
    bubble_fac=0.25,
    swim_boost_cost=0.025, swim_boost_cd=10, swim_surface_speed=5.0,
    is_rivulet=True,
)

RIVULET_DEF = CatDef(
    key="rivulet",
    body_color=(145, 204, 240),   # Rivulet
    eye_color=(22, 30, 16),       # 脸暗色，非种族相关
    frames={
        "head": ("base", "HeadA"),        # 仅 Saint→HeadB，其余→HeadA
        "face": ("base", "FaceA"),
        "face_blink": ("base", "FaceB"),
        "legs_walk": ("base", "LegsA"),
        "legs_crawl": ("base", "LegsACrawling"),
        "legs_air": ("base", "LegsAAir0"),
    },
    layout_file="rivulet.json",
    atlas_keys=("base",),
    caps=CatCaps(tongue=False, ascension=False, gills=True, acrobat=True),   # 舌/超度关；鳃+高后空翻独占
    stats=RIVULET_STATS,
    # 极敏捷好奇水生：最好动、爱潜深冲刺
    personality=replace(DEFAULT_PERSONALITY, activity=0.95, sociability=0.45, swim_zeal=1.0,
                        toy_pref={"pole_climb": 1.2, "hpole": 1.2, "riv_flip": 1.4}),
    tuning={},
    fsm_mount=_fsm_mount,
    wip=False,
)
