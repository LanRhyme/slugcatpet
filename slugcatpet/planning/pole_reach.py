"""竖杆够取族（爬杆到指定高度为共用前置）：杆上任意高度 beam jump 斜跳 / 杆顶站立跳直上 / 任意高度松杆落体漂移 / 杆上舌取（Saint）。"""
from __future__ import annotations
import math

from ..behavior import tuning
from ..core.units import clampf
from .ability import Ability, Estimate, RUNNING, DONE, GIVEUP, reach_assist
from .jump_arc import get_arc, get_drop_arc, get_pole_jump_arc, sweep_hit
from .tongue_reach import FETCH_IDEAL, FETCH_REEL, APPROACH_TIMEOUT, reset_tongue

POLE_TIP_C0_H = 17.0        # 杆顶/站立时 chunk0 距顶高
LAUNCH_ARRIVE_EPS = 6.0


def _vpoles(pet):
    """本世界可攀竖杆（无 poles 属性的桩 pet 回落空）。"""
    return [p for p in getattr(pet, "poles", ())
            if getattr(p, "kind", None) == "vertical"]


def _c0_range(pet, pole):
    """杆上 chunk0 可及 y 区间 [顶端高, 近地高]（y↓，顶端 y 最小）。"""
    return (pole.top_y - POLE_TIP_C0_H, pet._HL - POLE_TIP_C0_H)


def _climb_cost_to(pet, pole, hy):
    """走到杆下 + 爬到 chunk0 高 hy 的粗线性 (耗时, 体力)。"""
    walk_t = abs(pet.body.chunk1.x - pole.x) / tuning.PLAN_WALK_SPEED
    climb_t = max(0.0, (pet._HL - POLE_TIP_C0_H) - hy) / tuning.PLAN_CLIMB_SPEED
    return (walk_t + climb_t,
            walk_t * tuning.PLAN_EN_RATE_LIGHT + climb_t * tuning.PLAN_EN_RATE_VIGOROUS)


def _search_height(arc, gx, gy, pole_x, hy_lo, hy_hi, radius, pet, pole):
    """定 launch_x=pole_x、自由 chunk0 发射高 hy∈[hy_lo,hy_hi]：找弧上某点命中的最省 (hy, tick, 爬耗时, 爬体力)。"""
    best = None
    best_c = None
    for i, (px, py) in enumerate(arc.points):
        hy = gy - py                       # 令该采样点竖直正对目标
        if not (hy_lo <= hy <= hy_hi):
            continue
        if abs((pole_x + px) - gx) > radius:
            continue
        ct, ce = _climb_cost_to(pet, pole, hy)
        c = ct + (i + 1)
        if best_c is None or c < best_c:
            best_c = c
            best = (hy, i + 1, ct, ce)
    return best


class _PoleClimb:
    """爬杆到指定高度混入：_step_to_height() 回 running/ready/fail；_drop_pole() 收 PoleClimber。"""

    def _ensure_climber(self):
        if self.climber is None:
            from ..behavior.pole_climb import PoleClimber
            self.climber = PoleClimber(self.pet, self.pole, getattr(self.pet, "rng", None))

    def _step_to_height(self, release_hy, want_tip):
        pet = self.pet
        if self.pole not in getattr(pet, "poles", ()):
            return "fail"
        self._ensure_climber()
        done = self.climber.update(want_dismount=False)
        if self.climber.giveup:
            return "fail"
        phase = self.climber.phase
        if want_tip:
            return "ready" if phase == "tip" else ("fail" if done else "running")
        # 中途高度：须已抓上杆（phase climb/tip）且 chunk0 爬到发射高
        if phase in ("climb", "tip") and pet.body.chunk0.y <= release_hy + LAUNCH_ARRIVE_EPS:
            return "ready"
        if phase == "tip":                 # 到顶仍没到（目标比顶高，不该发生）→ 就用顶
            return "ready"
        return "fail" if done else "running"

    def _drop_pole(self):
        if self.climber is not None:
            self.climber.release()
            self.climber = None


# 杆上跳
class PoleJumpReach(Ability):
    key = "polejump"

    def _plan(self, goal):
        pet = self.pet
        gx, gy = goal.pos()
        stats = pet.cat.stats
        best = None
        best_t = None

        def consider(pole, kind, params, hy, t, e):
            nonlocal best, best_t
            if best_t is None or t < best_t:
                best_t = t
                best = (pole, kind, params, hy, t, e)

        for pole in _vpoles(pet):
            hy_lo, hy_hi = _c0_range(pet, pole)
            tip_c0y = hy_lo
            # 杆顶站立跳：竖直优先，再左右横弧
            ct, ce = _climb_cost_to(pet, pole, tip_c0y)
            for md in (0, 1, -1):
                done = False
                for hold in tuning.PLAN_JUMP_HOLD_GEARS:
                    hit = sweep_hit(get_arc(stats, hold, md), gx - pole.x,
                                    gy - tip_c0y, tuning.GRAB_REACH)
                    if hit is not None:
                        consider(pole, "tip", (hold, md), tip_c0y,
                                 ct + hit + tuning.PLAN_STARTUP_TICKS,
                                 ce + hit * tuning.PLAN_EN_RATE_VIGOROUS)
                        done = True
                        break
                if done:
                    break
            # 任意高度 beam jump（左右）：搜发射高度
            for d in (1, -1):
                r = _search_height(get_pole_jump_arc(stats, d), gx, gy, pole.x,
                                   hy_lo, hy_hi, tuning.GRAB_REACH, pet, pole)
                if r is not None:
                    hy, hit, ct2, ce2 = r
                    consider(pole, "beam", (d,), hy,
                             ct2 + hit + tuning.PLAN_STARTUP_TICKS,
                             ce2 + hit * tuning.PLAN_EN_RATE_VIGOROUS)
        return best

    def can_touch(self, goal):
        plan = self._plan(goal)
        if plan is None:
            return None
        return Estimate(plan[4], plan[5])

    def make_controller(self, goal):
        return PoleLaunchController(self.pet, goal, self._plan(goal))


# 杆上松杆落体漂移
class PoleDropReach(Ability):
    key = "poledrop"

    def _plan(self, goal):
        pet = self.pet
        gx, gy = goal.pos()
        stats = pet.cat.stats
        best = None
        best_t = None
        for pole in _vpoles(pet):
            hy_lo, hy_hi = _c0_range(pet, pole)
            for md in (0, 1, -1):
                r = _search_height(get_drop_arc(stats, md), gx, gy, pole.x,
                                   hy_lo, hy_hi, tuning.GRAB_REACH, pet, pole)
                if r is not None:
                    hy, hit, ct, ce = r
                    t = ct + hit + tuning.PLAN_STARTUP_TICKS
                    if best_t is None or t < best_t:
                        best_t = t
                        best = (pole, "drop", (md,), hy, t,
                                ce + hit * tuning.PLAN_EN_RATE_LIGHT)
        return best

    def can_touch(self, goal):
        plan = self._plan(goal)
        if plan is None:
            return None
        return Estimate(plan[4], plan[5])

    def make_controller(self, goal):
        return PoleLaunchController(self.pet, goal, self._plan(goal))


class PoleLaunchController(_PoleClimb):
    """爬杆到发射高度 → 按 kind 起跳/落体（tip=杆顶站立跳、beam=竖杆跳、drop=松杆落体）→ 持向探身/漂移，落地报 done。"""

    def __init__(self, pet, goal, plan):
        self.pet = pet
        self.goal = goal
        self.plan = plan
        self.pole = plan[0] if plan else None
        self.kind = plan[1] if plan else None
        self.params = plan[2] if plan else None
        self.release_hy = plan[3] if plan else None
        self.climber = None
        self.phase = "climb"
        self._airborne = False
        self._md = 0

    def update(self):
        pet = self.pet
        body = pet.body
        gx, gy = self.goal.pos()
        if self.pole is None:
            return GIVEUP
        if self.phase == "climb":
            reach_assist(pet, self.goal, gx, gy)
            st = self._step_to_height(self.release_hy, want_tip=(self.kind == "tip"))
            if st == "fail":
                return GIVEUP
            if st == "ready":
                self.phase = "launch"
            return RUNNING
        if self.phase == "launch":
            self._drop_pole()
            if self.kind == "tip":
                hold, md = self._pick_tip(gx, gy)
                body.tip_launch(hold_ticks=hold, move_dir=md)
                self._md = md
            elif self.kind == "beam":
                d = self.params[0]
                body.pole_jump(d)
                self._md = d
            else:
                md = self.params[0]
                body.release_to_air(move_dir=md)
                self._md = md
            self.phase = "air"
            return RUNNING
        # air
        reach_assist(pet, self.goal, gx, gy)
        if not body.on_floor():
            self._airborne = True
            body.move_dir = self._md
        elif self._airborne:
            body.stop_walk()
            return DONE
        return RUNNING

    def _pick_tip(self, gx, gy):
        # 起跳时以实际位置重选，无命中回落原计划
        c0 = self.pet.body.chunk0
        stats = self.pet.cat.stats
        for md in (0, 1, -1):
            for hold in tuning.PLAN_JUMP_HOLD_GEARS:
                if sweep_hit(get_arc(stats, hold, md), gx - c0.x, gy - c0.y,
                             tuning.GRAB_REACH) is not None:
                    return hold, md
        return self.params

    def cancel(self):
        self._drop_pole()
        self.pet.body.stop_walk()


# 杆上舌取（Saint）
class PoleTongueReach(Ability):
    key = "poletongue"

    def _plan(self, goal):
        pet = self.pet
        tg = pet.tongue
        if tg is None:
            return None
        gx, gy = goal.pos()
        rng = tg.total * tuning.PLAN_TONGUE_RANGE_FRAC
        best = None
        best_t = None
        for pole in _vpoles(pet):
            hy_lo, hy_hi = _c0_range(pet, pole)
            hy = clampf(gy, hy_lo, hy_hi)          # 贴目标高度最省舌
            d = math.hypot(gx - pole.x, gy - hy)
            if d <= rng:
                ct, ce = _climb_cost_to(pet, pole, hy)
                t = ct + d / tuning.PLAN_TONGUE_SPEED + tuning.PLAN_STARTUP_TICKS
                if best_t is None or t < best_t:
                    best_t = t
                    best = (pole, hy, Estimate(t, ce + (d / tuning.PLAN_TONGUE_SPEED)
                                               * tuning.PLAN_EN_RATE_LIGHT))
        return best

    def can_touch(self, goal):
        plan = self._plan(goal)
        return plan[2] if plan is not None else None

    def make_controller(self, goal):
        plan = self._plan(goal)
        return PoleTongueController(self.pet, goal,
                                    plan[0] if plan else None,
                                    plan[1] if plan else None)


class PoleTongueController(_PoleClimb):
    """爬杆到目标同高 → 松杆射舌粘果收绳，消费方查抓取即终止；落空/超时报 giveup。"""

    def __init__(self, pet, goal, pole, release_hy):
        self.pet = pet
        self.goal = goal
        self.pole = pole
        self.release_hy = release_hy
        self.climber = None
        self.phase = "climb"
        self.timer = 0

    def update(self):
        pet = self.pet
        gx, gy = self.goal.pos()
        if self.pole is None:
            return GIVEUP
        reach_assist(pet, self.goal, gx, gy)
        if self.phase == "climb":
            tip_c0y = self.pole.top_y - POLE_TIP_C0_H
            st = self._step_to_height(self.release_hy,
                                      want_tip=(self.release_hy <= tip_c0y + LAUNCH_ARRIVE_EPS))
            if st == "fail":
                return GIVEUP
            if st == "ready":
                self._drop_pole()
                pet.body.release_to_air(move_dir=0)   # 松杆，靠舌把身/果收拢
                self.phase = "fire"
            return RUNNING
        tg = pet.tongue
        if self.phase == "fire":
            if tg is None:
                return GIVEUP
            if tg.is_idle():
                if self.goal.obj is not None:
                    pet.fire_tongue_at_obj(self.goal.obj)
                else:
                    pet.fire_tongue_at(gx, gy)
                self.phase = "reel"
                self.timer = 0
            return RUNNING
        # reel
        self.timer += 1
        if tg.attached:
            tg.set_targets(ideal=FETCH_IDEAL, reel_rate=FETCH_REEL)
            if self.timer > 2 * APPROACH_TIMEOUT:
                reset_tongue(pet)
                return GIVEUP
            return RUNNING
        if self.timer > APPROACH_TIMEOUT:
            reset_tongue(pet)
            return GIVEUP
        return RUNNING

    def cancel(self):
        self._drop_pole()
        reset_tongue(self.pet)
        self.pet.body.stop_walk()
