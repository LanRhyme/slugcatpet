"""果子+Stalk 物理核心；y↓ 坐标；积分顺序 重力→空气阻尼→积分→碰撞。"""
from __future__ import annotations
import math
import random as _random
from ..core.chunkphys import aabb_wall_collide, apply_water
from .enums import ItemState

RAD = 8.0
MASS = 0.2               # 舌头弹簧质量比依赖此值
GRAVITY = 0.9            # y↓
AIR_FRICTION = 0.999
BOUNCE = 0.2
SURFACE_FRICTION = 0.7
BUOYANCY = 1.1           # 浮
WATER_FRICTION = 0.95
BITES = 3

STALK_ANCHOR_Y = -10.0          # 锚点 y，房顶 y=0 之上 10
STALK_SEG_LEN = 15.0
STALK_VEL_DAMP = 0.99
STALK_SEG_GRAV = 0.9           # y↓
STALK_CONN_POW = 1.1
STALK_RELEASE_FACTOR = 1.4
STALK_RELEASE_PAD = 10.0
FRUIT_PULLBACK = 0.25

PLACE_HANGING_FRAC = 0.7


def _dist(ax, ay, bx, by):
    return math.hypot(bx - ax, by - ay)


def _dirvec(ax, ay, bx, by):
    """单位方向 (b-a).normalized；退化 → (0,0)。"""
    dx, dy = bx - ax, by - ay
    d = math.hypot(dx, dy)
    if d < 1e-9:
        return (0.0, 0.0)
    return (dx / d, dy / d)


def _perp(nx, ny):
    """垂向量（y↓ 坐标系）：perp(dx,dy)=(dy,-dx)。"""
    return (ny, -nx)


class Fruit:
    """果子本体：单点物理+状态机；hanging 受 Stalk 约束。"""
    collision_layer = 1              # 与 Saint/黏菌同层互推

    __slots__ = ("x", "y", "vx", "vy", "last_x", "last_y",
                 "rad", "mass", "gravity", "air_friction", "bounce", "surface_friction",
                 "buoyancy", "water_friction", "water_y", "room_gravity",
                 "bites", "state", "rotation", "stalk", "held_by_hand",
                 "collide_with_objects",
                 "_id", "_contact_floor", "_contact_x", "_impact_cb")

    def __init__(self, x: float, y: float, seed: int = 0):
        self.x = self.last_x = float(x)
        self.y = self.last_y = float(y)
        self.vx = 0.0
        self.vy = 0.0
        self.rad = RAD
        self.mass = MASS
        self.gravity = GRAVITY
        self.air_friction = AIR_FRICTION
        self.bounce = BOUNCE
        self.surface_friction = SURFACE_FRICTION
        self.buoyancy = BUOYANCY
        self.water_friction = WATER_FRICTION
        self.water_y = None            # 外部每 tick 注入水面高；None=无水
        self.room_gravity = 1.0
        self.bites = BITES
        self.state = ItemState.FREE
        # rotation：渲染朝向，自由果初始随机
        a = _random.Random(seed).uniform(0.0, math.tau)
        self.rotation = (math.sin(a), -math.cos(a))
        self.stalk: "Stalk | None" = None
        self.held_by_hand: "str | None" = None
        self.collide_with_objects = True
        self._id = int(seed)
        self._contact_floor = False
        self._contact_x = 0           # batfly 用，本体不读
        self._impact_cb = None        # 窗口抖动回调；None=不触发

    @property
    def pos(self):
        return (self.x, self.y)

    def collision_chunks(self):
        """通用碰撞暴露；被抓/拖/吃/消失本 tick 豁免。"""
        self.collide_with_objects = not (
            self.state in (ItemState.CARRIED, ItemState.MOUSE, ItemState.EATEN, ItemState.GONE)
            or self.held_by_hand is not None)
        return (self,)

    def set_rotation_to_grabber(self, gx: float, gy: float) -> None:
        """被抓朝向。"""
        dx, dy = _dirvec(self.x, self.y, gx, gy)
        px, py = _perp(dx, dy)
        # y↓ 取负绝对值，尖朝上
        self.rotation = (px, -abs(py))

    def step(self, WL: float, HL: float) -> None:
        """推进一 tick。"""
        if self.state in (ItemState.CARRIED, ItemState.MOUSE):
            # kinematic：last 由外部存，这里存了会插值硬跳
            self._contact_floor = False
            return

        # 插值基准
        self.last_x, self.last_y = self.x, self.y

        if self.state == ItemState.EATEN:
            return

        # hanging：先推进 Stalk 再积分
        if self.state == ItemState.HANGING and self.stalk is not None:
            detached = self.stalk.step(self)
            if detached:
                self.stalk = None
                if self.state == ItemState.HANGING:
                    self.state = ItemState.FREE

        # 重力→水→积分→碰撞
        self.vy += self.gravity * self.room_gravity
        apply_water(self, self.water_y, self.buoyancy, self.water_friction,
                    self.room_gravity, self.air_friction)
        self.x += self.vx
        self.y += self.vy

        self._collide(WL, HL)

        # 落地：按横速微倾+减速
        if self._contact_floor:
            rx, ry = self.rotation
            px, py = _perp(rx, ry)
            k = 0.1 * self.vx
            nx, ny = rx - px * k, ry - py * k
            d = math.hypot(nx, ny)
            if d > 1e-9:
                self.rotation = (nx / d, ny / d)
            self.vx *= 0.8

    def _collide(self, WL: float, HL: float) -> None:
        """4 面轴对齐墙碰撞，竖直优先。"""
        aabb_wall_collide(self, WL, HL, impact=self._impact_cb)


class Stalk:
    """Verlet 软绳；拴住吊着的果子。step 返回 True=已 detach。"""
    __slots__ = ("stuck_pos", "rope_length", "segs", "conn_rad",
                 "displacements", "release_counter", "_n")

    def __init__(self, fruit: Fruit):
        fx, fy = fruit.x, fruit.y
        self.stuck_pos = (fx, STALK_ANCHOR_Y)
        self.rope_length = abs(self.stuck_pos[1] - fy)
        n = max(1, int(self.rope_length / STALK_SEG_LEN))
        self._n = n
        sx, sy = self.stuck_pos
        # segs[i] = [px,py,last_px,last_py,vx,vy]；初始沿锚点→果子均布
        self.segs = []
        for j in range(n):
            t = (j / (n - 1)) if n > 1 else 0.0
            px = sx + (fx - sx) * t
            py = sy + (fy - sy) * t
            self.segs.append([px, py, px, py, 0.0, 0.0])
        self.conn_rad = self.rope_length / (n ** STALK_CONN_POW)
        # 横向扰动向量，绘制用，seed=果子ID
        rng = _random.Random(fruit._id)
        self.displacements = []
        for _ in range(n):
            a = rng.uniform(0.0, math.tau)
            self.displacements.append((math.sin(a), -math.cos(a)))
        self.release_counter = 0

    def step(self, fruit: Fruit) -> bool:
        """推进一 tick；返回 True=已 detach。"""
        if self.rope_length <= 0:
            return True
        segs = self.segs
        n = self._n

        # 约束求解：正向→反向
        self._connect(True, fruit)
        self._connect(False, fruit)

        # 积分，y↓
        for s in segs:
            s[2], s[3] = s[0], s[1]
            s[0] += s[4]
            s[1] += s[5]
            s[4] *= STALK_VEL_DAMP
            s[5] *= STALK_VEL_DAMP
            s[5] += STALK_SEG_GRAV

        # 约束求解：反向→正向
        self._connect(False, fruit)
        self._connect(True, fruit)

        if self.release_counter > 0:
            self.release_counter -= 1

        # 吊着朝向：果子→末段单位方向
        lx, ly = segs[n - 1][0], segs[n - 1][1]
        rx, ry = _dirvec(fruit.x, fruit.y, lx, ly)
        if rx != 0.0 or ry != 0.0:
            fruit.rotation = (rx, ry)

        # 释放判定：拉锚过远/bites<3/counter==1
        sx, sy = self.stuck_pos
        if (not _dist(fruit.x, fruit.y, sx, sy) < self.rope_length * STALK_RELEASE_FACTOR + STALK_RELEASE_PAD
                or fruit.bites < BITES
                or self.release_counter == 1):
            return True
        return False

    def _connect(self, direction: bool, fruit: Fruit) -> None:
        """约束求解。"""
        segs = self.segs
        n = self._n
        sx, sy = self.stuck_pos
        cr = self.conn_rad

        idx = 0 if direction else (n - 1)
        while 0 <= idx < n:
            s = segs[idx]
            if idx == 0:
                d = _dist(s[0], s[1], sx, sy)
                if not d < cr:
                    ux, uy = _dirvec(s[0], s[1], sx, sy)
                    over = d - cr
                    s[0] += ux * over
                    s[1] += uy * over
                    s[4] += ux * over
                    s[5] += uy * over
            else:
                prev = segs[idx - 1]
                d = _dist(s[0], s[1], prev[0], prev[1])
                if not d < cr:
                    ux, uy = _dirvec(s[0], s[1], prev[0], prev[1])
                    over = d - cr
                    vx, vy = ux * over, uy * over
                    s[0] += vx * 0.5
                    s[1] += vy * 0.5
                    s[4] += vx * 0.5
                    s[5] += vy * 0.5
                    prev[0] -= vx * 0.5
                    prev[1] -= vy * 0.5
                    prev[4] -= vx * 0.5
                    prev[5] -= vy * 0.5
                # 末段兼拉住 fruit
                if idx == n - 1 and fruit is not None:
                    df = _dist(s[0], s[1], fruit.x, fruit.y)
                    if not df < cr:
                        ux, uy = _dirvec(s[0], s[1], fruit.x, fruit.y)
                        over = df - cr
                        vx, vy = ux * over, uy * over
                        s[0] += vx * 0.75
                        s[1] += vy * 0.75
                        s[4] += vx * 0.75
                        s[5] += vy * 0.75
                        fruit.vx -= vx * FRUIT_PULLBACK
                        fruit.vy -= vy * FRUIT_PULLBACK
            idx += 1 if direction else -1

    def points(self):
        """供渲染：中心线点序列（沿 segs 近似）。"""
        pts = [self.stuck_pos]
        for s in self.segs:
            pts.append((s[0], s[1]))
        return pts


def make_fruit(x: float, y: float, HL: float, seed: int = 0, zerog: bool = False) -> Fruit:
    """放置分流：按高度选 free/hanging；无重力恒 free。"""
    f = Fruit(x, y, seed=seed)
    if zerog or y > HL * PLACE_HANGING_FRAC:
        f.state = ItemState.FREE
    else:
        f.state = ItemState.HANGING
        f.stalk = Stalk(f)
    return f
