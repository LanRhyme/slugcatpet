"""蝙蝠 batfly 物理核心；y↓。"""
from __future__ import annotations
import math
import random as _random

from ..core.chunkphys import aabb_wall_collide, apply_water
from ..core.units import lerp, inv_lerp, clampf
from .enums import ItemState
from .batfly_gfx import update_render

# 物理常量
RAD, MASS = 6.0, 0.05
GRAVITY = 0.9
AIR_FRICTION, BOUNCE = 0.98, 0.1
SURFACE_FRICTION, SURFACE_FRICTION_DEAD = 0.5, 0.3
WATER_FRICTION, BUOYANCY = 0.9, 0.94
DROWN_RATE = 0.0125
BITES = 3
VEL_DAMP = 0.92
GRAV_FLY_FAC = 0.45
DIR_ACCEL_X = 0.6
FLAP_THRUST_LO, FLAP_THRUST_HI, FLAP_THRUST_POW = 1.1, 1.7, 1.5
FLAPSPEED_DOWN_A, FLAPSPEED_DOWN_B = -0.04, 0.15
FLAPSPEED_UP_A, FLAPSPEED_UP_B = 0.2, 0.8
WALL_REFLECT_X = -6.0
WATER_JUMP = 7.0                                   # y↓ 取负
EATEN_COUNTDOWN = 3

# 游走/力竭/卡住常量
WANDER_REPICK_TICKS, WANDER_REACH, WANDER_MARGIN = 180, 30.0, 24.0
STUCK_DIST, STUCK_TICKS, STUCK_KICK = 40.0, 40, 2.0
EXHAUST_FLAPS, EXHAUST_RECOVER = 34, 12


def _dist(ax, ay, bx, by):
    return math.hypot(bx - ax, by - ay)


def _dirvec(ax, ay, bx, by):
    """单位方向 (b-a).normalized；退化 → (0,0)。"""
    dx, dy = bx - ax, by - ay
    d = math.hypot(dx, dy)
    if d < 1e-9:
        return (0.0, 0.0)
    return (dx / d, dy / d)


def _deg_to_vec(deg):
    """角度转单位向量的 y↓ 镜像：0°=上 (0,-1)。"""
    t = math.radians(deg)
    return (math.sin(t), -math.cos(t))


class BatFly:
    """单 chunk 小飞虫：游走扑翅+力竭挂+手动塞食；接口对齐 Fruit。"""
    collision_layer = 0               # 层0 不参与 collide_objects

    __slots__ = ("x", "y", "vx", "vy", "last_x", "last_y",
                 "rad", "mass", "gravity", "air_friction", "bounce", "surface_friction",
                 "buoyancy", "water_friction", "water_y", "room_gravity", "drown",
                 "_contact_floor", "_contact_x", "_impact_cb",
                 "state", "held_by_hand", "stalk", "bites", "dead", "eaten",
                 "is_meat", "_id", "collide_with_objects",
                 "flap", "flap_speed", "flap_depth", "last_flap_depth", "dir_x", "dir_y",
                 "lower_x", "lower_y", "last_lower_x", "last_lower_y", "lower_vx", "lower_vy",
                 "wings", "_death_wing", "steer", "last_steer", "facing",
                 "rotation", "last_rotation",
                 "goal", "_grounded", "_flaps_since_rest", "_exhausted",
                 "_goal_timer", "_stuck_ref", "_stuck_timer", "_rng")

    def __init__(self, x: float, y: float, seed: int = 0):
        self.x = self.last_x = self.lower_x = self.last_lower_x = float(x)
        self.y = self.last_y = self.lower_y = self.last_lower_y = float(y)
        self.vx = self.vy = self.lower_vx = self.lower_vy = 0.0
        self.rad, self.mass, self.gravity = RAD, MASS, GRAVITY
        self.air_friction, self.bounce = AIR_FRICTION, BOUNCE
        self.surface_friction, self.buoyancy, self.water_friction = SURFACE_FRICTION, BUOYANCY, WATER_FRICTION
        self.water_y = None                # 外部每 tick 注入水面高；None=无水
        self.room_gravity, self.drown = 1.0, 0.0
        self._contact_floor, self._contact_x, self._impact_cb = False, 0, None
        self.state = ItemState.FREE
        self.held_by_hand = None
        self.stalk = None                  # 接口占位，fetcher/carry 读，恒 None
        self.bites, self.dead, self.eaten = BITES, False, 0
        self.is_meat = True                # fetch 食性判定读
        self._id, self.collide_with_objects = int(seed), True
        rng = self._rng = _random.Random(seed)
        self.flap = rng.random()
        self.flap_speed = rng.random() + 0.1
        self.flap_depth = self.last_flap_depth = 0.0
        self.dir_x, self.dir_y = 0.0, -1.0
        f = self.flap
        self.wings = [[f, f], [f, f]]               # [i][0]=今 [i][1]=昨；i=0 左 1 右
        self._death_wing = (rng.random(), rng.random())   # 死亡翅垂随机停位
        self.steer = self.last_steer = 0.0
        self.facing = "right"
        self.rotation = self.last_rotation = (0.0, -1.0)   # 被叼/死态朝向（尖朝上）
        self.goal = (self.x + rng.uniform(-50.0, 50.0), self.y + rng.uniform(-50.0, 50.0))
        self._grounded, self._flaps_since_rest, self._exhausted = False, 0, False
        self._goal_timer, self._stuck_ref, self._stuck_timer = 0, (self.x, self.y), 0

    @property
    def pos(self):
        return (self.x, self.y)

    @property
    def fetch_ready(self):
        # 飞行中够不到，落地/力竭/死亡才可抓
        return (self.state == ItemState.FREE and self.held_by_hand is None
                and (self.dead or self._grounded))

    def collision_chunks(self):
        # 层0 不自碰；被抓/拖/吃/消失本 tick 豁免
        self.collide_with_objects = not (
            self.state in (ItemState.CARRIED, ItemState.MOUSE, ItemState.EATEN, ItemState.GONE)
            or self.held_by_hand is not None)
        return (self,)

    def set_rotation_to_grabber(self, gx: float, gy: float) -> None:
        """被叼朝向；活体尖朝上，死态可侧翻。"""
        self.last_rotation = self.rotation
        dx, dy = _dirvec(self.x, self.y, gx, gy)
        px, py = (dy, -dx)                  # y↓ perp
        self.rotation = (px, py) if self.dead else (px, -abs(py))

    def step(self, WL: float, HL: float) -> None:
        """推进一 tick。"""
        st = self.state
        if st == ItemState.EATEN or st == ItemState.GONE:
            return
        self.last_flap_depth = self.flap_depth
        if st == ItemState.CARRIED:
            self.last_x, self.last_y = self.x, self.y
            if not self.dead and (st == ItemState.CARRIED or self.bites < BITES):
                self.die()                 # 抓起暴毙
            update_render(self, self._submersion())
            self._eaten_countdown()
            return
        if st == ItemState.MOUSE:
            self.last_x, self.last_y = self.x, self.y
            update_render(self, self._submersion())
            self._eaten_countdown()
            return
        # FREE
        self.last_x, self.last_y = self.x, self.y
        sub = self._submersion()
        if not self.dead and sub == 0.0:
            self._batflight()
        else:
            if not self.dead and sub > 0.0:
                self._water_behavior(sub)
            self.vy += self.gravity * self.room_gravity   # 水中/死体全重力，浮力另计
        apply_water(self, self.water_y, self.buoyancy, self.water_friction,
                    self.room_gravity, self.air_friction)
        self.x += self.vx
        self.y += self.vy
        aabb_wall_collide(self, WL, HL, impact=self._impact_cb)
        if not self.dead and self.flap_speed > 0.0 and self._contact_x != 0:
            self.vx = self._contact_x * WALL_REFLECT_X    # 撞侧墙 x 反弹
        self._grounded = self._contact_floor
        if not self.dead:
            self.drown = clampf(self.drown + DROWN_RATE * (1.0 if sub == 1.0 else -1.0), 0.0, 1.0)
            if self.drown >= 1.0:
                self.die()
            self._exhaust()
            self._wander(WL, HL)
        update_render(self, sub)
        if not self.dead and (self.state == ItemState.CARRIED or self.bites < BITES):
            self.die()
        self._eaten_countdown()

    def _submersion(self) -> float:
        """据 water_y/rad 算浸没度；无水恒 0，全浸 1。"""
        if self.water_y is None:
            return 0.0
        s = (self.y + self.rad - self.water_y) / (2.0 * self.rad)
        if s < 0.0:
            return 0.0
        return 1.0 if s > 1.0 else s

    def _batflight(self) -> None:
        """扑翅飞行：一冲一沉朝 goal 游走。"""
        dx, dy = _dirvec(self.x, self.y, self.goal[0], self.goal[1])
        self.dir_x, self.dir_y = dx, dy
        if dx > 0.1:
            self.facing = "right"
        elif dx < -0.1:
            self.facing = "left"
        self.flap_depth = inv_lerp(1.0, -1.0, dy)          # y↓：goal 在上→1
        self.vx *= VEL_DAMP
        self.vy *= VEL_DAMP
        self.vy += self.gravity * self.room_gravity * GRAV_FLY_FAC   # 下坠 +；零重力=0
        self.vx += dx * DIR_ACCEL_X
        self.flap += self.flap_speed
        if self.flap_speed > 0.0:
            if not self._exhausted:                        # 力竭时停上冲，只吃下坠
                self.vy -= (1.0 + self.flap_speed) ** FLAP_THRUST_POW \
                    * lerp(FLAP_THRUST_LO, FLAP_THRUST_HI, self.flap_depth)
            if self.flap > 1.0:
                self.flap = 1.0
                self.flap_speed = FLAPSPEED_DOWN_A - self.flap_depth * FLAPSPEED_DOWN_B
                self._flaps_since_rest += 1                # 完成一个上冲周期
        elif self.flap_speed < 0.0 and self.flap < 0.0:
            self.flap = 0.0
            self.flap_speed = FLAPSPEED_UP_A + self.flap_depth * FLAPSPEED_UP_B

    def _water_behavior(self, sub: float) -> None:
        """落水行为：全浸乱扑，半浸蹦出水面。"""
        if sub == 1.0:
            self.flap = clampf(self.flap + lerp(-1.0, 1.0, self._rng.random()) * 0.1, 0.0, 1.0)
            kx, ky = _deg_to_vec(-45.0 + 90.0 * self._rng.random())
            self.vx += kx * 0.75
            self.vy += ky * 0.75
        elif self.held_by_hand is None:
            self.vy -= WATER_JUMP                          # 蹦出水面（y↓ 取负）

    def _exhaust(self) -> None:
        """力竭：累计扑翅致死（原创机制），触墙回复。"""
        if self._flaps_since_rest >= EXHAUST_FLAPS:
            self._exhausted = True
        if self._exhausted and self._contact_floor and self.room_gravity > 1e-6:
            self.die()                                     # 力竭下坠落地→挂
        elif self._contact_x != 0 or self._contact_floor:
            self._flaps_since_rest = max(0, self._flaps_since_rest - EXHAUST_RECOVER)
            if self._flaps_since_rest == 0:
                self._exhausted = False

    def _wander(self, WL: float, HL: float) -> None:
        """游走：到达/超时重取 goal + 卡住检测。"""
        self._goal_timer += 1
        if (_dist(self.x, self.y, self.goal[0], self.goal[1]) < WANDER_REACH
                or self._goal_timer >= WANDER_REPICK_TICKS):
            self._pick_goal(WL, HL)
        self._stuck_timer += 1
        if self._stuck_timer >= STUCK_TICKS:
            if _dist(self.x, self.y, self._stuck_ref[0], self._stuck_ref[1]) < STUCK_DIST:
                kx, ky = _deg_to_vec(self._rng.random() * 360.0)
                self.vx += kx * STUCK_KICK
                self.vy += ky * STUCK_KICK
            self._stuck_ref = (self.x, self.y)
            self._stuck_timer = 0

    def _pick_goal(self, WL: float, HL: float) -> None:
        """随机屏内落点。"""
        m = WANDER_MARGIN
        self.goal = (self._rng.uniform(m, max(m, WL - m)),
                     self._rng.uniform(m, max(m, HL - m)))
        self._goal_timer = 0

    def _eaten_countdown(self) -> None:
        """被吃倒计时：归零转 EATEN 供剔除。"""
        if self.eaten > 0:
            self.eaten -= 1
            if self.eaten == 0:
                self.state = ItemState.EATEN

    def bite(self) -> bool:
        """手动塞结算，返回 True=可结算食物点。"""
        self.bites -= 1
        if not self.dead:
            self.die()
        if self.bites < 1 and self.eaten == 0:
            self.eaten = EATEN_COUNTDOWN
            return True
        return False

    def die(self) -> None:
        """死亡处理。"""
        self.dead = True
        self.surface_friction = SURFACE_FRICTION_DEAD
