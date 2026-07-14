"""Artificer 独占状态挂载：caps.pyro → 燃料回落 ticker + PyroRomp 爆跳撒欢态 + mood 候选。"""
from __future__ import annotations

from ...behavior import tuning
from ...behavior.desire import Candidate, play_gate, play_mult
from ...behavior.fsm import pick_open_x
from ...planning.backflip_reach import SETTLE_MAX, SETTLE_VX
from ...planning.jump_arc import PYRO_INPUTS
from . import pyro

ARRIVE_X = 8.0           # px
LAUNCH_TIMEOUT = 80      # 起跳未腾空兜底 tick（被顶/卡住）
ROMP_TIMEOUT = 1200      # tick，仿 T_HPOLE_TIMEOUT 量级


def mount(fsm):
    """按 caps.pyro 挂载燃料 ticker + PyroRomp。"""
    if fsm.win.cat.caps.pyro:
        pyro.ensure(fsm.body)
        fsm.register_ticker(lambda: pyro.tick_fuel(fsm.win, fsm.body))
        _mount_pyroromp(fsm)


def _mount_pyroromp(fsm):
    """PyroRomp：选开阔点→走位→settle→普通跳→腾空第 PYRO_BOOST_AIR_TICKS tick 爆冲→落地，按 PYROROMP_JUMPS 再来或回 IdleStand。"""
    heat_cap = fsm.win.cat.tuning["pyro_heat_cap"]

    def fuel_ok(cost):
        # AI 不自爆：counter+本次成本≤heat_cap
        pyro.ensure(fsm.body)
        return fsm.body._ctrl_pyro_counter + cost <= heat_cap

    def next_round():
        fsm._romp_phase = "walk"
        fsm._romp_settle = 0
        fsm._romp_air = 0
        fsm._romp_launch_t = 0
        fsm._romp_fired = False
        fsm._romp_airborne = False
        fsm._romp_x = pick_open_x(fsm)
        fsm.body.walk_to(fsm._romp_x)

    def enter():
        fsm.body.set_posture(True)
        fsm._clear_hands()
        fsm._romp_jumps = 0
        fsm._romp_dirty = True
        next_round()

    def pick_variant():
        # 一半冲天直跳，否则朝开阔侧上斜
        if fsm.rng.random() < 0.5:
            return "vert"
        return "diag+" if fsm.body.chunk0.x < fsm.WL * 0.5 else "diag-"

    def finish(b):
        brk()
        fsm._transition("IdleStand" if b.on_floor() else "Airborne")

    def st_pyroromp(cursor, disturbed):
        b = fsm.body
        if fsm.timer > ROMP_TIMEOUT:
            finish(b)
            return
        ph = fsm._romp_phase
        if ph == "walk":
            if b.on_floor() and (not b.is_moving()
                                 or abs(b.chunk1.x - fsm._romp_x) < ARRIVE_X):
                b.stop_walk()
                fsm._romp_phase = "settle"
            return
        if ph == "settle":
            b.stop_walk()
            fsm._romp_settle += 1
            still = abs(b.chunk0.vx) < SETTLE_VX and abs(b.chunk1.vx) < SETTLE_VX
            if b.on_floor() and (still or fsm._romp_settle > SETTLE_MAX):
                if not fuel_ok(1):
                    finish(b)
                    return
                fsm._romp_variant = pick_variant()
                b.request_jump("stand")
                fsm._romp_phase = "air"
                fsm._romp_launch_t = 0
            return
        # air：腾空达阈值发射（再过燃料门），落地按次数再来或收工
        if not b.on_floor():
            fsm._romp_airborne = True
            fsm._romp_air += 1
            if not fsm._romp_fired and fsm._romp_air >= tuning.PYRO_BOOST_AIR_TICKS:
                fsm._romp_fired = True
                if fuel_ok(1):
                    ix, iy = PYRO_INPUTS[fsm._romp_variant]
                    pyro.fire_air_jump(fsm.win, b, ix, iy)
        elif fsm._romp_airborne:
            b.animation = None
            b.jump_boost = 0.0
            b.set_posture(True)          # 落地扶正
            fsm._romp_jumps += 1
            if fsm._romp_jumps >= tuning.PYROROMP_JUMPS or not fuel_ok(1):
                finish(b)
            else:
                next_round()
        else:
            fsm._romp_launch_t += 1
            if fsm._romp_launch_t > LAUNCH_TIMEOUT:
                finish(b)

    def clear_motion():
        # 无 ANIM_RESET 兜底：终止必清 animation/jump_boost/走停
        b = fsm.body
        b.animation = None
        b.jump_boost = 0.0
        b.stop_walk()
        fsm._romp_dirty = False

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
        if fsm.state != "PyroRomp" and getattr(fsm, "_romp_dirty", False):
            clear_motion()

    fsm.register_ticker(leak_watch)
    fsm.register_state("PyroRomp", enter=enter, tick=st_pyroromp,
                       brk=brk, kill_break=brk, mood="pyro_romp")

    mult = play_mult(fsm.pers, "pyro_romp")
    energy_gate = play_gate(fsm.pers)

    def gate(ctx):
        # 燃料门 counter+全轮跳数≤heat_cap；泳/零重力退避；体力过门
        pyro.ensure(fsm.body)
        return (not ctx.submerged and not getattr(fsm.body, "zerog", False)
                and ctx.energy >= energy_gate
                and fsm.body._ctrl_pyro_counter + tuning.PYROROMP_JUMPS <= heat_cap)

    fsm.mood.add(Candidate(
        "pyro_romp", base=tuning.PYROROMP_BASE * mult,
        start=tuning.PYROROMP_START, quit=tuning.PYROROMP_QUIT,
        decay=tuning.PYROROMP_DECAY, recover=tuning.PYROROMP_RECOVER,
        gate=gate,
        energy_factor=lambda e: 1.0, temper_factor=lambda t: 1.0,
        one_shot=True, init=tuning.PYROROMP_INIT))
