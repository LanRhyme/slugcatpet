"""工匠爆跳够取（caps.pyro）：普通起跳腾空第 PYRO_BOOST_AIR_TICKS tick 爆冲命中远/高目标；近目标或普通跳更省时不参赛。"""
from __future__ import annotations
import math

from ..behavior import tuning
from ..cats.artificer import pyro
from ..core.units import clampf
from .ability import Ability, Estimate, RUNNING, DONE, GIVEUP, reach_assist, walk_band
from .backflip_reach import (SETTLE_MAX, SETTLE_VX, best_launch_hit,
                             sweep_hit_topsafe, takeoff_c0_h)
from .jump_arc import get_pyro_arc, PYRO_INPUTS
from .jump_reach import JumpReach, PLAN_HIT_RADIUS

_VARIANTS = ("vert", "side+", "side-", "diag+", "diag-")


def _fuel_ok(pet, body):
    """AI 发射门（不自爆铁律）：counter + 本次成本 1 ≤ pyro_heat_cap。"""
    pyro.ensure(body)
    return body._ctrl_pyro_counter + 1 <= pet.cat.tuning["pyro_heat_cap"]


class PyroJumpReach(Ability):
    key = "pyrojump"

    def _plan(self, goal):
        # 泳/零重力/燃料/最小距离门禁，普通跳更省则退赛
        pet = self.pet
        body = pet.body
        if getattr(body, "swimming", False) or getattr(body, "zerog", False):
            return None
        if not _fuel_ok(pet, body):
            return None
        gx, gy = goal.pos()
        hip = body.chunk1
        if math.hypot(gx - hip.x, gy - hip.y) < tuning.PYRO_REACH_MIN_DX:
            return None
        xmin, xmax = walk_band(pet)
        stats = pet.cat.stats
        launch_y = pet._HL - takeoff_c0_h(stats)
        best = None
        for v in _VARIANTS:
            r = best_launch_hit(get_pyro_arc(stats, v), gx, gy, launch_y,
                                xmin, xmax, PLAN_HIT_RADIUS, hip.x)
            if r is not None and (best is None or r[2] < best[3]):
                best = (r[0], v, r[1], r[2])
        if best is None:
            return None
        jump_est = JumpReach(pet).can_touch(goal)
        if jump_est is not None and jump_est.time_est <= best[3]:
            return None
        return best

    def can_touch(self, goal):
        plan = self._plan(goal)
        if plan is None:
            return None
        _, _, hit, t = plan
        walk_t = t - hit - tuning.PLAN_STARTUP_TICKS
        return Estimate(t, walk_t * tuning.PLAN_EN_RATE_LIGHT
                        + hit * tuning.PLAN_EN_RATE_VIGOROUS)

    def make_controller(self, goal):
        return PyroJumpReachController(self.pet, goal)


class PyroJumpReachController:
    """走到起跳 x → 驻停（实位重选变体）→ 普通起跳 → 腾空第 PYRO_BOOST_AIR_TICKS tick 过燃料门爆冲，落地清态报 done。"""

    def __init__(self, pet, goal):
        self.pet = pet
        self.goal = goal
        self.phase = "walk"
        self._settle = 0
        self._air = 0
        self._fired = False
        self._airborne = False
        plan = PyroJumpReach(pet)._plan(goal)
        self._launch_x = plan[0] if plan is not None else None
        self._variant = plan[1] if plan is not None else None

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
                v = self._pick_at_launch(gx, gy)
                if v is None:
                    return GIVEUP              # 尚未起跳无脏态，不白耗燃料照爆
                self._variant = v
                body.request_jump("stand")
                self.phase = "air"
            return RUNNING
        # 腾空计 tick，过燃料门后 fire_air_jump
        if not body.on_floor():
            self._airborne = True
            self._air += 1
            if not self._fired and self._air >= tuning.PYRO_BOOST_AIR_TICKS:
                self._fired = True
                if _fuel_ok(pet, body):
                    ix, iy = PYRO_INPUTS[self._variant]
                    pyro.fire_air_jump(pet, body, ix, iy)
        elif self._airborne:
            self._cleanup()
            return DONE
        return RUNNING

    def _pick_at_launch(self, gx, gy):
        # 起跳时以实际位置重选变体
        c0 = self.pet.body.chunk0
        stats = self.pet.cat.stats
        order = (self._variant,) + tuple(v for v in _VARIANTS if v != self._variant)
        for v in order:
            if sweep_hit_topsafe(get_pyro_arc(stats, v), gx - c0.x,
                                 gy - c0.y, tuning.GRAB_REACH, c0.y) is not None:
                return v
        return None

    def _cleanup(self):
        # 非手操路径无 ANIM_RESET 兜底，终止需手动清理
        body = self.pet.body
        body.animation = None
        body.jump_boost = 0.0
        body.stop_walk()
        body.set_posture(True)
        if self._variant is not None:
            ix = PYRO_INPUTS[self._variant][0]
            if ix:
                body.facing = ix

    def cancel(self):
        self._cleanup()
