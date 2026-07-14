"""SlugStats：每种族的移动因子/体重/饱食/动作冲量数值。DEFAULT_STATS=现值基线，各猫 replace 只写差异。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SlugStats:
    """一种族的静态数值：移动因子 + 动作冲量；y↓。"""
    # 移动因子
    runspeed_fac: float = 1.0        # 不乘加速度
    pole_fac: float = 1.0
    weight_fac: float = 1.0          # 不进跳跃公式
    # 隧道爬速因子留白：无对应玩法，趴行恒 2.5 不分种族

    # 饱食：上限/冬眠阈（整数格）
    max_food: int = 5
    food_hibernate: int = 4

    # 站立跳
    jump_head: float = -4.0
    jump_feet: float = -3.0
    jump_boost: float = 8.0

    # 急刹翻跳 Flip
    flip_head: float = -9.0
    flip_feet: float = -7.0
    flip_boost: float = 5.0

    # 翻滚火箭 Roll→Rocket
    roll_rocket_vx_mult: float = 1.0

    # 后空翻 Belly→Flip；backflip_vx 用作 rd*(-backflip_vx)
    backflip_vx: float = 7.0
    backflip_c0_vy: float = -10.0
    backflip_c1_vy: float = -11.0

    # 滑铲火箭 Belly→Rocket；belly_rocket_vy 用作 -y
    belly_rocket_vx: float = 9.0
    belly_rocket_vy: float = 8.5

    # 超级扑跳冲量；普通扑跳 1.5 无差异，写死
    pounce_super: float = 9.0

    # 滑铲前冲正弦峰值；belly_no_kick=省略起始后蹬（仅溪流）
    belly_slide_spd: float = 18.1
    belly_no_kick: bool = False

    # 计时<此值按跳键=取消滑铲
    belly_jump_cancel_window: int = 12
    # 同向跑 tick 数>此值才可起刹
    skid_init_thresh: int = 10

    # 竖杆跳 beam jump：无持跳续力，y↓取负
    pole_jump_head_vx: float = 6.0
    pole_jump_head_vy: float = -8.0
    pole_jump_feet_vx: float = 5.0
    pole_jump_feet_vy: float = -7.0

    # 水/游泳
    buoyancy: float = 0.95
    lungs_fac: float = 1.0            # 耗气倍率
    swim_boost_force: float = 3.0
    swim_boost_cost: float = 0.2
    swim_boost_cd: int = 20           # tick
    swim_surface_speed: float = 2.7
    drown_threshold: float = 1.0 / 3.0  # 缺氧挣扎/自救阈
    swim_force_fac: float = 1.0
    bubble_fac: float = 1.0           # 吐泡概率倍率（桌宠原创）
    is_rivulet: bool = False          # 溪流游泳特判（潜泳冲力/鳃免溺等）
    is_artificer: bool = False        # 工匠水下耗尽气溺爆而死

    # 0-based，HUD 显示 +1；None=用全局 KARMA_MAX
    karma_cap: int | None = None


DEFAULT_STATS = SlugStats()
