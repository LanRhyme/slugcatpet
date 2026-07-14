"""舌取能力：走进射程→射舌粘住→收绳/荡摆/flyby 拉近（机制自 behavior/fetch.py 迁移）。"""
from __future__ import annotations
import math

from ..behavior import tuning
from ..core.units import clampf
from .ability import Ability, Estimate, RUNNING, GIVEUP, reach_assist, walk_band

# 执行机制常量
FETCH_IDEAL = 10.0
FETCH_REEL = 3.0
FLYBY_TRIGGER = 1.4          # 荡摆掠过阈值，触发断舌借势
APPROACH_TIMEOUT = 240
TONGUE_UNDER_TOL = 40.0


def mouth_pos(pet):
    """嘴世界坐标；无 gfx 时以 chunk0 近似。"""
    gfx = getattr(pet, "gfx", None)
    if gfx is not None:
        return gfx.mouth_world()
    c0 = pet.body.chunk0
    return c0.x, c0.y


def reset_tongue(pet, owner=None):
    """收舌 + 恢复默认参数 + 解除悬挂；舌头被他人持有时拒绝（不清舌、不解悬）。"""
    tg = pet.tongue
    if tg is not None:
        if tg.owned_by_other(owner):
            return
        tg.retract()
        tg.reset_config()
    pet.body.suspended = False


def tongue_fire_range(pet):
    return pet.tongue.total * tuning.PLAN_TONGUE_RANGE_FRAC


class TongueReach(Ability):
    key = "tongue"

    def can_touch(self, goal):
        # 取站地估距与实际嘴位距二者更近
        pet = self.pet
        gx, gy = goal.pos()
        rng = tongue_fire_range(pet)
        best = None
        xmin, xmax = walk_band(pet)
        fx = clampf(gx, xmin, xmax)
        d = math.hypot(gx - fx, gy - (pet._HL - tuning.PLAN_MOUTH_H))
        if d <= rng:
            t = (abs(pet.body.chunk1.x - fx) / tuning.PLAN_WALK_SPEED
                 + d / tuning.PLAN_TONGUE_SPEED + tuning.PLAN_STARTUP_TICKS)
            best = Estimate(t, t * tuning.PLAN_EN_RATE_LIGHT)
        mox, moy = mouth_pos(pet)
        dm = math.hypot(gx - mox, gy - moy)
        if dm <= rng:
            t = dm / tuning.PLAN_TONGUE_SPEED + tuning.PLAN_STARTUP_TICKS
            if best is None or t < best.time_est:
                best = Estimate(t, t * tuning.PLAN_EN_RATE_LIGHT)
        return best

    def make_controller(self, goal):
        return TongueApproachController(self.pet, goal)


class TongueApproachController:
    """走进射程→跳跃辅助→射舌→收绳/flyby；超时或到位仍出射程报 giveup。"""

    def __init__(self, pet, goal):
        self.pet = pet
        self.goal = goal
        self.timer = 0
        self._fired = False        # 本控制器是否已射过一发（单发，不原地狂射）

    def update(self):
        pet = self.pet
        body = pet.body
        tg = pet.tongue
        self.timer += 1
        gx, gy = self.goal.pos()
        reach_assist(pet, self.goal, gx, gy)
        mox, moy = mouth_pos(pet)
        c0 = body.chunk0
        xmin, xmax = walk_band(pet)
        fx = clampf(gx, xmin, xmax)
        in_range = math.hypot(gx - mox, gy - moy) <= tongue_fire_range(pet)
        under = abs(body.chunk1.x - fx) <= TONGUE_UNDER_TOL

        if tg.is_idle():
            if self._fired:
                # 已射未粘住 → 交回执行器换方案
                reset_tongue(pet)
                return GIVEUP
            if not (in_range and under):
                # 先走到正下方再射，空中等落地
                if body.on_floor():
                    if under and not in_range:
                        return GIVEUP           # 正下方仍够不到 → 换方案
                    body.walk_to(fx)
                self.timer = 0
                return RUNNING
            body.stop_walk()
            if body.on_floor() and gy < c0.y - tuning.GRAB_REACH:
                body.request_jump("stand")
            if self.goal.obj is not None:
                pet.fire_tongue_at_obj(self.goal.obj)
            else:
                pet.fire_tongue_at(gx, gy)
            self._fired = True
            self.timer = 0
            return RUNNING

        if tg.attached:
            tg.set_targets(ideal=FETCH_IDEAL, reel_rate=FETCH_REEL)
            if self._should_flyby(gx, gy):
                tg.retract()
            elif self.timer > 2 * APPROACH_TIMEOUT:
                reset_tongue(pet)
                return GIVEUP
            return RUNNING

        if self.timer > APPROACH_TIMEOUT:
            reset_tongue(pet)
            return GIVEUP
        return RUNNING

    def _should_flyby(self, gx, gy):
        # 身体荡过目标上方且横向贴近 → 断舌借势
        c0 = self.pet.body.chunk0
        if c0.y >= gy:
            return False
        return abs(c0.x - gx) < tuning.GRAB_REACH * FLYBY_TRIGGER

    def cancel(self):
        reset_tongue(self.pet)
        self.pet.body.stop_walk()
