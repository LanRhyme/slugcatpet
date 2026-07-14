"""后空翻够取（caps.acrobat）：走到起跳点→驻停→boosted backflip_launch 高后空翻弧命中普通跳够不到的高/远目标；落地报 done。"""
from __future__ import annotations

from ..behavior import tuning
from ..core.units import clampf
from .ability import Ability, Estimate, RUNNING, DONE, GIVEUP, reach_assist, walk_band
from .jump_arc import get_arc, get_backflip_arc
from .jump_reach import JumpReach, PLAN_HIT_RADIUS, SETTLE_MAX, SETTLE_VX

TOP_CLEAR = 20.0     # 窗顶余量：高于此线视为被 clamp，弃解


def takeoff_c0_h(stats):
    """站立起跳瞬间 chunk0 距地高（各弧线 sim 同源 settle，取 JumpArc 缓存值）。"""
    return get_arc(stats, 0, 0).takeoff_h


def best_launch_hit(arc, gx, gy, launch_y, xmin, xmax, radius, hipx):
    """定 launch_y，扫掠自由 launch_x 取走+飞最省解；越窗顶余量弃整弧；无解 None。"""
    best = None
    best_t = None
    for i, (px, py) in enumerate(arc.points):
        if launch_y + py < TOP_CLEAR:
            break
        lx = gx - px
        if not (xmin <= lx <= xmax) or abs((launch_y + py) - gy) > radius:
            continue
        t = (abs(hipx - lx) / tuning.PLAN_WALK_SPEED
             + (i + 1) + tuning.PLAN_STARTUP_TICKS)
        if best_t is None or t < best_t:
            best_t = t
            best = (lx, i + 1, t)
    return best


def sweep_hit_topsafe(arc, dx, dy, radius, c0y):
    """扫掠命中 + 窗顶过滤，命中回 tick(1 起)。"""
    r2 = radius * radius
    for i, (px, py) in enumerate(arc.points):
        if c0y + py < TOP_CLEAR:
            return None
        ex, ey = dx - px, dy - py
        if ex * ex + ey * ey <= r2:
            return i + 1
    return None


class BackflipReach(Ability):
    key = "backflip"

    def _plan(self, goal):
        # 泳/零重力退避，普通跳够得着则不翻
        pet = self.pet
        body = pet.body
        if getattr(body, "swimming", False) or getattr(body, "zerog", False):
            return None
        if JumpReach(pet).can_touch(goal) is not None:
            return None
        gx, gy = goal.pos()
        xmin, xmax = walk_band(pet)
        stats = pet.cat.stats
        launch_y = pet._HL - takeoff_c0_h(stats)
        hipx = body.chunk1.x
        best = None
        for d in (1, -1):
            r = best_launch_hit(get_backflip_arc(stats, d, boosted=True), gx, gy,
                                launch_y, xmin, xmax, PLAN_HIT_RADIUS, hipx)
            if r is not None and (best is None or r[2] < best[3]):
                best = (r[0], d, r[1], r[2])
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
        return BackflipReachController(self.pet, goal)


class BackflipReachController:
    """走到起跳 x → 驻停 → 起跳瞬间以实际 chunk0 重选方向 → backflip_launch 持向漂移，落地清态报 done。"""

    def __init__(self, pet, goal):
        self.pet = pet
        self.goal = goal
        self.phase = "walk"
        self._settle = 0
        self._airborne = False
        self._d = 0
        plan = BackflipReach(pet)._plan(goal)
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
                d = self._pick_at_launch(gx, gy)
                if d is None:
                    return GIVEUP
                body.backflip_launch(d, boosted=True)
                self._d = d
                self.phase = "air"
            return RUNNING
        # air
        if not body.on_floor():
            self._airborne = True
            body.move_dir = self._d
        elif self._airborne:
            self._cleanup()
            return DONE
        return RUNNING

    def _pick_at_launch(self, gx, gy):
        # 起跳时以实际位置重选方向
        c0 = self.pet.body.chunk0
        stats = self.pet.cat.stats
        first = 1 if gx >= c0.x else -1
        for d in (first, -first):
            if sweep_hit_topsafe(get_backflip_arc(stats, d, boosted=True), gx - c0.x,
                                 gy - c0.y, tuning.GRAB_REACH, c0.y) is not None:
                return d
        return None

    def _cleanup(self):
        # 非手操路径无 ANIM_RESET 兜底，终止需手动清理
        body = self.pet.body
        body.animation = None
        body.jump_boost = 0.0
        body.stop_walk()
        body.set_posture(True)
        if self._d:
            body.facing = self._d

    def cancel(self):
        self._cleanup()
