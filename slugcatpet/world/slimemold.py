"""挂黏菌本体物理：单点质点 + 粘边弹簧 + 触须丛；y↓ 坐标。"""
from __future__ import annotations
import math
import random as _random

from ..core.chunkphys import aabb_wall_collide, apply_water
from ..core.units import lerp, inv_lerp
from ..core.gfxmath import _ang_from_up, _rot
from .enums import ItemState

RAD = 5.0
MASS = 0.12
GRAVITY = 0.9            # y↓
AIR_FRICTION = 0.999
BOUNCE = 0.2
SURFACE_FRICTION = 0.7
BUOYANCY = 1.1           # 浮
WATER_FRICTION = 0.95
BITES = 3

STUCK_GAP = 7.0
STUCK_STIFFNESS = 0.2

TENDRIL_MIN = 8
TENDRIL_MAX = 14            # 参考区间 8..15 截断
TENDRIL_REST_MIN = 3.0
TENDRIL_REST_MAX = 8.0
TENDRIL_DAMP = 0.98
TENDRIL_GRAVITY = 0.9       # y↓
ROOT_SPRING = 0.9           # 断口挂本体
LINK_SPRING = 0.5           # 触须间
TENDRIL_RAD = 3.0
TENDRIL_NEAR = 100.0        # 距本体<此才与墙碰
TENDRIL_JAG_K = 20          # 锯齿顶点数


def _dist(ax, ay, bx, by):
    return math.hypot(bx - ax, by - ay)


def _dirvec(ax, ay, bx, by):
    """单位方向 (b-a).normalized；退化 → (0,0)。"""
    dx, dy = bx - ax, by - ay
    d = math.hypot(dx, dy)
    if d < 1e-9:
        return (0.0, 0.0)
    return (dx / d, dy / d)


def _lerp_map(v, in_a, in_b, out_a, out_b):
    """线性重映射：v 从 [in_a,in_b] 映射到 [out_a,out_b]（钳制）。"""
    return lerp(out_a, out_b, inv_lerp(in_a, in_b, v))


class SlimeMold:
    """一坨挂黏菌：单点本体+触须丛；粘边态复用 HANGING。"""
    collision_layer = 1              # 与 Saint/果同层互推

    __slots__ = ("x", "y", "vx", "vy", "last_x", "last_y",
                 "rad", "mass", "gravity", "air_friction", "bounce", "surface_friction",
                 "buoyancy", "water_friction", "water_y", "room_gravity",
                 "bites", "state", "rotation", "last_rotation", "stalk", "held_by_hand",
                 "stuck_pos", "stuck_pos_slime", "tendrils", "tendril_jag",
                 "_tendril_polys", "collide_with_objects",
                 "_id", "_rng", "_contact_floor", "_contact_x", "_impact_cb")

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
        self.rotation = (0.0, 1.0)
        self.last_rotation = self.rotation
        self.stalk = None                 # 接口占位，fetcher/carry 读，恒 None
        self.held_by_hand: "str | None" = None
        self.stuck_pos: "tuple[float, float] | None" = None
        self.collide_with_objects = True
        self._id = int(seed)
        self._contact_floor = False
        self._contact_x = 0           # batfly 用，本体不读
        self._impact_cb = None        # 窗口抖动回调；None=不触发
        # 触须格式：[px,py,lpx,lpy,vx,vy,link,rest,perturb_x,perturb_y,alpha]；link<0 挂本体
        rng = _random.Random(seed)
        count = rng.randint(TENDRIL_MIN, TENDRIL_MAX)
        self.stuck_pos_slime = rng.randrange(0, count)
        self.tendrils = []
        for i in range(count):
            link = -1
            if i != 0 and not (rng.random() < 0.5):
                link = (i - 1) if rng.random() < 0.2 else rng.randrange(0, i)
            rest = lerp(TENDRIL_REST_MIN, TENDRIL_REST_MAX, rng.random())
            a = rng.uniform(0.0, math.tau)
            self.tendrils.append([self.x, self.y, self.x, self.y, 0.0, 0.0,
                                  link, rest, math.cos(a), math.sin(a), rng.random()])
        self._rng = rng
        # 逐根锯齿半径因子，渲染用；种子取 alpha
        self.tendril_jag = []
        for t in self.tendrils:
            jr = _random.Random((int(t[10] * 1_000_003) ^ 0x5A5A5A) & 0xFFFFFFFF)
            self.tendril_jag.append(tuple(0.7 + 0.3 * jr.random()
                                          for _ in range(TENDRIL_JAG_K)))
        self._tendril_polys = None    # 渲染层懒建缓存，形状不变

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
        """被抓朝向；顺带补 last_rotation 供渲染 slerp。"""
        self.last_rotation = self.rotation
        dx, dy = _dirvec(self.x, self.y, gx, gy)
        # y↓ 镜像：perp(dx,dy)=(dy,-dx)，尖朝上取 y=-abs
        self.rotation = (dy, -abs(dx))

    def stick_to(self, sx: float, sy: float) -> None:
        """锚到窗边点。"""
        self.stuck_pos = (float(sx), float(sy))
        ux, uy = _dirvec(self.x, self.y, sx, sy)
        self.rotation = (-ux, -uy)
        self.last_rotation = self.rotation
        self.state = ItemState.HANGING
        self.reset_tendrils()

    def reset_tendrils(self) -> None:
        """触须散布到本体周围（ResetSlime）。"""
        rng = self._rng
        for t in self.tendrils:
            a = rng.uniform(0.0, math.tau)
            r = 4.0 * rng.random()
            t[0] = t[2] = self.x + math.sin(a) * r
            t[1] = t[3] = self.y - math.cos(a) * r
            t[4] = self.vx
            t[5] = self.vy

    def step(self, WL: float, HL: float) -> None:
        """推进一 tick。"""
        if self.state == ItemState.EATEN:
            return
        if self.state in (ItemState.CARRIED, ItemState.MOUSE):
            # kinematic：仅推触须跟随本体
            self._contact_floor = False
            self._step_tendrils(WL, HL)
            return
        self.last_x, self.last_y = self.x, self.y
        self.last_rotation = self.rotation

        # 重力→水→积分→碰撞
        self.vy += self.gravity * self.room_gravity
        apply_water(self, self.water_y, self.buoyancy, self.water_friction,
                    self.room_gravity, self.air_friction)
        self.x += self.vx
        self.y += self.vy
        aabb_wall_collide(self, WL, HL, impact=self._impact_cb)

        self._step_tendrils(WL, HL)

        # 落地：按横速微倾+减速
        if self._contact_floor:
            rx, ry = self.rotation
            px, py = ry, -rx           # y↓ 垂向量（perp 镜像）
            k = 0.1 * self.vx
            nx, ny = rx - px * k, ry - py * k
            d = math.hypot(nx, ny)
            if d > 1e-9:
                self.rotation = (nx / d, ny / d)
            self.vx *= 0.8

        if self.stuck_pos is None:
            return

        # 粘边弹簧：拉向锚点+背墙朝内
        sx, sy = self.stuck_pos
        ux, uy = _dirvec(self.x, self.y, sx, sy)
        dist = _dist(self.x, self.y, sx, sy)
        f = (dist - STUCK_GAP) * STUCK_STIFFNESS
        cvx, cvy = ux * f, uy * f
        self.vx += cvx
        self.vy += cvy
        self.x += cvx
        self.y += cvy
        self.rotation = (-ux, -uy)

        # 钉一根到墙，其余从锚点外推
        pin = self.tendrils[self.stuck_pos_slime]
        pin[0], pin[1] = sx, sy
        pin[4] = pin[5] = 0.0
        for j, t in enumerate(self.tendrils):
            if j == self.stuck_pos_slime:
                continue
            px, py = _dirvec(sx, sy, t[0], t[1])
            push = _lerp_map(_dist(sx, sy, t[0], t[1]), 3.0, 24.0, 6.0, 0.0)
            t[4] += px * push
            t[5] += py * push

    def _step_tendrils(self, WL: float, HL: float) -> None:
        """推进触须物理。"""
        bx, by = self.x, self.y
        rest_k = _lerp_map(self.bites, 3.0, 1.0, 1.0, 0.1)
        rx, ry = self.rotation
        rot_deg = _ang_from_up(rx, ry)
        free = self.stuck_pos is None
        near2 = TENDRIL_NEAR * TENDRIL_NEAR
        r = TENDRIL_RAD
        bnc = self.bounce
        T = self.tendrils
        n = len(T)
        for i in range(n):
            t = T[i]
            t[2], t[3] = t[0], t[1]
            t[0] += t[4]; t[1] += t[5]
            t[4] *= TENDRIL_DAMP; t[5] *= TENDRIL_DAMP
            t[5] += TENDRIL_GRAVITY
            link = t[6]
            if link < 0 or link >= n:
                ux, uy = _dirvec(t[0], t[1], bx, by)
                rest = t[7] * rest_k
                f = (rest - _dist(t[0], t[1], bx, by)) * ROOT_SPRING
                vx, vy = ux * f, uy * f
                t[0] -= vx; t[1] -= vy
                t[4] -= vx; t[5] -= vy
                if free:
                    t[4] -= rx * 2.0; t[5] -= ry * 2.0
            else:
                p = T[link]
                ux, uy = _dirvec(t[0], t[1], p[0], p[1])
                rest = t[7] * rest_k
                f = (rest - _dist(t[0], t[1], p[0], p[1])) * LINK_SPRING
                vx, vy = ux * f, uy * f
                t[0] -= vx; t[1] -= vy
                t[4] -= vx; t[5] -= vy
                p[0] += vx; p[1] += vy
                p[4] += vx; p[5] += vy
                # 扰动力偶：本根+/父根-
                px_f, py_f = _rot(t[8], t[9], rot_deg)
                t[4] += px_f; t[5] += py_f
                p[4] -= px_f; p[5] -= py_f
                if free:
                    sway = _lerp_map(_dist(t[0], t[1], bx, by), 4.0, 12.0, 2.0, 0.0)
                    t[4] -= rx * sway; t[5] -= ry * sway
            # 近本体触须撞窗反弹
            if (t[0] - bx) ** 2 + (t[1] - by) ** 2 < near2:
                if t[1] + r > HL and t[5] > 0:
                    t[1] = HL - r; t[5] = -abs(t[5]) * bnc
                elif t[1] - r < 0 and t[5] < 0:
                    t[1] = r; t[5] = abs(t[5]) * bnc
                if t[0] + r > WL and t[4] > 0:
                    t[0] = WL - r; t[4] = -abs(t[4]) * bnc
                elif t[0] - r < 0 and t[4] < 0:
                    t[0] = r; t[4] = abs(t[4]) * bnc
