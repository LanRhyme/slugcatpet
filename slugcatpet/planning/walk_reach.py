"""走够能力：沿地面走到目标 x；站立臂展内可碰，地面带落 radius 圆内可驻留。"""
from __future__ import annotations
import math

from ..behavior import tuning
from ..core.units import clampf
from .ability import Ability, Estimate, RUNNING, DONE, reach_assist, walk_band


class WalkReach(Ability):
    key = "walk"

    def _plan(self, goal, max_h):
        # 地面带内且高度不超限才可走
        pet = self.pet
        gx, gy = goal.pos()
        floor = pet._HL
        if gy < floor - max_h or gy > floor + tuning.PLAN_FLOOR_TOL:
            return None
        xmin, xmax = walk_band(pet)
        fx = clampf(gx, xmin, xmax)
        if abs(gx - fx) > tuning.PLAN_WALK_X_PAD:
            return None
        t = (abs(pet.body.chunk1.x - fx) / tuning.PLAN_WALK_SPEED
             + tuning.PLAN_STARTUP_TICKS)
        return Estimate(t, t * tuning.PLAN_EN_RATE_LIGHT)

    def can_touch(self, goal):
        return self._plan(goal, tuning.PLAN_STAND_REACH_H)

    def can_stay(self, goal):
        r = goal.radius
        if r <= 0.0:
            return self._plan(goal, tuning.PLAN_FLOOR_TOL)
        return self._plan_radius(goal, r)

    def _plan_radius(self, goal, r):
        # 地面带上找落在 radius 圆内的落脚点
        pet = self.pet
        gx, gy = goal.pos()
        dy = abs(gy - pet._HL)
        if dy > r:
            return None
        half = math.sqrt(r * r - dy * dy)
        xmin, xmax = walk_band(pet)
        fx = clampf(gx, xmin, xmax)
        if abs(gx - fx) > half:
            return None
        t = (abs(pet.body.chunk1.x - fx) / tuning.PLAN_WALK_SPEED
             + tuning.PLAN_STARTUP_TICKS)
        return Estimate(t, t * tuning.PLAN_EN_RATE_LIGHT)

    def make_controller(self, goal):
        return WalkReachController(self.pet, goal)


class WalkReachController:
    """走到目标 x，到位驻留后报 done；近距用 reach_for 探身。"""

    def __init__(self, pet, goal):
        self.pet = pet
        self.goal = goal
        self._hold = 0

    def update(self):
        pet = self.pet
        body = pet.body
        gx, gy = self.goal.pos()
        xmin, xmax = walk_band(pet)
        fx = clampf(gx, xmin, xmax)
        reach_assist(pet, self.goal, gx, gy)
        if body.on_floor() and abs(body.chunk1.x - fx) <= tuning.PLAN_ARRIVE_EPS:
            body.stop_walk()
            self._hold += 1
            return DONE if self._hold >= tuning.PLAN_ARRIVE_HOLD else RUNNING
        self._hold = 0
        body.walk_to(fx)
        return RUNNING

    def cancel(self):
        self.pet.body.stop_walk()
