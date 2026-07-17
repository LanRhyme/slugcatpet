"""Rivulet 独占状态：caps.acrobat → RivFlip 后空翻上横杆 + mood 候选。"""
from __future__ import annotations

import math

from ...behavior import tuning
from ...behavior.desire import Candidate, play_gate, play_mult
from ...planning.backflip_reach import SETTLE_MAX, SETTLE_VX, TOP_CLEAR, takeoff_c0_h
from ...planning.jump_arc import get_backflip_arc
from ...world.hpole import GRIP_DIST

ARRIVE_X = 8.0           # px
LAUNCH_TIMEOUT = 80      # 起跳未腾空兜底 tick
FLIP_TIMEOUT = 1200      # tick
POLE_X_MARGIN = 10.0     # 离杆端余量 px
AIM_BAND = GRIP_DIST - 4.0   # 贴杆瞄准带，留 sim 残差余量


def mount(fsm):
    """按 caps.acrobat 挂载 RivFlip + RivSnatch。"""
    if fsm.win.cat.caps.acrobat:
        _mount_rivflip(fsm)
        from .snatch import mount_snatch
        mount_snatch(fsm)


def _walk_band(fsm):
    b = fsm.body
    return (0.0 if b.walk_min is None else b.walk_min,
            fsm.WL if b.walk_max is None else b.walk_max)


def _pole_reachable(fsm):
    """gate 预检：横杆抬升在 apex+GRIP_DIST 内（不跑全量选点）。"""
    stats = fsm.win.cat.stats
    launch_y = fsm.HL - takeoff_c0_h(stats)
    apex = max(get_backflip_arc(stats, 1).apex, get_backflip_arc(stats, -1).apex)
    for pole in fsm.win.poles:
        if getattr(pole, "kind", None) != "horizontal":
            continue
        rise = launch_y - pole.ay
        if 0.0 < rise <= apex + GRIP_DIST:
            return True
    return False


def _pole_plan(fsm):
    """选可达横杆：杆线在起跳 chunk0 上方且 apex+GRIP_DIST 够到 → (pole, d, launch_x)；无 → None。"""
    stats = fsm.win.cat.stats
    launch_y = fsm.HL - takeoff_c0_h(stats)
    b = fsm.body
    xmin, xmax = _walk_band(fsm)
    for pole in fsm.win.poles:
        if getattr(pole, "kind", None) != "horizontal":
            continue
        rise = launch_y - pole.ay
        if rise <= 0.0:
            continue
        lo = min(pole.ax, pole.bx) + POLE_X_MARGIN
        hi = max(pole.ax, pole.bx) - POLE_X_MARGIN
        if hi <= lo:
            continue
        # 锚点：贴近当前 x 优先，其次杆中点
        for ax_t in (max(lo, min(hi, b.chunk1.x)), (lo + hi) * 0.5):
            for d in ((1, -1) if ax_t >= b.chunk1.x else (-1, 1)):
                arc = get_backflip_arc(stats, d)
                if arc.apex + GRIP_DIST < rise:
                    continue
                for px, py in arc.points:
                    if launch_y + py < TOP_CLEAR:   # 越窗顶余量：其后命中被 clamp 失真，弃该弧
                        break
                    if abs(launch_y + py - pole.ay) <= AIM_BAND:
                        lx = ax_t - px
                        if xmin <= lx <= xmax:
                            return (pole, d, lx)
    return None


def _near_pole(b, pole):
    """chunk0 距杆线（x clamp 进杆段）≤ GRIP_DIST 即可抓。"""
    lo = min(pole.ax, pole.bx) + 2.0
    hi = max(pole.ax, pole.bx) - 2.0
    c0 = b.chunk0
    ax = max(lo, min(hi, c0.x))
    return math.hypot(c0.x - ax, c0.y - pole.ay) <= GRIP_DIST


def _mount_rivflip(fsm):
    """RivFlip：全量选点→走到杆下起跳点→settle→backflip_launch→贴杆转 HPole；无解不翻、抓不上落地即收工。"""

    def enter():
        fsm.body.set_posture(True)
        fsm._clear_hands()
        plan = _pole_plan(fsm)
        if plan is None:                 # 预检过但选点无解→收工
            fsm._rf_dirty = False
            fsm._rf_pole = None
            fsm._transition("IdleStand")
            return
        fsm._rf_dirty = True
        fsm._rf_pole, fsm._rf_d, fsm._rf_x = plan
        fsm._rf_phase = "walk"
        fsm._rf_settle = 0
        fsm._rf_launch_t = 0
        fsm._rf_airborne = False
        fsm.body.walk_to(fsm._rf_x)

    def finish(b):
        brk()
        fsm._transition("IdleStand" if b.on_floor() else "Airborne")

    def st_rivflip(cursor, disturbed):
        b = fsm.body
        if fsm.timer > FLIP_TIMEOUT:
            finish(b)
            return
        pole = fsm._rf_pole
        if pole is not None and pole not in fsm.win.poles:   # 杆没了：空中顺势落地，未起跳直接收工
            pole = fsm._rf_pole = None
        ph = fsm._rf_phase
        if pole is None and ph != "air":
            finish(b)
            return
        if ph == "walk":
            if b.on_floor() and (not b.is_moving()
                                 or abs(b.chunk1.x - fsm._rf_x) < ARRIVE_X):
                b.stop_walk()
                fsm._rf_phase = "settle"
            return
        if ph == "settle":
            b.stop_walk()
            fsm._rf_settle += 1
            still = abs(b.chunk0.vx) < SETTLE_VX and abs(b.chunk1.vx) < SETTLE_VX
            if b.on_floor() and (still or fsm._rf_settle > SETTLE_MAX):
                b.backflip_launch(fsm._rf_d)
                fsm._rf_phase = "air"
                fsm._rf_launch_t = 0
            return
        # air：贴杆交 HPole，抓不上落地收工
        if not b.on_floor():
            fsm._rf_airborne = True
            b.move_dir = fsm._rf_d
            if pole is not None and _near_pole(b, pole):
                b.stop_walk()
                fsm._rf_dirty = False        # animation 交 HPole 生命周期接管
                fsm._hpole_pole = pole
                fsm._transition("HPole")
            return
        if fsm._rf_airborne:
            finish(b)
        else:
            fsm._rf_launch_t += 1
            if fsm._rf_launch_t > LAUNCH_TIMEOUT:
                finish(b)

    def clear_motion():
        # 无 ANIM_RESET 兜底：终止必清 animation/jump_boost/走停
        b = fsm.body
        b.animation = None
        b.jump_boost = 0.0
        b.stop_walk()
        fsm._rf_dirty = False

    def brk():
        # 落地扶正：站姿，面朝行进方向
        b = fsm.body
        d = b.move_dir
        clear_motion()
        b.set_posture(True)
        if d != 0:
            b.facing = 1 if d > 0 else -1

    def leak_watch():
        # 旁路打断兜底（被抓/被砸晕不走 brk）：只清运动残留
        if fsm.state != "RivFlip" and getattr(fsm, "_rf_dirty", False):
            clear_motion()

    fsm.register_ticker(leak_watch)
    fsm.register_state("RivFlip", enter=enter, tick=st_rivflip,
                       brk=brk, kill_break=brk, mood="riv_flip")

    mult = play_mult(fsm.pers, "riv_flip")
    energy_gate = play_gate(fsm.pers)

    def gate(ctx):
        # 泳/零重力退避；体力过门；有可达横杆
        return (not ctx.submerged and not getattr(fsm.body, "zerog", False)
                and ctx.energy >= energy_gate and _pole_reachable(fsm))

    fsm.mood.add(Candidate(
        "riv_flip", base=tuning.RIVFLIP_BASE * mult,
        start=tuning.RIVFLIP_START, quit=tuning.RIVFLIP_QUIT,
        decay=tuning.RIVFLIP_DECAY, recover=tuning.RIVFLIP_RECOVER,
        gate=gate,
        energy_factor=lambda e: 1.0, temper_factor=lambda t: 1.0,
        one_shot=True, init=tuning.RIVFLIP_INIT))
