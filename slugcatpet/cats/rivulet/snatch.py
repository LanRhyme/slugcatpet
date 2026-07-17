"""溪流驻留劫持 RivSnatch：光标中下带驻留→跑位后空翻掠过时劫持→落地回归日常行为、贴身携带 10s 后释放。"""
from __future__ import annotations

import math

from ...cats.saint.cursorlick import (BAND_LO, BAND_HI, DWELL_TICKS, SPEED_RELEASE)
from ...planning.ability import walk_band
from ...planning.backflip_reach import (best_launch_hit, sweep_hit_topsafe,
                                        takeoff_c0_h)
from ...planning.jump_reach import SETTLE_MAX, SETTLE_VX
from ...planning.jump_arc import get_backflip_arc

PLAN_R = 30.0
CATCH_R = 24.0
HOLD_MAX = 700
CARRY_TICKS = 400        # 10s
COOLDOWN = 1200          # 成功触发冷却
COOLDOWN_ABORT = 300     # 放弃/扑空冷却
WALK_TIMEOUT = 400
SNATCH_TIMEOUT = 800
ARRIVE_X = 8.0
LAUNCH_TIMEOUT = 80
# 携带期异常态即提前释放
_CARRY_BREAK = frozenset(("Dragged", "Stunned", "Dead", "Swimming"))


def mount_snatch(fsm):
    """RivSnatch 状态 + 驻留触发 ticker + 携带层 + 旁路兜底清扫。"""
    fsm._rs_cooldown = 0
    fsm._rs_hj = None
    fsm._rs_dirty = False
    fsm._rs_plan = None
    fsm._rs_carry = 0

    def in_band(cursor):
        return (cursor is not None
                and fsm.HL * BAND_LO <= cursor[1] <= fsm.HL * BAND_HI)

    def plan(cursor):
        # boosted 后空翻双方向选起跳点；无解=光标太高/太远
        cx, cy = cursor
        stats = fsm.win.cat.stats
        launch_y = fsm.HL - takeoff_c0_h(stats)
        xmin, xmax = walk_band(fsm.win)
        hipx = fsm.body.chunk1.x
        best = None
        for d in (1, -1):
            r = best_launch_hit(get_backflip_arc(stats, d, boosted=True), cx, cy,
                                launch_y, xmin, xmax, PLAN_R, hipx)
            if r is not None and (best is None or r[2] < best[2]):
                best = (r[0], d, r[2])
        return None if best is None else (best[0], best[1])

    def can_snatch():
        b = fsm.body
        return (fsm.state == "IdleStand" and fsm.cursor is not None
                and not fsm.grab.active and not fsm._exhausted
                and not fsm._zerog() and not b.swimming
                and fsm.win.cursor_hijack is None
                and fsm._rs_cooldown <= 0 and fsm._dwell >= DWELL_TICKS)

    def release_hold():
        hj = fsm._rs_hj
        if hj is not None:
            if fsm.win.cursor_hijack is hj:
                fsm.win.stop_cursor_hijack()
            else:
                hj.release()
            fsm._rs_hj = None

    def clear_motion():
        b = fsm.body
        b.animation = None
        b.jump_boost = 0.0
        b.stop_walk()
        fsm._rs_dirty = False

    def body_mid():
        c0, c1 = fsm.body.chunk0, fsm.body.chunk1
        return ((c0.x + c1.x) * 0.5, (c0.y + c1.y) * 0.5)

    def carry_tick():
        hj = fsm._rs_hj
        bad = (hj is None or fsm.win.cursor_hijack is not hj or not hj.active
               or fsm.grab.active or fsm.body.dead or fsm.body.swimming
               or fsm._zerog() or fsm.state in _CARRY_BREAK)
        fsm._rs_carry -= 1
        if bad or fsm._rs_carry <= 0:
            fsm._rs_carry = 0
            release_hold()
        else:
            fsm.win.move_cursor_hold(*body_mid())

    def watch():
        # 冷却回落 + 携带层推进 + 驻留触发 + 旁路打断兜底
        if fsm._rs_cooldown > 0:
            fsm._rs_cooldown -= 1
        if fsm._rs_carry > 0:
            carry_tick()
        if fsm.state == "RivSnatch":
            return
        if fsm._rs_dirty:
            release_hold()
            clear_motion()
        if can_snatch():
            p = plan(fsm.cursor)
            if p is not None:
                fsm._rs_plan = p
                fsm._rs_cooldown = COOLDOWN
                fsm._transition("RivSnatch")

    def enter():
        b = fsm.body
        b.set_posture(True)
        fsm._clear_hands()
        fsm._rs_phase = "walk"
        fsm._rs_settle = 0
        fsm._rs_launch_t = 0
        fsm._rs_airborne = False
        fsm._rs_hj = None
        fsm._rs_d = 0
        fsm._rs_dirty = True
        fsm._rs_x = fsm._rs_plan[0] if fsm._rs_plan is not None else None
        if fsm._rs_x is not None:
            b.walk_to(fsm._rs_x)

    def finish(b, ok):
        brk(cooldown=COOLDOWN if ok else COOLDOWN_ABORT)
        fsm._transition("IdleStand" if b.on_floor() else "Airborne")

    def hold_lost():
        # 外部解除（Ctrl+Alt+Q/被顶替）
        return (fsm._rs_hj is not None
                and (fsm.win.cursor_hijack is not fsm._rs_hj or not fsm._rs_hj.active))

    def pick_at_launch(cursor):
        # 起跳瞬间按实时光标重选方向
        c0 = fsm.body.chunk0
        stats = fsm.win.cat.stats
        first = 1 if cursor[0] >= c0.x else -1
        for d in (first, -first):
            if sweep_hit_topsafe(get_backflip_arc(stats, d, boosted=True),
                                 cursor[0] - c0.x, cursor[1] - c0.y,
                                 PLAN_R, c0.y) is not None:
                return d
        return None

    def st_rivsnatch(cursor, disturbed):
        b = fsm.body
        if hold_lost():
            finish(b, ok=True)
            return
        if fsm.timer > SNATCH_TIMEOUT or fsm._rs_x is None:
            finish(b, ok=False)
            return
        ph = fsm._rs_phase
        if ph == "walk":
            if (cursor is None or not in_band(cursor)
                    or fsm._cursor_speed > SPEED_RELEASE or fsm.timer > WALK_TIMEOUT):
                finish(b, ok=False)
                return
            fsm.gfx.look_at = cursor
            if b.on_floor() and (not b.is_moving()
                                 or abs(b.chunk1.x - fsm._rs_x) < ARRIVE_X):
                b.stop_walk()
                fsm._rs_phase = "settle"
            else:
                b.walk_to(fsm._rs_x)
            return
        if ph == "settle":
            if cursor is None or fsm._cursor_speed > SPEED_RELEASE:
                finish(b, ok=False)
                return
            b.stop_walk()
            fsm._rs_settle += 1
            still = abs(b.chunk0.vx) < SETTLE_VX and abs(b.chunk1.vx) < SETTLE_VX
            if b.on_floor() and (still or fsm._rs_settle > SETTLE_MAX):
                d = pick_at_launch(cursor)
                if d is None:
                    finish(b, ok=False)
                    return
                b.backflip_launch(d, boosted=True)
                fsm._rs_d = d
                fsm._rs_phase = "air"
                fsm._rs_launch_t = 0
            return
        if not b.on_floor():
            fsm._rs_airborne = True
            b.move_dir = fsm._rs_d
            if fsm._rs_hj is None and cursor is not None and fsm.win.cursor_hijack is None:
                mx, my = body_mid()
                c0 = b.chunk0
                near = min(math.hypot(cursor[0] - mx, cursor[1] - my),
                           math.hypot(cursor[0] - c0.x, cursor[1] - c0.y))
                if near <= CATCH_R:
                    fsm._rs_hj = fsm.win.start_cursor_hold(mx, my, HOLD_MAX)
            if fsm._rs_hj is not None:
                fsm.win.move_cursor_hold(*body_mid())
        elif fsm._rs_airborne:
            if fsm._rs_hj is not None:
                clear_motion()
                b.set_posture(True)
                fsm._rs_carry = CARRY_TICKS
                fsm._rs_cooldown = COOLDOWN
                fsm._transition("IdleStand")
            else:
                finish(b, ok=False)              # 扑空
        else:
            fsm._rs_launch_t += 1
            if fsm._rs_launch_t > LAUNCH_TIMEOUT:
                finish(b, ok=False)

    def brk(cooldown=COOLDOWN_ABORT):
        b = fsm.body
        d = b.move_dir
        release_hold()
        clear_motion()
        b.set_posture(True)
        fsm._clear_hands()
        if d != 0:
            b.facing = 1 if d > 0 else -1
        fsm._rs_cooldown = cooldown

    fsm.register_ticker(watch)
    fsm.register_state("RivSnatch", enter=enter, tick=st_rivsnatch,
                       brk=brk, kill_break=brk)
