"""物理内核：显式速度质点 + 连接约束 + 轴对齐碰撞。坐标系 y↓，常量换算见 core.units。"""
from __future__ import annotations
import math

from .units import K_IMP, K_VEL, clampf, damp60, lerp

RAD0 = 9.0            # chest
RAD1 = 8.0            # hips
MASS = 0.35
DIST_STAND = 17.0
DIST_CRAWL = 17.0

GRAVITY = 0.9 * K_IMP            # y↓
AIR_FRICTION = damp60(0.999)
BOUNCE = 0.1
WEIGHT_SYMMETRY = 0.5
ELASTICITY = 1.0
SURFACE_FRICTION = 0.5
MAX_STRETCH = 1.5    # pinned 端硬上限，rest×此值

STOP_THRESH = (1.0 + 9.0 * (1.0 - BOUNCE)) * K_VEL
TANGENTIAL = min(max(SURFACE_FRICTION * 2.0, 0.0), 1.0)

IMPACT_THRESHOLD = 1.0 * K_VEL
IMPACT_SHAKE_MOMENTUM = 7.0 * K_VEL
IMPACT_STRENGTH_KNEE = 30.0 * K_VEL


def apply_water(obj, water_y, buoyancy: float, water_friction, room_gravity: float,
                air_friction: float, immunity: float = 0.0) -> None:
    """水管线，重力后积分前调用。"""
    r = obj.rad
    sub = 0.0
    if water_y is not None and obj.y + r > water_y:      # 最低点入水
        sub = (obj.y + r - water_y) / (2.0 * r)
        if sub > 1.0:
            sub = 1.0
    if sub <= 0.0:
        obj.vx *= air_friction
        obj.vy *= air_friction
        return
    if obj.vx > -obj.vy * 5.0 and abs(obj.vx) > 10.0 and obj.vy > 0.0 and sub < 0.5:
        obj.vy *= -0.5                                    # 打水漂
        obj.vx *= 0.75
        return
    obj.vy -= buoyancy * room_gravity * sub              # 浮力，y↓取负
    wf = water_friction if water_friction is not None else air_friction
    spd = math.hypot(obj.vx, obj.vy)
    inner = lerp(wf * immunity, wf, (1.0 / max(1.0, spd - 10.0)) ** 0.5)
    k = lerp(air_friction, inner, sub)                   # 空气↔水阻插值
    obj.vx *= k
    obj.vy *= k


class BodyChunk:
    """BodyChunk：显式速度质点 + 圆-墙碰撞。坐标 y 向下。"""
    __slots__ = ("x", "y", "vx", "vy", "last_x", "last_y", "last_last_x", "last_last_y",
                 "rad", "mass", "index", "cx", "cy", "lcx", "lcy", "pinned",
                 "collide_with_objects")

    def __init__(self, index: int, x: float, y: float, rad: float, mass: float):
        self.index = index
        self.x = self.last_x = self.last_last_x = x
        self.y = self.last_y = self.last_last_y = y
        self.vx = self.vy = 0.0
        self.rad = rad
        self.mass = mass
        self.cx = self.cy = 0      # 本帧接触 (±1/0)
        self.lcx = self.lcy = 0    # 上帧接触，边沿检测用
        self.pinned = False        # 外部定位，不积分不撞
        self.collide_with_objects = True   # 通用 chunk 碰撞开关

    @property
    def on_floor(self) -> bool:
        return self.cy == 1     # y↓，+1=着地

    def update(self, W: float, H: float, gravity: float = GRAVITY,
               air_friction: float = AIR_FRICTION, impact=None,
               room_gravity: float = 1.0, water_y=None, buoyancy: float = 1.0,
               water_friction=None, water_immunity: float = 0.0) -> None:
        """推进一帧。"""
        if self.vx != self.vx:
            self.vx = 0.0
        if self.vy != self.vy:
            self.vy = 0.0
        if self.pinned:
            # kinematic，只维护快照
            self.last_last_x, self.last_last_y = self.last_x, self.last_y
            self.last_x, self.last_y = self.x, self.y
            self.lcx, self.lcy = self.cx, self.cy
            self.cx = self.cy = 0
            return
        self.vy += gravity * room_gravity
        apply_water(self, water_y, buoyancy, water_friction, room_gravity, air_friction, water_immunity)
        self.last_last_x, self.last_last_y = self.last_x, self.last_y
        self.last_x, self.last_y = self.x, self.y
        self.x += self.vx
        self.y += self.vy
        self.lcx, self.lcy = self.cx, self.cy
        self.cx = self.cy = 0
        # 碰撞：竖直优先 → 水平
        self._collide(W, H, impact)

    def clamp_inside(self, W: float, H: float) -> None:
        """位置边界夹（安全网）。"""
        if self.pinned:
            return
        r = max(self.rad, 1.0)
        if self.x < r:
            self.x = r
        elif self.x > W - r:
            self.x = W - r
        if self.y < r:
            self.y = r
        elif self.y > H - r:
            self.y = H - r

    def _collide(self, W: float, H: float, impact) -> None:
        r = max(self.rad, 1.0)
        # 竖直优先
        if self.y + r > H and self.vy > 0:
            self.y = H - r
            if self.vy > IMPACT_THRESHOLD and impact is not None:
                _fire_impact(self, (0, 1), abs(self.vy), self.lcy < 1, impact)
            self.cy = 1
            self.vy = -abs(self.vy) * BOUNCE
            if self.vy > -STOP_THRESH:
                self.vy = 0.0
            self.vx *= TANGENTIAL
        elif self.y - r < 0 and self.vy < 0:
            self.y = r
            if -self.vy > IMPACT_THRESHOLD and impact is not None:
                _fire_impact(self, (0, -1), abs(self.vy), self.lcy > -1, impact)
            self.cy = -1
            self.vy = abs(self.vy) * BOUNCE
            if self.vy < STOP_THRESH:
                self.vy = 0.0
            self.vx *= TANGENTIAL
        # 水平其次
        if self.x + r > W and self.vx > 0:
            self.x = W - r
            if self.vx > IMPACT_THRESHOLD and impact is not None:
                _fire_impact(self, (1, 0), abs(self.vx), self.lcx < 1, impact)
            self.cx = 1
            self.vx = -abs(self.vx) * BOUNCE
            if self.vx > -STOP_THRESH:
                self.vx = 0.0
            self.vy *= TANGENTIAL
        elif self.x - r < 0 and self.vx < 0:
            self.x = r
            if -self.vx > IMPACT_THRESHOLD and impact is not None:
                _fire_impact(self, (-1, 0), abs(self.vx), self.lcx > -1, impact)
            self.cx = -1
            self.vx = abs(self.vx) * BOUNCE
            if self.vx < STOP_THRESH:
                self.vx = 0.0
            self.vy *= TANGENTIAL


def _fire_impact(c: BodyChunk, direction, speed: float, first_contact: bool, impact) -> None:
    """地形撞击：首次接触边沿 + 动量超阈值时触发。"""
    if not first_contact:
        return
    momentum = speed * c.mass
    if momentum <= IMPACT_SHAKE_MOMENTUM:
        return
    strength = max((momentum - IMPACT_STRENGTH_KNEE) / 50.0, 0.0)
    ix = direction[0] * momentum * 0.1
    iy = direction[1] * momentum * 0.1
    impact(c, direction, speed, strength, ix, iy)


def solve_conn(a: BodyChunk, b: BodyChunk, rest: float = DIST_STAND,
               wsym: float = WEIGHT_SYMMETRY, elasticity: float = ELASTICITY,
               ctype: str = "Normal", max_stretch: float = MAX_STRETCH) -> None:
    """单遍半隐式约束求解，pinned 端不被推走。"""
    dx, dy = b.x - a.x, b.y - a.y
    d = math.hypot(dx, dy) or 1e-6
    if ctype == "Pull" and not (d > rest):
        return
    if ctype == "Push" and not (d < rest):
        return
    ux, uy = dx / d, dy / d
    corr = (rest - d) * elasticity  # >0 推开，<0 拉拢
    ca = corr * wsym
    cb = corr * (1.0 - wsym)
    ap, bp = a.pinned, b.pinned
    if ap and bp:
        return
    if ap:                                  # a 钉死，b 吃 (1-wsym)
        b.x += ux * cb
        b.y += uy * cb
        b.vx += ux * cb * K_IMP
        b.vy += uy * cb * K_IMP
    elif bp:                                # b 钉死，a 吃 wsym
        a.x -= ux * ca
        a.y -= uy * ca
        a.vx -= ux * ca * K_IMP
        a.vy -= uy * ca * K_IMP
    else:                                   # 都自由，按 wsym 分
        a.x -= ux * ca
        a.y -= uy * ca
        a.vx -= ux * ca * K_IMP
        a.vy -= uy * ca * K_IMP
        b.x += ux * cb
        b.y += uy * cb
        b.vx += ux * cb * K_IMP
        b.vy += uy * cb * K_IMP

    # 硬上限，仅单端 pinned 时触发
    if max_stretch is not None and (ap != bp):
        limit = rest * max_stretch
        dx, dy = b.x - a.x, b.y - a.y
        d = math.hypot(dx, dy)
        if d > limit:
            ux, uy = dx / d, dy / d
            if ap:                          # a 钉死，拉 b 到上限
                b.x = a.x + ux * limit
                b.y = a.y + uy * limit
            else:                           # b 钉死，拉 a
                a.x = b.x - ux * limit
                a.y = b.y - uy * limit


def aabb_wall_collide(obj, WL, HL, impact=None):
    """圆-墙 4 面碰撞，竖直优先。"""
    r = obj.rad
    tang = clampf(obj.surface_friction * 2.0, 0.0, 1.0)   # 切向摩擦
    stop = 1.0 + 9.0 * (1.0 - obj.bounce)                 # 低弹性→高阈值，撞墙即停
    has_ceil = hasattr(obj, "_contact_ceil")
    prev_floor, prev_x = obj._contact_floor, obj._contact_x
    prev_ceil = obj._contact_ceil if has_ceil else False
    obj._contact_floor = False
    obj._contact_x = 0
    if has_ceil:
        obj._contact_ceil = False
    # 竖直优先
    if obj.y + r > HL and obj.vy > 0:
        obj.y = HL - r
        if impact is not None:
            _fire_impact(obj, (0, 1), abs(obj.vy), not prev_floor, impact)
        obj._contact_floor = True
        obj.vy = -abs(obj.vy) * obj.bounce
        if obj.vy > -stop:
            obj.vy = 0.0
        obj.vx *= tang
    elif obj.y - r < 0 and obj.vy < 0:
        obj.y = r
        if impact is not None:
            _fire_impact(obj, (0, -1), abs(obj.vy), not prev_ceil, impact)
        if has_ceil:
            obj._contact_ceil = True
        obj.vy = abs(obj.vy) * obj.bounce
        if obj.vy < stop:
            obj.vy = 0.0
        obj.vx *= tang
    # 水平其次
    if obj.x + r > WL and obj.vx > 0:
        obj.x = WL - r
        if impact is not None:
            _fire_impact(obj, (1, 0), abs(obj.vx), prev_x < 1, impact)
        obj._contact_x = 1
        obj.vx = -abs(obj.vx) * obj.bounce
        if obj.vx > -stop:
            obj.vx = 0.0
        obj.vy *= tang
    elif obj.x - r < 0 and obj.vx < 0:
        obj.x = r
        if impact is not None:
            _fire_impact(obj, (-1, 0), abs(obj.vx), prev_x > -1, impact)
        obj._contact_x = -1
        obj.vx = abs(obj.vx) * obj.bounce
        if obj.vx < stop:
            obj.vx = 0.0
        obj.vy *= tang


def collide_objects(entities) -> None:
    """通用 chunk 碰撞 pass，层 0 不自碰。"""
    buckets: dict[int, list] = {}
    for e in entities:
        layer = e.collision_layer
        if layer == 0:
            continue
        buckets.setdefault(layer, []).append(e)
    for objs in buckets.values():
        n = len(objs)
        if n < 2:
            continue
        groups = [o.collision_chunks() for o in objs]   # 每实体取一次，含本 tick 豁免
        for i in range(n):
            for j in range(i + 1, n):
                _collide_pair(objs[i], objs[j], groups[i], groups[j])


def _collide_pair(a, b, a_chunks, b_chunks) -> None:
    """一对同层实体的 chunk 圆重叠推开。"""
    for ca in a_chunks:
        if not ca.collide_with_objects:
            continue
        for cb in b_chunks:
            if not cb.collide_with_objects:
                continue
            rad_sum = ca.rad + cb.rad
            dx, dy = cb.x - ca.x, cb.y - ca.y
            dist = math.hypot(dx, dy)
            if dist >= rad_sum:
                continue
            if dist < 1e-9:                     # 完全重合，退化取 (0,1)
                ux, uy = 0.0, 1.0
            else:
                ux, uy = dx / dist, dy / dist
            pen = rad_sum - dist                # 穿透深度
            mr = cb.mass / (ca.mass + cb.mass)  # 对方质量占比，轻的位移多
            ax, ay = ux * pen * mr, uy * pen * mr
            bx, by = ux * pen * (1.0 - mr), uy * pen * (1.0 - mr)
            ca.x -= ax; ca.y -= ay; ca.vx -= ax; ca.vy -= ay
            cb.x += bx; cb.y += by; cb.vx += bx; cb.vy += by
            if ca.x == cb.x:                    # 同 x 时加确定性微扰
                ca.vx += 1e-4
                cb.vx -= 1e-4
