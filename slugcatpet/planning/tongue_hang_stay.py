"""舌锚吊挂驻留：枚举 {左墙,右墙,天花板,goal实体} 四锚点求最低代价 + 校验驻留位落 radius 圆内；控制器接近→附着→维持。"""
from __future__ import annotations
import math

from ..behavior import tuning
from ..core.chunkphys import DIST_STAND
from ..core.units import clampf
from .ability import Ability, Estimate, RUNNING, GIVEUP, HOLD, walk_band
from .tongue_reach import mouth_pos, reset_tongue

WALL_ARRIVE = 12.0
ATTACH_TIMEOUT = 120
DROP_TIMEOUT = 200
DROP_ALIGN_EPS = 8.0
SETTLE_VX_EPS = 0.35        # 松手前横速门，防被摆荡甩离锚点
SETTLE_DX_EPS = 60.0        # 松手前对准门，防停在摆动端点误判到位
SETTLE_TIMEOUT = 400

# 锚点种类 → 吊挂目标绳长
_IDEALS = {
    "wall_l": tuning.PLAN_HANG_WALL_IDEAL,
    "wall_r": tuning.PLAN_HANG_WALL_IDEAL,
    "ceiling": tuning.PLAN_HANG_CEIL_IDEAL,
    "entity": tuning.PLAN_HANG_BULB_IDEAL,
}


def _anchor_kinds(goal):
    """本 goal 可用锚点种类：实体锚仅当 goal 有底层物体。"""
    kinds = ["wall_l", "wall_r", "ceiling"]
    if goal.obj is not None:
        kinds.append("entity")
    return kinds


def _anchor_coord(pet, goal, kind):
    """锚点世界坐标（逐 tick 从 goal.pos() 重算，跟随活目标）。"""
    gx, gy = goal.pos()
    if kind == "wall_l":
        return (0.0, gy)
    if kind == "wall_r":
        return (pet._WL, gy)
    if kind == "ceiling":
        return (gx, 0.0)
    return (gx, gy)


def _side_for(pet, goal, kind):
    """接近所走的墙侧：墙锚取其墙，天花板/实体锚取近墙。"""
    if kind == "wall_l":
        return -1
    if kind == "wall_r":
        return 1
    gx, _ = goal.pos()
    return -1 if gx < pet._WL * 0.5 else 1


def _settle_dist(pet, goal, kind):
    """吊挂稳定后 chunk1 估算落点到 goal 的距离（落点≈锚点正下方 ideal+体节偏移）。"""
    ax, ay = _anchor_coord(pet, goal, kind)
    sx, sy = ax, ay + _IDEALS[kind] + DIST_STAND
    gx, gy = goal.pos()
    return math.hypot(sx - gx, sy - gy)


def _cost(pet, goal, kind):
    """粗线性代价：走到墙下 + 爬升(+沿顶横移/落体) + 射舌收绳常数。"""
    gx, gy = goal.pos()
    ax, ay = _anchor_coord(pet, goal, kind)
    c0, c1 = pet.body.chunk0, pet.body.chunk1
    xmin, xmax = walk_band(pet)
    attach_t = tuning.PLAN_HANG_ATTACH_TICKS
    en_l, en_v = tuning.PLAN_EN_RATE_LIGHT, tuning.PLAN_EN_RATE_VIGOROUS
    if kind in ("wall_l", "wall_r"):
        walk_t = abs(c1.x - clampf(ax, xmin, xmax)) / tuning.PLAN_WALK_SPEED
        climb_t = max(0.0, c0.y - ay) / tuning.PLAN_CLIMB_SPEED
        t = walk_t + climb_t + attach_t
        e = walk_t * en_l + climb_t * en_v + attach_t * en_l
        return Estimate(t, e)
    wall_x = 0.0 if gx < pet._WL * 0.5 else pet._WL
    walk_t = abs(c1.x - clampf(wall_x, xmin, xmax)) / tuning.PLAN_WALK_SPEED
    climb_t = c0.y / tuning.PLAN_CLIMB_SPEED
    traverse_t = abs(gx - wall_x) / tuning.PLAN_WALK_SPEED
    drop_t = (gy / tuning.PLAN_CLIMB_SPEED) if kind == "entity" else 0.0
    t = walk_t + climb_t + traverse_t + drop_t + attach_t
    e = walk_t * en_l + (climb_t + traverse_t) * en_v + drop_t * en_l + attach_t * en_l
    return Estimate(t, e)


def _best(pet, goal):
    """最低代价的合法锚点：驻留位须落在 radius 圆内。返回 (kind, Estimate) 或 None。"""
    r = goal.radius
    best = None
    for kind in _anchor_kinds(goal):
        if _settle_dist(pet, goal, kind) > r:
            continue
        est = _cost(pet, goal, kind)
        if best is None or est.time_est < best[1].time_est:
            best = (kind, est)
    return best


class TongueHangStay(Ability):
    """舌锚吊挂驻留能力：只答 can_stay（can_touch 恒 None），门禁 caps.tongue。"""
    key = "tonguehang"

    def can_touch(self, goal):
        return None

    def can_stay(self, goal):
        if self.pet.tongue is None:
            return None
        b = _best(self.pet, goal)
        return None if b is None else b[1]

    def make_controller(self, goal):
        return TongueHangController(self.pet, goal)


class TongueHangController:
    """三段：TongueClimber 接近锚点 → 射舌附着收绳 → 返回 HOLD 维持；掉落有限次重爬，超限报 GIVEUP。"""

    def __init__(self, pet, goal):
        self.pet = pet
        self.goal = goal
        b = _best(pet, goal)
        self.kind = b[0] if b is not None else "entity"
        self.side = _side_for(pet, goal, self.kind)
        self.phase = "approach"
        self.climber = None
        self.reclimbs = 0
        self.timer = 0

    def update(self):
        if self.pet.tongue is None:
            return GIVEUP
        ax, ay = _anchor_coord(self.pet, self.goal, self.kind)
        if self.phase == "approach":
            return self._approach(ax, ay)
        if self.phase == "attach":
            return self._attach(ax, ay)
        if self.phase == "settle":
            return self._settle()
        if self.phase == "drop":
            return self._drop()
        return self._hold()

    def _approach(self, ax, ay):
        pet = self.pet
        body = pet.body
        from ..cats.saint.climb import TongueClimber
        if self.climber is None:
            wall_x = pet._WL if self.side > 0 else 0.0
            xmin, xmax = walk_band(pet)
            fx = clampf(wall_x, xmin, xmax)
            if body.on_floor() and abs(body.chunk1.x - fx) > WALL_ARRIVE:
                body.walk_to(fx)
                return RUNNING
            body.stop_walk()
            stop = (self.goal.radius * tuning.PLAN_HANG_WALL_STOP_FRAC
                    if self.kind in ("wall_l", "wall_r") else None)
            self.climber = TongueClimber(pet, self.side, target=(ax, ay), stop_dist=stop)
            return RUNNING
        self.climber.target = (ax, ay)                 # 每 tick 重喂活锚点
        done = self.climber.update()
        if self.climber.giveup:
            reset_tongue(pet)
            self.climber = None
            return self._retry()
        if done:
            self.climber = None
            if self.kind == "ceiling":
                self.phase = "hold"                    # 吊顶已附着，直接维持
            elif self.kind == "entity":
                self.phase = "settle"                  # 先稳住摆荡再松手，否则会被甩离实体锚
                self.timer = 0
            else:
                self.phase = "attach"                  # 墙锚：射舌粘墙点
                self.timer = 0
        return RUNNING

    def _attach(self, ax, ay):
        pet = self.pet
        tg = pet.tongue
        self.timer += 1
        if tg.attached:
            tg.set_targets(ideal=tuning.PLAN_HANG_WALL_IDEAL,
                           reel_rate=tuning.PLAN_HANG_REEL_RATE)
            self.phase = "hold"
            return RUNNING
        if tg.is_idle():
            mox, moy = mouth_pos(pet)
            if math.hypot(ax - mox, ay - moy) <= tg.total:
                tg.set_targets(shoot_v=tuning.PLAN_HANG_SHOOT_V,
                               ideal=tuning.PLAN_HANG_WALL_IDEAL,
                               reel_rate=tuning.PLAN_HANG_REEL_RATE)
                pet.fire_tongue_at(ax, ay)
                return RUNNING
            if pet.body.on_floor():
                return self._retry()
        if self.timer > ATTACH_TIMEOUT:
            return self._retry()
        return RUNNING

    def _settle(self):
        """吊顶悬停等摆荡平息（同时对准+静止）再松手：climber 的 done 只保证锚点对准，不保证猫已稳。"""
        pet = self.pet
        tg = pet.tongue
        body = pet.body
        self.timer += 1
        if not tg.attached:
            return self._retry()
        tg.set_targets(ideal=tuning.PLAN_HANG_CEIL_IDEAL,
                       reel_rate=tuning.PLAN_HANG_REEL_RATE)
        gx, _ = self.goal.pos()
        c0 = body.chunk0
        calm = abs(c0.vx) <= SETTLE_VX_EPS and abs(c0.x - gx) <= SETTLE_DX_EPS
        if calm or self.timer > SETTLE_TIMEOUT:
            reset_tongue(pet)
            body.release_to_air(move_dir=0)
            self.phase = "drop"
            self.timer = 0
        return RUNNING

    def _drop(self):
        pet = self.pet
        tg = pet.tongue
        body = pet.body
        self.timer += 1
        gx, gy = self.goal.pos()
        if tg.attached:
            tg.set_targets(ideal=tuning.PLAN_HANG_BULB_IDEAL,
                           reel_rate=tuning.PLAN_HANG_REEL_RATE)
            self.phase = "hold"
            return RUNNING
        if not body.on_floor():          # 持向修正，防吊顶摆荡横速甩离锚点
            dx = gx - body.chunk0.x
            body.move_dir = 0 if abs(dx) < DROP_ALIGN_EPS else (1 if dx > 0 else -1)
        if tg.is_idle():
            mox, moy = mouth_pos(pet)
            if math.hypot(mox - gx, moy - gy) <= tg.total * 0.95:
                tg.set_targets(shoot_v=tuning.PLAN_HANG_SHOOT_V,
                               ideal=tuning.PLAN_HANG_BULB_IDEAL,
                               reel_rate=tuning.PLAN_HANG_REEL_RATE)
                pet.fire_tongue_at(gx, gy)   # 定点钉，不走双体弹簧（会反拽锚点）
                return RUNNING
            if body.on_floor():
                return self._retry()
        if self.timer > DROP_TIMEOUT:
            return self._retry()
        return RUNNING

    def _hold(self):
        pet = self.pet
        tg = pet.tongue
        if not tg.attached or pet.body.on_floor():     # 姿态丢失 → 重爬
            reset_tongue(pet)
            return self._retry()
        tg.set_targets(ideal=_IDEALS[self.kind],        # 持续维持绳长
                       reel_rate=tuning.PLAN_HANG_REEL_RATE)
        return HOLD

    def _retry(self):
        self.reclimbs += 1
        if self.reclimbs > tuning.PLAN_HANG_MAX_RECLIMB:
            reset_tongue(self.pet)
            self.pet.body.stop_walk()
            return GIVEUP
        self.climber = None
        self.timer = 0
        self.phase = "approach"
        return RUNNING

    def cancel(self):
        reset_tongue(self.pet)
        self.pet.body.stop_walk()
        self.climber = None
