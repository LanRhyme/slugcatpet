"""工匠低好感光标劫持 PyroMaul：光标经过后，移远≥2身位概率爆跳扑抓；贴身驻留3s直接走近啃；埋身啃咬一嘴后松开。"""
from __future__ import annotations

import math

from ...behavior.fetch import BITE_HEAD_NUDGE
from ...control.mouse import is_over
from ...planning.jump_reach import SETTLE_MAX, SETTLE_VX
from . import pyro

BODY_LEN = 34.0          # 一个身位：chunk 间距 17 + 两端半径
OVER_PAD = 6.0
POUNCE_PROB = 0.30
COOLDOWN = 1200          # 30s，两种模式共用
NEAR_DIST = BODY_LEN     # 贴身驻留门
NEAR_TICKS = 120         # 3s
NEAR_GIVEUP = BODY_LEN * 2.5
NEAR_CATCH_R = 30.0      # 走近模式嘴-光标抓住判定
POUNCE_MIN = BODY_LEN * 2.0
POUNCE_MAX = 350.0
POUNCE_MAX_RISE = 160.0  # 高于此够不到（vert/diag apex ~165）
CATCH_R = 26.0           # 爆跳空中嘴-光标抓住判定
HOLD_MAX = 400           # hold 看门狗上限
LAUNCH_TIMEOUT = 80
APPROACH_TIMEOUT = 200
MAUL_TIMEOUT = 600
CHEW_TICKS = 60          # ~1.5s
BITE_PERIOD = 8          # 原版 maul：每 8 tick 一口
JITTER_PERIOD = 3        # 原版 maul：每 3 tick 身体微抖
JITTER_AMP = 1.2


def _fire_tick_for(dist):
    """起跳时按光标距离查开始时刻。"""
    if dist < 95.0:
        return 18
    if dist < 145.0:
        return 16
    if dist < 185.0:
        return 14
    if dist < 235.0:
        return 13
    return 8


def _variant_for(dx, dy):
    """点火瞬间按光标方位选爆冲输入：正上 vert、高角 diag、平角 side。"""
    adx = abs(dx)
    sx = 1 if dx >= 0 else -1
    if adx < 40.0 and dy < -90.0:
        return (0, 0)
    if -dy > adx * 0.7:
        return (sx, 1)
    return (sx, 0)


def mount_maul(fsm):
    """PyroMaul 状态 + 经过追踪触发 ticker + 旁路兜底清扫。"""
    heat_cap = fsm.win.cat.tuning["pyro_heat_cap"]
    temper_gate = fsm.win.cat.tuning["temper_maul_gate"]
    fsm._pm_cooldown = 0
    fsm._pm_over = False
    fsm._pm_pass = False
    fsm._pm_near_t = 0
    fsm._pm_rolled = False
    fsm._pm_mode = "pounce"
    fsm._pm_hj = None
    fsm._pm_dirty = False

    def fuel_ok():
        pyro.ensure(fsm.body)
        return fsm.body._ctrl_pyro_counter + 1 <= heat_cap

    def body_dist(cursor):
        c0, c1 = fsm.body.chunk0, fsm.body.chunk1
        return min(math.hypot(cursor[0] - c0.x, cursor[1] - c0.y),
                   math.hypot(cursor[0] - c1.x, cursor[1] - c1.y))

    def gates_ok():
        b = fsm.body
        return (fsm.state == "IdleStand" and b.on_floor()
                and not fsm.grab.active and not fsm._exhausted
                and not fsm._zerog() and not b.swimming
                and fsm.win.cursor_hijack is None
                and b.carried_fruit is None and b.carried_stone is None
                and b.temper <= temper_gate and fsm._pm_cooldown <= 0)

    def release_hold():
        hj = fsm._pm_hj
        if hj is not None:
            if fsm.win.cursor_hijack is hj:
                fsm.win.stop_cursor_hijack()
            else:
                hj.release()
            fsm._pm_hj = None

    def clear_motion():
        b = fsm.body
        b.animation = None
        b.jump_boost = 0.0
        b.stop_walk()
        fsm._pm_dirty = False

    def reset_track():
        fsm._pm_pass = False
        fsm._pm_near_t = 0
        fsm._pm_rolled = False

    def trigger(mode):
        fsm._pm_cooldown = COOLDOWN
        fsm._pm_mode = mode
        reset_track()
        fsm._transition("PyroMaul")

    def watch():
        # 冷却回落 + 经过追踪（远→爆跳/贴身驻留→走近啃）+ 旁路打断兜底
        if fsm._pm_cooldown > 0:
            fsm._pm_cooldown -= 1
        cursor = fsm.cursor
        over = cursor is not None and is_over(fsm.body, fsm.gfx, cursor, pad=OVER_PAD)
        if fsm.state == "PyroMaul":
            fsm._pm_over = over
            return
        if fsm._pm_dirty:
            release_hold()
            clear_motion()
        if not gates_ok():
            fsm._pm_over = over
            reset_track()
            return
        if over:
            if not fsm._pm_over:
                fsm._pm_pass = True
                fsm._pm_rolled = False
            fsm._pm_near_t += 1      # 悬在身上也算 1 身位内
            if fsm._pm_near_t >= NEAR_TICKS:
                trigger("walkup")
        elif cursor is None:
            reset_track()
        elif fsm._pm_pass:
            d = body_dist(cursor)
            if d <= NEAR_DIST:
                fsm._pm_near_t += 1
                if fsm._pm_near_t >= NEAR_TICKS:
                    trigger("walkup")
            else:
                fsm._pm_near_t = 0
                if d >= POUNCE_MIN and not fsm._pm_rolled:
                    fsm._pm_rolled = True
                    rise = fsm.body.chunk0.y - cursor[1]
                    if (fsm.rng.random() < POUNCE_PROB and fuel_ok()
                            and d <= POUNCE_MAX and rise <= POUNCE_MAX_RISE):
                        trigger("pounce")
                    else:
                        fsm._pm_pass = False       # 本次经过作废
        fsm._pm_over = over

    def enter():
        b = fsm.body
        b.set_posture(True)
        b.stop_walk()
        fsm._clear_hands()
        fsm._pm_phase = "approach" if fsm._pm_mode == "walkup" else "settle"
        fsm._pm_settle = 0
        fsm._pm_air = 0
        fsm._pm_ft = 0
        fsm._pm_fired = False
        fsm._pm_airborne = False
        fsm._pm_launch_t = 0
        fsm._pm_chew_t = 0
        fsm._pm_hj = None
        fsm._pm_dirty = True
        if fsm.cursor is not None:
            b.facing = 1 if fsm.cursor[0] >= b.chunk0.x else -1

    def finish(b):
        brk()
        fsm._transition("IdleStand" if b.on_floor() else "Airborne")

    def hold_lost():
        # 外部解除（Ctrl+Alt+Q/被顶替）
        return (fsm._pm_hj is not None
                and (fsm.win.cursor_hijack is not fsm._pm_hj or not fsm._pm_hj.active))

    def pin_to_mouth():
        mox, moy = fsm.gfx.mouth_world()
        fsm.win.move_cursor_hold(mox, moy)
        fsm.gfx.hand_aim["l"] = (mox, moy)
        fsm.gfx.hand_aim["r"] = (mox, moy)
        return mox, moy

    def enter_chew(b):
        b.animation = None
        b.jump_boost = 0.0
        b.stop_walk()
        b.set_posture(False)
        fsm._pm_phase = "chew"
        fsm._pm_chew_t = 0

    def st_pyromaul(cursor, disturbed):
        b = fsm.body
        if fsm.timer > MAUL_TIMEOUT or hold_lost():
            finish(b)
            return
        ph = fsm._pm_phase
        if ph == "approach":
            if (cursor is None or body_dist(cursor) > NEAR_GIVEUP
                    or fsm.timer > APPROACH_TIMEOUT):
                finish(b)
                return
            fsm.gfx.look_at = cursor
            mox, moy = fsm.gfx.mouth_world()
            if (math.hypot(cursor[0] - mox, cursor[1] - moy) <= NEAR_CATCH_R
                    and fsm.win.cursor_hijack is None):
                fsm._pm_hj = fsm.win.start_cursor_hold(mox, moy, HOLD_MAX)
                enter_chew(b)
                return
            b.walk_to(cursor[0])
            return
        if ph == "settle":
            b.stop_walk()
            fsm._pm_settle += 1
            still = abs(b.chunk0.vx) < SETTLE_VX and abs(b.chunk1.vx) < SETTLE_VX
            if b.on_floor() and (still or fsm._pm_settle > SETTLE_MAX):
                if cursor is None:
                    finish(b)
                    return
                d = body_dist(cursor)
                rise = b.chunk0.y - cursor[1]
                if (d < POUNCE_MIN * 0.7 or d > POUNCE_MAX
                        or rise > POUNCE_MAX_RISE):
                    finish(b)          # 光标折回/跑太远=放弃
                    return
                fsm._pm_ft = _fire_tick_for(d)
                b.request_jump("stand")
                fsm._pm_phase = "air"
                fsm._pm_launch_t = 0
            return
        if ph == "air":
            if not b.on_floor():
                fsm._pm_airborne = True
                fsm._pm_air += 1
                if fsm._pm_hj is not None:
                    fsm._pm_fired = True
                if not fsm._pm_fired and fsm._pm_air >= fsm._pm_ft:
                    fsm._pm_fired = True
                    if cursor is not None and fuel_ok():
                        c0 = b.chunk0
                        ix, iy = _variant_for(cursor[0] - c0.x, cursor[1] - c0.y)
                        pyro.fire_air_jump(fsm.win, b, ix, iy)
                if fsm._pm_fired and fsm._pm_hj is None and cursor is not None:
                    b.move_dir = 1 if cursor[0] >= b.chunk0.x else -1
                elif fsm._pm_hj is not None:
                    b.move_dir = 0
                if fsm._pm_hj is None and cursor is not None and fsm.win.cursor_hijack is None:
                    mox, moy = fsm.gfx.mouth_world()
                    if math.hypot(cursor[0] - mox, cursor[1] - moy) <= CATCH_R:
                        fsm._pm_hj = fsm.win.start_cursor_hold(mox, moy, HOLD_MAX)
                if fsm._pm_hj is not None:
                    pin_to_mouth()
            elif fsm._pm_airborne:
                if fsm._pm_hj is not None:
                    enter_chew(b)
                else:
                    finish(b)          # 扑空放弃
            else:
                fsm._pm_launch_t += 1
                if fsm._pm_launch_t > LAUNCH_TIMEOUT:
                    finish(b)
            return
        
        fsm._pm_chew_t += 1
        mox, moy = pin_to_mouth()
        fsm.gfx.look_at = (mox, moy)
        if fsm._pm_chew_t % JITTER_PERIOD == 0:
            b.chunk0.vx += fsm.rng.uniform(-JITTER_AMP, JITTER_AMP)
            b.chunk0.vy += fsm.rng.uniform(-JITTER_AMP, JITTER_AMP)
        if fsm._pm_chew_t % BITE_PERIOD == BITE_PERIOD // 2:
            hd = fsm.gfx.head
            dx, dy = mox - hd.x, moy - hd.y
            d = math.hypot(dx, dy)
            if d > 1e-6:
                hd.vx += dx / d * BITE_HEAD_NUDGE
                hd.vy += dy / d * BITE_HEAD_NUDGE
        if fsm._pm_chew_t >= CHEW_TICKS:
            finish(b)

    def brk():
        b = fsm.body
        release_hold()
        clear_motion()
        b.set_posture(True)
        fsm._clear_hands()
        fsm._pm_cooldown = COOLDOWN

    fsm.register_ticker(watch)
    fsm.register_state("PyroMaul", enter=enter, tick=st_pyromaul,
                       brk=brk, kill_break=brk)
