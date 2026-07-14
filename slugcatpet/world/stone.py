"""石头物理内核：单点质点，重力积分+碰撞+自旋。"""
from __future__ import annotations
import math
from ..core.chunkphys import aabb_wall_collide, apply_water
from ..core.units import lerp
from .enums import ItemState

RAD = 5.0
MASS = 0.07
GRAVITY = 0.9            # y↓
AIR_FRICTION = 0.999
BOUNCE = 0.4
SURFACE_FRICTION = 0.4
BUOYANCY = 0.4           # 沉，高速打水漂
WATER_FRICTION = 0.98

PEBBLE_FRAMES = 14       # 帧号 Pebble1..14

REST_VEL_EPS = 0.6
EXIT_FLING_SPEED = 8.0   # 脱离投掷阈，同砸晕阈


class Stone:
    """石头：物理质点+自旋+状态机；fling 态高速命中 saint 致晕。"""
    collision_layer = 2              # 与 Saint(层1) 不同层

    __slots__ = ("x", "y", "vx", "vy", "last_x", "last_y",
                 "rad", "mass", "gravity", "air_friction", "bounce", "surface_friction",
                 "buoyancy", "water_friction", "water_y", "room_gravity",
                 "state", "rotation_deg", "last_rotation", "spin", "vibrate", "fling",
                 "thrown_by_saint", "frame", "collide_with_objects",
                 "_id", "_contact_floor", "_contact_ceil", "_contact_x", "_impact_cb",
                 "unfetchable", "fetch_fails")

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
        self.state = ItemState.FREE
        self.rotation_deg = 0.0
        self.last_rotation = 0.0
        self.spin = 0.0
        self.vibrate = 0
        self.fling = False
        self.thrown_by_saint = False
        self.collide_with_objects = True
        self._id = int(seed)
        self.frame = "Pebble" + str(1 + (int(seed) % PEBBLE_FRAMES))
        self._contact_floor = False
        self._contact_ceil = False    # 本 tick 撞顶
        self._contact_x = 0           # batfly 用，本体不读
        self._impact_cb = None        # 窗口抖动回调；None=不触发
        self.unfetchable = False
        self.fetch_fails = 0

    @property
    def pos(self):
        return (self.x, self.y)

    def collision_chunks(self):
        """通用碰撞暴露；拖拽/携带/消失本 tick 豁免。"""
        self.collide_with_objects = self.state not in (
            ItemState.CARRIED, ItemState.MOUSE, ItemState.GONE) and not self.fling
        return (self,)

    def at_rest_on_ground(self, HL: float) -> bool:
        """贴地且基本静止，可作 saint 捡石目标。"""
        return (self.y + self.rad >= HL - 0.5
                and abs(self.vx) < REST_VEL_EPS and abs(self.vy) < REST_VEL_EPS)

    def step(self, WL: float, HL: float) -> None:
        """free：重力积分+碰撞+滚动；mouse/carried：kinematic。"""
        if self.state in (ItemState.MOUSE, ItemState.CARRIED):
            self._contact_floor = False
            return

        self.last_x, self.last_y = self.x, self.y
        self.last_rotation = self.rotation_deg

        if self.state == ItemState.GONE:
            return

        self.rotation_deg += self.spin
        # 重力→水→积分→碰撞
        self.vy += self.gravity * self.room_gravity
        apply_water(self, self.water_y, self.buoyancy, self.water_friction,
                    self.room_gravity, self.air_friction)
        self.x += self.vx
        self.y += self.vy

        self._collide(WL, HL)

        if self._contact_floor or self._contact_ceil:
            self.spin = (self.spin * 2.0 + self.vx * 5.0) / 3.0

        if self.vibrate > 0:
            self.vibrate -= 1

        if (self.fling or self.thrown_by_saint) and (
                self.at_rest_on_ground(HL)
                or math.hypot(self.vx, self.vy) < EXIT_FLING_SPEED):
            self.fling = False
            self.thrown_by_saint = False

    def _collide(self, WL: float, HL: float) -> None:
        """圆-墙碰撞。"""
        aabb_wall_collide(self, WL, HL, impact=self._impact_cb)

    def deflect(self, rng) -> None:
        """命中 saint 后速度变化：半反弹+随机扰动。"""
        v = math.hypot(self.vx, self.vy)
        a = rng.uniform(0.0, math.tau)
        mag = rng.uniform(0.1, 0.4) * v
        self.vx = -0.5 * self.vx + math.cos(a) * mag
        self.vy = -0.5 * self.vy + math.sin(a) * mag
        self.vibrate = 20
        self.spin = rng.uniform(-40.0, 40.0) * lerp(0.05, 1.0, self.room_gravity)
