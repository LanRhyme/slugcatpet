"""控制会话编排：进入/退出手动控制的状态复位、FSM 冻结与交还（挂点在 PetUnit.step）。"""
from __future__ import annotations

from .input import InputBuffer

# 退出控制复位表（字段 → 默认值）；进/退共用，测试遍历断言
RESET_TABLE: dict[str, object] = {
    "_ctrl_on": False,               # 总闸
    "_input_provider": None,         # 不摘则每 tick 重置 _ctrl_on=True
    "_ctrl_input": None,             # 防跨会话陈旧边沿
    "_ctrl_want_jump": 0,            # 防再入首帧误跳
    "_ctrl_can_jump": 0,
    "_ctrl_roll_direction": 0,       # 双保险
    "_ctrl_roll_counter": 0,
    "_ctrl_whiplash": False,         # 退出后无人清
    "_ctrl_flip_from_slide": False,
    "_ctrl_rocket_from_belly": False,
    "_ctrl_exit_belly": 0,
    "_ctrl_stop_rolling": 0,
    "_ctrl_super_launch": 0,         # 防下次开局白送持跳
    "_ctrl_sim_hold": 0,
    "_ctrl_sl_decay": 0,
    "_ctrl_slide_direction": 0,      # 防下次误走 flip_skid_jump
    "_ctrl_init_slide_counter": 0,
    "_ctrl_slide_counter": 0,
    "_ctrl_allow_roll": 0,           # 防再入首帧误触落地滚
    "_ctrl_consistent_dd": 0,
    "_ctrl_fall_speed": 0.0,
    "_ctrl_prev_floor": True,
    "_ctrl_lower_on_ground": 0,      # 防再入误触 StandUp/DownOnFours
    "_ctrl_upper_off_ground": 0,
    "_ctrl_crawl_turn_delay": 0,
    "_ctrl_pyro": None,              # 工匠专属，非工匠恒 None
    "_ctrl_pyro_jumped": False,      # 与 PYRO_DEFAULTS 同步
    "_ctrl_pyro_counter": 0,
    "_ctrl_pyro_cooldown": 0.0,
    "_ctrl_pyro_parry_cd": 0.0,
}

# 退出时清控制专属动画，不碰 ZeroGPoleGrab
ANIM_RESET = frozenset(("Roll", "Flip", "BellySlide", "RocketJump",
                        "CrawlTurn", "StandUp", "DownOnFours"))


def reset_ctrl_state(body) -> None:
    """按复位表把控制态字段全部归默认（进入/退出共用）。"""
    for k, v in RESET_TABLE.items():
        setattr(body, k, v)


def enter_control(pet, provider) -> None:
    """接管一只猫，FSM 冻结于 IdleStand。"""
    body = pet.body
    beh = pet.behavior
    if beh is not None:
        beh._break_active_controllers()
        beh.grab.force_release()
        beh._hibernating = False
    body.stop_walk()
    body.walk_speed_target = None
    body.zerog_pole = None             # FSM 冻结后无人松杆
    pet.gfx.sleeping = False
    body.sleeping = False
    pet.gfx.look_at = None
    if beh is not None:
        # 强制态直写+_enter，绕 _transition 早退
        beh.state = "IdleStand"
        beh.timer = 0
        beh.phase = 0
        beh._enter("IdleStand")
    reset_ctrl_state(body)
    body._ctrl_input = InputBuffer()   # 新建历史环，防跨会话陈旧边沿
    body._input_provider = provider
    _mount_species_ctrl(pet, body)
    pet.controlled = True


def _mount_species_ctrl(pet, body) -> None:
    """种族专属控制器挂载，非命中种族保持 None。"""
    if getattr(pet.cat, "key", None) == "artificer":
        from ..cats.artificer.pyro import PyroController
        body._ctrl_pyro = PyroController(pet)


def exit_control(pet) -> None:
    """交还一只猫（幂等）。"""
    if not getattr(pet, "controlled", False):
        return
    body = pet.body
    body._input_provider = None
    body._ctrl_on = False
    reset_ctrl_state(body)
    if body.animation in ANIM_RESET:   # 死体残留 Roll 会让尾钩永续触发
        body.animation = None
    body.stop_walk()
    body.jump_boost = 0.0
    beh = pet.behavior
    if beh is not None:
        if body.dead:
            pass                       # 留 Dead
        elif body.stun > 0:
            # 留 Stunned，强制进以防未在此态
            beh.state = "Stunned"
            beh.timer = 0
            beh.phase = 0
            beh._enter("Stunned")
        else:
            # 强制进，绕同名早退
            st = "IdleStand" if body.on_floor() else "Airborne"
            beh.state = st
            beh.timer = 0
            beh.phase = 0
            beh._enter(st)
    pet.controlled = False
