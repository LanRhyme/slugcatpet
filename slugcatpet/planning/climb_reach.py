"""爬墙辅助舌取能力：走到近墙→TongueClimber 拉升缩距→入射程转舌取。"""
from __future__ import annotations
import math

from ..behavior import tuning
from ..core.units import clampf
from .ability import Ability, Estimate, RUNNING, GIVEUP, walk_band
from .tongue_reach import (TongueApproachController, mouth_pos, reset_tongue,
                           tongue_fire_range)

CLIMB_ASSIST_MAX = 600
WALL_ARRIVE = 12.0


class ClimbReach(Ability):
    key = "climb"

    def can_touch(self, goal):
        # 两侧墙各求可达高度，取更省的
        pet = self.pet
        gx, gy = goal.pos()
        floor = pet._HL
        rng = tongue_fire_range(pet)
        xmin, xmax = walk_band(pet)
        best = None
        for wall_x in (0.0, pet._WL):
            dxw = abs(gx - wall_x)
            if dxw > rng:
                continue
            spread = math.sqrt(rng * rng - dxw * dxw)
            y_need = clampf(gy + spread, 0.0, floor)
            climb_t = max(0.0, pet.body.chunk0.y - y_need) / tuning.PLAN_CLIMB_SPEED
            walk_t = (abs(pet.body.chunk1.x - clampf(wall_x, xmin, xmax))
                      / tuning.PLAN_WALK_SPEED)
            light_t = (walk_t + dxw / tuning.PLAN_TONGUE_SPEED
                       + 2.0 * tuning.PLAN_STARTUP_TICKS)
            t = light_t + climb_t
            e = (light_t * tuning.PLAN_EN_RATE_LIGHT
                 + climb_t * tuning.PLAN_EN_RATE_VIGOROUS)
            if best is None or t < best.time_est:
                best = Estimate(t, e)
        return best

    def make_controller(self, goal):
        return ClimbAssistController(self.pet, goal)


class ClimbAssistController:
    """三段：走墙下→爬升缩距→入射程转舌取（swing/reel 复用舌取控制器）。"""

    def __init__(self, pet, goal):
        self.pet = pet
        self.goal = goal
        self.timer = 0
        self._climber = None
        self._lick = None
        gx, _ = goal.pos()
        self._side = 1 if gx >= pet._WL * 0.5 else -1

    def update(self):
        pet = self.pet
        body = pet.body
        self.timer += 1
        if self._lick is not None:
            return self._lick.update()

        gx, gy = self.goal.pos()
        mox, moy = mouth_pos(pet)
        if math.hypot(gx - mox, gy - moy) <= tongue_fire_range(pet):
            # 入射程：停爬转舌取
            reset_tongue(pet)
            self._climber = None
            self._lick = TongueApproachController(pet, self.goal)
            return RUNNING
        if self.timer > CLIMB_ASSIST_MAX:
            reset_tongue(pet)
            return GIVEUP

        c0 = body.chunk0
        wall_x = body.walk_max if self._side > 0 else body.walk_min
        if wall_x is None:
            wall_x = pet._WL if self._side > 0 else 0.0

        if self._climber is None:
            if body.on_floor() and abs(c0.x - wall_x) > WALL_ARRIVE:
                body.walk_to(wall_x)
                return RUNNING
            body.stop_walk()
            from ..cats.saint.climb import TongueClimber
            self._climber = TongueClimber(pet, self._side)
            return RUNNING

        self._climber.update()
        if self._climber.giveup:
            reset_tongue(pet)
            return GIVEUP
        return RUNNING

    def cancel(self):
        reset_tongue(self.pet)
        self.pet.body.stop_walk()
