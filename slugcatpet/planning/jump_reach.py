"""跳跃够取能力（全员）：走到起跳点→驻停→按档起跳，竖直或持向横弧；空中探身+持向漂移，落地报 done。"""
from __future__ import annotations

from ..behavior import tuning
from ..core.units import clampf
from .ability import Ability, Estimate, RUNNING, DONE, GIVEUP, reach_assist, walk_band
from .jump_arc import get_arc, sweep_hit

SETTLE_VX = 0.3
SETTLE_MAX = 40      # 驻停等待上限，超时按当前状态起跳
# 预留走位残差，防"规划说行/临跳说不行"死循环
PLAN_HIT_RADIUS = tuning.GRAB_REACH - tuning.PLAN_JUMP_TAKEOFF_EPS


def _free_launch_hit(arc, gx, gy, launch_y, xmin, xmax, radius):
    """定 launch_y、自由 launch_x∈[xmin,xmax]：找弧上某点命中 (gx,gy) 的 (launch_x, tick)；无则 None。"""
    for i, (px, py) in enumerate(arc.points):
        lx = gx - px
        if xmin <= lx <= xmax and abs((launch_y + py) - gy) <= radius:
            return lx, i + 1
    return None


class JumpReach(Ability):
    key = "jump"

    def _plan(self, goal):
        # 枚举 档×{竖直,右,左}，取耗时最省
        pet = self.pet
        gx, gy = goal.pos()
        xmin, xmax = walk_band(pet)
        stats = pet.cat.stats
        floor = pet._HL
        hipx = pet.body.chunk1.x
        best = None
        best_t = None

        def consider(lx, hold, md, hit):
            nonlocal best, best_t
            t = abs(hipx - lx) / tuning.PLAN_WALK_SPEED + hit + tuning.PLAN_STARTUP_TICKS
            if best_t is None or t < best_t:
                best_t = t
                best = (lx, hold, md, hit)

        for hold in tuning.PLAN_JUMP_HOLD_GEARS:
            arc0 = get_arc(stats, hold, 0)
            if xmin <= gx <= xmax:
                dy = gy - (floor - arc0.takeoff_h)
                hit = sweep_hit(arc0, 0.0, dy, PLAN_HIT_RADIUS)
                if hit is not None:
                    consider(gx, hold, 0, hit)
            for md in (1, -1):
                arc = get_arc(stats, hold, md)
                lh = _free_launch_hit(arc, gx, gy, floor - arc.takeoff_h,
                                      xmin, xmax, PLAN_HIT_RADIUS)
                if lh is not None:
                    lx, hit = lh
                    consider(lx, hold, md, hit)
        if best is None:
            return None
        return best + (best_t,)

    def can_touch(self, goal):
        plan = self._plan(goal)
        if plan is None:
            return None
        _, _, md, hit, t = plan
        walk_t = t - hit - tuning.PLAN_STARTUP_TICKS
        return Estimate(t, walk_t * tuning.PLAN_EN_RATE_LIGHT
                        + hit * tuning.PLAN_EN_RATE_VIGOROUS)

    def make_controller(self, goal):
        return JumpReachController(self.pet, goal)


class JumpReachController:
    """走到起跳 x（紧到位判定）→ 驻停 → 起跳时刻以实际 chunk0 重选 (档,横向) 起跳，持向探身，落地报 done。"""

    def __init__(self, pet, goal):
        self.pet = pet
        self.goal = goal
        self.phase = "walk"
        self._settle = 0
        self._airborne = False
        self._move_dir = 0
        plan = JumpReach(pet)._plan(goal)
        self._launch_x = plan[0] if plan is not None else None

    def update(self):
        pet = self.pet
        body = pet.body
        gx, gy = self.goal.pos()
        reach_assist(pet, self.goal, gx, gy)
        if self._launch_x is None:
            return GIVEUP
        xmin, xmax = walk_band(pet)
        lx = clampf(self._launch_x, xmin, xmax)
        if self.phase == "walk":
            if (body.on_floor()
                    and abs(body.chunk1.x - lx) <= tuning.PLAN_JUMP_TAKEOFF_EPS):
                body.stop_walk()
                self.phase = "settle"
                return RUNNING
            body.walk_to(lx)
            return RUNNING
        if self.phase == "settle":
            body.stop_walk()
            self._settle += 1
            still = (abs(body.chunk0.vx) < SETTLE_VX
                     and abs(body.chunk1.vx) < SETTLE_VX)
            if body.on_floor() and (still or self._settle > SETTLE_MAX):
                pick = self._pick_at_launch(gx, gy)
                if pick is None:
                    return GIVEUP
                hold, md = pick
                body.request_jump("stand", hold_ticks=hold)
                body.move_dir = md
                self._move_dir = md
                self.phase = "air"
            return RUNNING
        # air
        if not body.on_floor():
            self._airborne = True
            body.move_dir = self._move_dir
        elif self._airborne:
            body.stop_walk()
            return DONE
        return RUNNING

    def _pick_at_launch(self, gx, gy):
        # 起跳时以实际位置重选：先竖直后横弧
        c0 = self.pet.body.chunk0
        stats = self.pet.cat.stats
        for hold in tuning.PLAN_JUMP_HOLD_GEARS:
            if sweep_hit(get_arc(stats, hold, 0),
                         gx - c0.x, gy - c0.y, tuning.GRAB_REACH) is not None:
                return hold, 0
        for md in (1, -1):
            for hold in tuning.PLAN_JUMP_HOLD_GEARS:
                if sweep_hit(get_arc(stats, hold, md),
                             gx - c0.x, gy - c0.y, tuning.GRAB_REACH) is not None:
                    return hold, md
        return None

    def cancel(self):
        self.pet.body.stop_walk()
