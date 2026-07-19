"""SlugcatGraphics：sprites 由代码定义，每帧从物理算位姿 / 帧 / 色。"""
from __future__ import annotations
import math
import re

from ..core.units import K_VEL, K_IMP, damp60, clampf, inv_lerp
from ..core.gfxmath import (_hsl2rgb, _ang_from_up, _rot, _lerp, _catmull,
                           SHOULDER_OFF_X, SHOULDER_OFF_Y, ARM_DIV, ARM_MAX,
                           TAIL_RAD, TONGUE_WIDTH_SCALE)

# head 骨参数
HEAD_AIR = damp60(0.99)
HEAD_CONNECT_RAD = 3.0
HEAD_ELASTIC = 0.2 * K_IMP
HEAD_ADAPT_RETAIN = 0.3
HEAD_EXAGGERATE = 0.1
HEAD_TARGET_LERP = 0.20
HEAD_PRELEAD = 3.0

LEGS_AIR = HEAD_AIR
LEGS_CONNECT_RAD = 4.0
LEGS_ELASTIC = 0.25 * K_IMP
LEGS_ADAPT_RETAIN = 0.5
LEGS_EXAGGERATE = 0.1
LEGS_HOST_Y = 10.0 * K_VEL

HUNT_SPEED = 7.0 * K_VEL
HAND_QUICKNESS = 0.5
SHOULDER_RAD = 20.0

# Crawl 前进手
CRAWL_HUNT_SPEED = 12.0
CRAWL_QUICKNESS = 0.7

# arm_aim 缺字段回退
_NO_ARM_AIM = {"l": None, "r": None}

SLEEP_CURL_RATE = 0.01 * K_VEL
GILLS_FLAT_RATE = 0.08 * K_VEL
BLINK_MIN, BLINK_MAX = 2, 1800   # 自驱 blink 间隔（tick）

# 寒冷发白
_COLD_ICY = (0.8, 0.8, 1.0)


def _lerp3(a, b, t):
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return (a[0] + (b[0] - a[0]) * t,
            a[1] + (b[1] - a[1]) * t,
            a[2] + (b[2] - a[2]) * t)


def _cold_blend(old01, hyp):
    """冷度染色，上限不发紫。"""
    b = _lerp3(old01, _COLD_ICY, hyp)
    return _lerp3(old01, b, 0.92)

LOOK_LEAN_VCAP = 0.10       # 竖直 body-lean 上限



from ..rendering.graphics_draw import GraphicsDrawMixin
from ..behavior import tuning
from ..cats import default_def


class GenericBone:
    """质点骨。"""
    __slots__ = ("x", "y", "vx", "vy", "lx", "ly", "pinned")

    def __init__(self, x, y):
        self.x = self.lx = x
        self.y = self.ly = y
        self.vx = self.vy = 0.0
        self.pinned = False

    def update(self, air=HEAD_AIR):
        self.lx, self.ly = self.x, self.y
        self.x += self.vx
        self.y += self.vy
        self.vx *= air
        self.vy *= air

    def connect_to_point(self, px, py, host_vx, host_vy,
                         connect_rad=HEAD_CONNECT_RAD, elastic=HEAD_ELASTIC,
                         adapt_retain=HEAD_ADAPT_RETAIN, exaggerate=HEAD_EXAGGERATE):
        # 弹性拉向点 + 阻尼拴绳
        dx, dy = px - self.x, py - self.y
        if elastic > 0:
            self.vx += dx * elastic
            self.vy += dy * elastic
        self.vx += host_vx * exaggerate
        self.vy += host_vy * exaggerate
        d = math.hypot(dx, dy)
        if d > connect_rad and d > 1e-6:
            ux, uy = dx / d, dy / d
            corr = connect_rad - d
            vecx, vecy = ux * corr, uy * corr
            self.x -= vecx
            self.y -= vecy
            self.vx -= vecx
            self.vy -= vecy
        self.vx = host_vx + (self.vx - host_vx) * adapt_retain
        self.vy = host_vy + (self.vy - host_vy) * adapt_retain


class HeadBone(GenericBone):
    """头部骨。"""


class Hand:
    """手：Retracted / HuntAbsolutePosition 两态机。"""
    __slots__ = ("x", "y", "lx", "ly", "vx", "vy", "j", "active",
                 "retract_counter", "mode", "reached")

    def __init__(self, sx, sy, j):
        self.x = self.lx = sx
        self.y = self.ly = sy
        self.vx = self.vy = 0.0
        self.j = j
        self.active = False
        self.retract_counter = 0
        self.mode = "Retracted"
        self.reached = True

    def update(self, sx, sy, target, speed=HUNT_SPEED, quickness=HAND_QUICKNESS):
        """sx,sy=肩点；target=绝对目标或 None（收回）。"""
        self.lx, self.ly = self.x, self.y

        if target is not None:
            retracting = False
            self.mode = "HuntAbsolutePosition"
            self.active = True
        else:
            retracting = True
            self.active = False

        hunt_target = target

        if retracting and self.mode != "Retracted":
            self.retract_counter += 1
            if self.retract_counter > 5:
                self.mode = "HuntAbsolutePosition"
                k = min(1.0, (self.retract_counter - 5) * 0.05)
                self.x += (sx - self.x) * k
                self.y += (sy - self.y) * k
                speed = 1.0 + self.retract_counter * 0.2
                quickness = 1.0
                hunt_target = (sx, sy)
                if math.hypot(self.x - sx, self.y - sy) < 2.0 and self.reached:
                    self.mode = "Retracted"
        else:
            self.retract_counter -= 10
            if self.retract_counter < 0:
                self.retract_counter = 0

        if self.mode == "Retracted":
            self.vx = 0.0
            self.vy = 0.0
            self.x = sx
            self.y = sy
            self.reached = True
        elif self.mode == "HuntAbsolutePosition":
            if hunt_target is not None:
                tx, ty = hunt_target
                dx, dy = tx - self.x, ty - self.y
                d = math.hypot(dx, dy)
                if d < speed:
                    self.vx, self.vy = dx, dy
                    self.reached = True
                else:
                    ux, uy = dx / d, dy / d
                    self.vx += (ux * speed - self.vx) * quickness
                    self.vy += (uy * speed - self.vy) * quickness
                    self.reached = False
                self.x += self.vx
                self.y += self.vy
        if self.mode != "Retracted":
            sdx, sdy = sx - self.x, sy - self.y
            sd = math.hypot(sdx, sdy)
            if sd > SHOULDER_RAD and sd > 1e-6:
                ux, uy = sdx / sd, sdy / sd
                corr = SHOULDER_RAD - sd
                self.x -= ux * corr
                self.y -= uy * corr
                self.vx -= ux * corr
                self.vy -= uy * corr


class SlugcatGraphics(GraphicsDrawMixin):
    """sprites 由代码算位姿/帧/色，体色眼色来自 CatDef。"""

    def __init__(self, body, layout=None, atlas=None, cat=None):
        self.body = body
        self.L = layout
        self.atlas = atlas
        self.cat = cat or default_def()
        self.BODY = tuple(self.cat.body_color)
        self.EYE = tuple(self.cat.eye_color)

        # petunit 构建后注入：tail_segs/tongue
        self.tail_segs = None
        self.tongue = None
        self.gills = None            # 仅 caps.gills 猫非空

        self.tail_smooth = True
        self.tail_smooth_subdiv = 4

        c0, c1 = body.chunk0, body.chunk1
        self.head = HeadBone(c0.x, c0.y - HEAD_PRELEAD)
        self.legs = GenericBone(c1.x, c1.y + 2.0)
        self.legs_dir = [0.0, 1.0]
        self.hands = [Hand(c0.x - 1, c0.y, 0), Hand(c0.x + 1, c0.y, 1)]
        self.hand_aim = {"l": None, "r": None}

        self.draw0 = [c0.x, c0.y]
        self.draw1 = [c1.x, c1.y]
        self._last_draw0 = list(self.draw0)
        self._last_draw1 = list(self.draw1)

        self.look_at = None
        self.look_dir = (0.0, 0.0)
        self.sleeping = False
        self.sleep_curl = 0.0
        self.gills_flat = 0.0          # 1=鳃锚退回世界水平（趴/睡）
        self.dead = False
        self.stunned = False           # 晕脸 + 头帧0耷拉
        self.blink = 0
        self._blink_rng = _Rng(12345)
        self._shiver_rng = _Rng(0xC01D)        # 发抖用，独立于 blink
        self.anim_frame = 0
        self.disbalance = 0.0
        self.balance_counter = 0.0
        self.last_look_dir = (0.0, 0.0)
        self.head_angle = 0.0
        self.head_frame_override = None
        self.face_angle = 0.0
        self.face_scale_x = 1.0
        self.face_offset = (0.0, 2.0)

        fam = self.cat.frames
        self._head_frames = self._family_frames(*fam["head"])
        self._face_frames = self._family_frames(*fam["face"])
        self._face_blink_frames = self._family_frames(*fam["face_blink"])
        self._face_a_frames = (self._family_frames(*fam["face_open"])
                               if "face_open" in fam else [])
        self._face_mirror_frames = (self._family_frames(*fam["face_mirror"])
                                    if "face_mirror" in fam else [])
        self._face_scar_frame = fam["face_scar"][1] if "face_scar" in fam else None
        self._leg_walk_frames = self._family_frames(*fam["legs_walk"])
        self._leg_crawl_frames = self._family_frames(*fam["legs_crawl"])
        air_key, air_frame = fam["legs_air"]
        self._leg_air_frame = (air_frame
                               if self.atlas is not None and self.atlas.atlases[air_key].has(air_frame)
                               else (self._leg_walk_frames[0] if self._leg_walk_frames
                                     else fam["legs_walk"][1] + "0"))

        self.ascension = None
        self._asc_face_color = None

        self._tongue_rope = None
        self._tongue_rope_v = None

        self._rope_damp = damp60(0.98)
        self._rope_pull_vel = 0.2
        self._rope_pull_pos = 0.4

        self._legs_scale_x = 1.0
    @property
    def facing(self):
        return self.body.facing

    @property
    def bodyMode(self):
        return self.body.bodyMode

    def is_moving(self):
        b = self.body
        return b.is_moving() or b.move_dir != 0

    def body_axis(self):
        """体轴角。"""
        return _ang_from_up(self.draw0[0] - self.draw1[0], self.draw0[1] - self.draw1[1])

    def update(self):
        """每帧推进，在 body.step() 之后调用。"""
        b = self.body
        c0, c1 = b.chunk0, b.chunk1

        if b.cold > 0.0:
            base = self.cat.body_color
            base01 = (base[0] / 255.0, base[1] / 255.0, base[2] / 255.0)
            cq = round(b.cold * 12) / 12   # 量化冷度，压缩 tint 缓存长尾
            r, g, bl = _cold_blend(base01, cq)
            self.BODY = (int(r * 255), int(g * 255), int(bl * 255))
        else:
            self.BODY = tuple(self.cat.body_color)

        self._last_draw0, self._last_draw1 = list(self.draw0), list(self.draw1)
        self.draw0 = [c0.x, c0.y]
        self.draw1 = [c1.x, c1.y]
        if b.bodyMode == "Stand":
            if b.is_moving() or b.move_dir != 0:
                self.anim_frame += 1
                if self.anim_frame > 6:
                    self.anim_frame = 0
            else:
                self.anim_frame = 0
        elif b.bodyMode == "Crawl":
            if (b.is_moving() or b.move_dir != 0) and abs(c1.vx) > 0.5:
                self.anim_frame += 1
                if self.anim_frame > 10:
                    self.anim_frame = 0
            else:
                self.anim_frame = 0
        elif b.bodyMode == "ClimbingOnBeam":
            anim = getattr(b, "animation", None)
            if anim in ("ClimbOnBeam", "HangFromBeam", "GetUpOnBeam"):
                self.anim_frame = (self.anim_frame + 1) % 20
            elif anim == "StandOnBeam":
                self.anim_frame = ((self.anim_frame + 1) % 7
                                   if abs(c1.vx) > 0.5 else 0)
            else:
                self.anim_frame = 0
        elif b.bodyMode == "ZeroG":
            self.anim_frame = (self.anim_frame + 1) % 240
        else:
            self.anim_frame = 0

        self._apply_drawpos_offsets()
        self._update_blink()

        self.last_look_dir = self.look_dir
        self._update_look()

        lx, ly = self.look_dir
        if not self.dead and (lx or ly):
            if b.standing:
                ly_c = clampf(ly, -LOOK_LEAN_VCAP, LOOK_LEAN_VCAP)
                if not (b.is_moving() or b.move_dir != 0):
                    self.head.vx -= lx * 0.5
                    self.head.vy -= ly_c * 0.5
                self.draw0[0] -= lx * 2
                self.draw0[1] -= ly_c * 2
            else:
                self.head.vx += lx * K_IMP
                self.head.vy += ly * K_IMP

        tx = self.draw0[0] + (self.draw1[0] - self.draw0[0]) * HEAD_TARGET_LERP
        ty = self.draw0[1] + (self.draw1[1] - self.draw0[1]) * HEAD_TARGET_LERP
        ddx, ddy = self.draw0[0] - self.draw1[0], self.draw0[1] - self.draw1[1]
        dd = math.hypot(ddx, ddy) or 1.0
        if b.bodyMode == "Crawl":
            tx += ddx / dd * HEAD_PRELEAD * 2.5
            ty += ddy / dd * HEAD_PRELEAD
        else:
            tx += ddx / dd * HEAD_PRELEAD
            ty += ddy / dd * HEAD_PRELEAD
        self.head.update(HEAD_AIR)
        self.head.connect_to_point(tx, ty, c0.vx, c0.vy)

        if b.cold_gain > 0.0:
            amt = inv_lerp(0.0, 0.0007, b.cold_gain) * 2.0
            if amt > 0.0:
                ang = 6.28318530718 * self._shiver_rng.random()
                self.head.vx += math.cos(ang) * amt
                self.head.vy += math.sin(ang) * amt

        target = 1.0 if self.sleeping else 0.0
        if self.sleep_curl < target:
            self.sleep_curl = min(target, self.sleep_curl + SLEEP_CURL_RATE)
        elif self.sleep_curl > target:
            self.sleep_curl = max(target, self.sleep_curl - SLEEP_CURL_RATE * 1.5)

        gf = 1.0 if (self.sleeping or b.bodyMode == "Crawl") else 0.0
        if self.gills_flat < gf:
            self.gills_flat = min(gf, self.gills_flat + GILLS_FLAT_RATE)
        elif self.gills_flat > gf:
            self.gills_flat = max(gf, self.gills_flat - GILLS_FLAT_RATE)
        self._apply_sleep_curl_pose()

        self._update_face_pose()
        self._update_legs()
        self._update_hands()

    def _apply_drawpos_offsets(self):
        """每 bodyMode 的位姿偏移。"""
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        flip = b.facing
        af = self.anim_frame
        TAU = 2.0 * math.pi

        if b.bodyMode == "Stand":
            c = clampf(abs(c1.vx) - 0.2, 0.0, 1.0)
            self.draw0[0] += flip * 6.0 * c
            self.draw0[1] -= math.cos((af + 0.0) / 6.0 * TAU) * 2.0
            self.draw1[0] -= flip * (1.5 - af / 6.0) * 1.0
            self.draw1[1] -= 2.0 + math.sin((af + 0.0) / 6.0 * TAU) * 4.0

        elif b.bodyMode == "Crawl":
            sway_slow = math.sin(af / 21.0 * TAU)
            sway_fast = math.cos(af / 14.0 * TAU)
            hip_drop = 0.0 if getattr(b, "_ctrl_super_launch", 0) > 19 else 1.0  # 自主态无该字段则不拱
            self.draw0[0] += sway_fast * flip * 2.0
            self.draw0[1] -= 1.5 * sway_slow + 3.0
            self.head.vy -= 0.5 * sway_slow + 0.5
            self.head.vx += (-1.0 if c0.x < c1.x else 1.0)
            self.draw1[0] += -3.0 * sway_slow * flip
            self.draw1[1] -= -1.5 * sway_fast + 7.0 - 3.0 * hip_drop

        elif b.bodyMode == "ClimbingOnBeam":
            anim = getattr(b, "animation", None)
            if anim == "ClimbOnBeam":
                ph = af / 20.0 * TAU
                self.draw0[0] += flip * 2.5 + flip * 0.5 * math.sin(ph)
                self.draw1[0] += flip * 2.5 * math.cos(ph)
            elif anim in ("BeamTip", "StandOnBeam"):
                if anim == "StandOnBeam":
                    self.draw1[1] -= 3.0
                sway = math.sin(self.balance_counter / 300.0 * TAU) / (abs(c1.vx) + 1.0)
                self.draw0[0] += sway * (self.disbalance + 20.0) * tuning.BAL_SWAY_X
                self.draw0[1] -= sway * self.disbalance * tuning.BAL_SWAY_Y

        elif b.bodyMode == "ZeroG":
            ddx, ddy = self.draw0[0] - self.draw1[0], self.draw0[1] - self.draw1[1]
            dl = math.hypot(ddx, ddy) or 1.0
            sway = math.sin(af / 240.0 * TAU) * 1.2
            self.draw0[0] += (-ddy / dl) * sway
            self.draw0[1] += (ddx / dl) * sway

        elif b.bodyMode == "Swimming":
            sc = math.sin(b.swim_cycle * TAU)
            if b.swim_mode == "deep" or getattr(b, "swim_input_x", 0) != 0:
                dvx, dvy = c1.x - c0.x, c1.y - c0.y
                dl = math.hypot(dvx, dvy) or 1.0
                px, py = -dvy / dl, dvx / dl
                self.draw1[0] += px * sc * 5.0
                self.draw1[1] += py * sc * 5.0
            if b.lungs_exhausted:
                self.head.vy -= sc * 1.0                  # y↓ 取反
                self.draw0[1] -= sc * 2.5

    def _update_blink(self):
        if self.dead:
            self.blink = 0
            return
        self.blink -= 1
        if self.blink < -self._blink_rng.randint(BLINK_MIN, BLINK_MAX):
            self.blink = self._blink_rng.randint(4, self._blink_rng.randint(4, 15))
        if self.sleeping and self.sleep_curl > 0.5:
            self.blink = max(2, self.blink)
        if (self.body.bodyMode == "Swimming" and getattr(self.body, "lungs_exhausted", False)):
            self.blink = max(self.blink, 1)

    def _apply_sleep_curl_pose(self):
        """睡眠蜷曲：chunks / head 向体中心收拢。"""
        s = self.sleep_curl
        if s <= 0.0:
            return
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        side = 1.0 if c0.x >= c1.x else -1.0
        cx = (c0.x + c1.x) * 0.5
        cy = (c0.y + c1.y) * 0.5
        k = s * 0.2
        self.draw0[0] += (cx - self.draw0[0]) * k
        self.draw0[1] += (cy - self.draw0[1]) * k - 2.0 * s
        self.draw1[0] += (cx - self.draw1[0]) * k - 3.0 * side * s
        self.draw1[1] += (cy - self.draw1[1]) * k - 2.0 * s
        self.head.vx *= 1.0 - 0.4 * s
        self.head.vy *= 1.0 - 0.4 * s
        self.head.x += (cx + side * 5.0 - self.head.x) * (0.5 * s)
        self.head.y += (cy + 3.0 - self.head.y) * (0.5 * s)

    def _apply_sleep_tail_curl(self):
        """尾巴睡眠蜷曲推进，在 tail.step() 之后调用。"""
        s = self.sleep_curl
        if s <= 0.0 or self.tail_segs is None:
            return
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        side = 1.0 if c0.x >= c1.x else -1.0
        d1x, d1y = self.draw1[0], self.draw1[1]
        n = len(self.tail_segs)
        for i, seg in enumerate(self.tail_segs):
            t = i / (n - 1) if n > 1 else 0.0
            seg.vx *= 1.0 - 0.2 * s
            seg.vy *= 1.0 - 0.2 * s
            sin_t = math.sin(t * math.pi)
            tx = d1x + (sin_t * 25.0 - t * 10.0) * (-side)
            ty = d1y + _lerp(-5.0, 15.0, t)
            k = 0.1 * s
            seg.x += (tx - seg.x) * k
            seg.y += (ty - seg.y) * k

    def _update_look(self):
        if self.look_at is None or self.dead:
            self.look_dir = (0.0, 0.0)
            return
        lx = self.look_at[0] - self.head.x
        ly = self.look_at[1] - self.head.y
        d = math.hypot(lx, ly)
        if d < 1e-6:
            self.look_dir = (0.0, 0.0)
            return
        self.look_dir = (lx / d, ly / d)

    def _update_face_pose(self):
        """计算 head_angle, face_angle, face_scale_x, face_offset。"""
        b = self.body
        body_x, body_y = self.draw0
        hip_x, hip_y = self.draw1
        hx, hy = self.head.x, self.head.y
        base_x = (hip_x + body_x) * 0.5
        base_y = (hip_y + body_y) * 0.5
        head_ang = _ang_from_up(hx - base_x, hy - base_y)
        look_x = (self.last_look_dir[0] + self.look_dir[0]) * 0.5 * 3.0 * (1.0 - self.sleep_curl)
        look_y = (self.last_look_dir[1] + self.look_dir[1]) * 0.5 * 3.0 * (1.0 - self.sleep_curl)
        if self.sleep_curl > 0.0:
            self.head_frame_override = None
            side = 1.0 if body_x >= hip_x else -1.0
            self.head_angle = _lerp(head_ang, 45.0 * side, self.sleep_curl)
            self.face_angle = head_ang * (1.0 - self.sleep_curl)
            self.face_scale_x = side
            look_x -= 4.0 * side * self.sleep_curl
            look_y += 2.0 * self.sleep_curl
        elif self.dead or self.stunned:
            self.head_frame_override = None
            self.head_angle = head_ang
            self.face_angle = head_ang
            self.face_scale_x = -1.0 if head_ang < 0 else 1.0
            look_x = look_y = 0.0
        elif b.bodyMode == "Crawl":
            self.head_frame_override = 7
            self.head_angle = head_ang
            self.face_angle = 0.0
            self.face_scale_x = 1.0 if body_x >= hip_x else -1.0
            look_x = 0.0
        elif b.bodyMode == "ZeroG":
            self.head_frame_override = None
            self.head_angle = head_ang
            self.face_angle = head_ang
            self.face_scale_x = -1.0 if head_ang < 0.0 else 1.0
        elif b.bodyMode == "Swimming":
            self.head_frame_override = None
            self.head_angle = head_ang
            self.face_angle = head_ang
            self.face_scale_x = -1.0 if head_ang < 0.0 else 1.0
        elif b.bodyMode == "Stand" and (b.is_moving() or b.move_dir != 0):
            self.head_frame_override = 6
            self.head_angle = head_ang
            self.face_angle = 0.0
            self.face_scale_x = 1.0 if head_ang >= 0 else -1.0
            look_x = 0.0
        else:
            self.head_frame_override = None
            self.head_angle = head_ang
            self.face_angle = 0.0
            self.face_scale_x = (1.0 if look_x >= 0 else -1.0) if abs(look_x) >= 0.1 else (-1.0 if head_ang < 0 else 1.0)
        self.face_offset = (look_x, look_y + 2.0)
        if b.animation == "Flip":
            r = math.radians(self.head_angle)
            self.face_offset = (self.face_offset[0] + math.sin(r) * 4.0,
                                self.face_offset[1] - math.cos(r) * 4.0)

    def _update_legs(self):
        """腿部弹性骨推进。"""
        b = self.body
        c1 = b.chunk1
        self.legs.update(LEGS_AIR)

        anim = getattr(b, "animation", None)
        if b.bodyMode == "ClimbingOnBeam" and anim in (
                "ClimbOnBeam", "BeamTip", "StandOnBeam", "HangFromBeam", "GetUpOnBeam"):
            c0 = b.chunk0
            if anim == "ClimbOnBeam":
                ph = self.anim_frame / 20.0 * 2.0 * math.pi
                tx = c0.x + (-b.facing) * (5.0 - math.sin(ph))
                ty = c0.y + 16.0 + 5.0 * math.cos(ph)
                self.legs.connect_to_point(tx, ty, 0.0, 0.0, connect_rad=0.0,
                                           elastic=LEGS_ELASTIC, adapt_retain=LEGS_ADAPT_RETAIN,
                                           exaggerate=LEGS_EXAGGERATE)
                self.legs_dir[1] += 1.0
            elif anim == "BeamTip":
                self.legs.connect_to_point(c1.x, c1.y + 8.0, 0.0, 10.0, connect_rad=0.0,
                                           elastic=LEGS_ELASTIC, adapt_retain=LEGS_ADAPT_RETAIN,
                                           exaggerate=LEGS_EXAGGERATE)
                dx = c1.x - self.draw0[0]
                dy = (c1.y + 10.0) - self.draw0[1]
                dl = math.hypot(dx, dy) or 1.0
                self.legs_dir[0] += dx / dl
                self.legs_dir[1] += dy / dl
            elif anim == "StandOnBeam":
                tx = c1.x + self.legs_dir[0] * 8.0
                ty = c1.y - 1.0
                self.legs.connect_to_point(tx, ty, c1.vx, LEGS_HOST_Y, connect_rad=5.0,
                                           elastic=LEGS_ELASTIC, adapt_retain=LEGS_ADAPT_RETAIN,
                                           exaggerate=LEGS_EXAGGERATE)
                self.legs_dir[1] += 1.0
            else:
                tx = c1.x + self.legs_dir[0] * 8.0
                ty = c1.y + (5.0 if anim == "HangFromBeam" else 2.0)
                self.legs.connect_to_point(tx, ty, c1.vx, LEGS_HOST_Y, connect_rad=LEGS_CONNECT_RAD,
                                           elastic=LEGS_ELASTIC, adapt_retain=LEGS_ADAPT_RETAIN,
                                           exaggerate=LEGS_EXAGGERATE)
                self.legs_dir[0] += c1.vx * 0.01
                self.legs_dir[1] += c1.vy * 0.01 + 0.05
            d = math.hypot(self.legs_dir[0], self.legs_dir[1]) or 1.0
            self.legs_dir[0] /= d
            self.legs_dir[1] /= d
            return

        if b.bodyMode == "ZeroG":
            c0 = b.chunk0
            dx, dy = c1.x - c0.x, c1.y - c0.y
            dl = math.hypot(dx, dy) or 1.0
            ux, uy = dx / dl, dy / dl
            self.legs.connect_to_point(c1.x + ux * 4.0, c1.y + uy * 4.0, c1.vx, c1.vy,
                                       connect_rad=LEGS_CONNECT_RAD, elastic=0.0,
                                       adapt_retain=0.8, exaggerate=0.0)
            self.legs_dir[0] = ux
            self.legs_dir[1] = uy
            self.legs.vx += ux * 0.2
            self.legs.vy += uy * 0.2
            d = math.hypot(self.legs_dir[0], self.legs_dir[1]) or 1.0
            self.legs_dir[0] /= d
            self.legs_dir[1] /= d
            return


        if c1.on_floor:
            tx = c1.x + self.legs_dir[0] * 8.0
            ty = c1.y - 1.0
            self.legs.connect_to_point(tx, ty, c1.vx, LEGS_HOST_Y,
                                       connect_rad=5.0, elastic=LEGS_ELASTIC,
                                       adapt_retain=LEGS_ADAPT_RETAIN,
                                       exaggerate=LEGS_EXAGGERATE)
            self.legs_dir[0] -= b.chunk1.on_slope if hasattr(b.chunk1, "on_slope") else 0.0
            self.legs_dir[1] += 1.0
        else:
            tx = c1.x + self.legs_dir[0] * 8.0
            ty = c1.y + 2.0
            self.legs.connect_to_point(tx, ty, c1.vx, LEGS_HOST_Y,
                                       connect_rad=LEGS_CONNECT_RAD, elastic=LEGS_ELASTIC,
                                       adapt_retain=LEGS_ADAPT_RETAIN, exaggerate=LEGS_EXAGGERATE)
            self.legs_dir[0] += c1.vx * 0.01
            self.legs_dir[1] += c1.vy * 0.01 + 0.05

        d = math.hypot(self.legs_dir[0], self.legs_dir[1]) or 1.0
        self.legs_dir[0] /= d
        self.legs_dir[1] /= d

    def _update_hands(self):
        """双手 IK：确定每手 target 后交给 Hand.update()。"""
        b = self.body
        spine_ang = self.body_axis()
        crawl_ground_y = getattr(b, "visual_floor_y", b.H) - 4.0
        for idx, (side, sh_local_sign) in enumerate((("l", -1.0), ("r", +1.0))):
            sx, sy = self._shoulder(sh_local_sign, spine_ang)
            hand = self.hands[0] if side == "l" else self.hands[1]

            # 优先级：hand_aim > arm_aim > 内部姿态 > None（收回）
            aim = None if self.dead else self.hand_aim[side]
            if aim is None and not self.dead:
                aim = getattr(b, "arm_aim", _NO_ARM_AIM).get(side)
            speed = HUNT_SPEED
            quickness = HAND_QUICKNESS

            if aim is None and not self.dead:
                anim = getattr(b, "animation", None)
                if b.bodyMode == "ClimbingOnBeam" and anim in (
                        "ClimbOnBeam", "BeamTip", "StandOnBeam", "HangFromBeam", "GetUpOnBeam"):
                    aim, speed, quickness = self._beam_hand_target(idx, anim, spine_ang)
                elif b.bodyMode == "Crawl":
                    if self.sleep_curl > 0.0:
                        pass    # 睡觉手缩回贴肩，勿伸向腹部目标
                    else:
                        c0 = b.chunk0
                        vspd = math.hypot(c0.vx, c0.vy)
                        if vspd > 1e-6:
                            lead_x = c0.vx / vspd * 20.0
                        else:
                            lead_x = b.facing * 20.0
                        off_x = -6.0 + 12.0 * idx
                        aim = (c0.x + off_x + lead_x, crawl_ground_y)
                        speed = CRAWL_HUNT_SPEED
                        quickness = CRAWL_QUICKNESS
                elif b.bodyMode == "ZeroG" and getattr(b, "animation", None) == "ZeroGPoleGrab":
                    px = getattr(b, "pole_x", b.chunk0.x)
                    py = getattr(b, "pole_y", b.chunk0.y)
                    pole = getattr(b, "zerog_pole", None)
                    if pole is not None:
                        plx, ply = pole.bx - pole.ax, pole.by - pole.ay
                        pll = math.hypot(plx, ply) or 1.0
                        axu, ayu = plx / pll, ply / pll
                    else:
                        axu, ayu = 0.0, 1.0
                    off = 6.0 * (-1.0 if idx == 0 else 1.0)
                    aim = (px + axu * off, py + ayu * off)
                elif b.bodyMode == "ZeroG":
                    ph = self.anim_frame / 240.0 * 2.0 * math.pi + idx * math.pi
                    ox, oy = _rot(sh_local_sign * 6.0, 8.0 + 2.0 * math.sin(ph), spine_ang)
                    aim = (self.draw0[0] + ox, self.draw0[1] + oy)
                    speed = 3.0
                    quickness = 0.3
                elif b.bodyMode == "Swimming":
                    # 潜水=扇形划桨（相对目标）；浮水=贴水面线划圆（绝对目标）
                    c0, c1 = b.chunk0, b.chunk1
                    sw = b.swim_cycle
                    paddle_t = sw / 3.0 if sw < 3.0 else (1.0 - (sw - 3.0))
                    ix = getattr(b, "swim_input_x", 0)
                    if b.swim_mode == "deep":
                        stroke = (1.0 - inv_lerp(0.5, 1.0, paddle_t)) ** 1.5
                        ang = math.radians((20.0 + stroke * 140.0) * sh_local_sign)
                        rhx, rhy = math.sin(ang) * 20.0, math.cos(ang) * 20.0
                        if sw < 3.0:
                            rhx *= 0.5
                        spine_phys = _ang_from_up(c0.x - c1.x, c0.y - c1.y)
                        ox, oy = _rot(rhx, -rhy, spine_phys)  # y↓ 取反
                        aim = (c0.x + ox, c0.y + oy)
                    else:
                        ws = getattr(b, "water_surface", None)
                        ahx = c0.x + _lerp(sh_local_sign * 30.0,
                                           ix * 10.0 * (-math.sin(paddle_t * 2.0 * math.pi)), 0.5)
                        ahy = (ws.level_at(ahx) + 7.0) if ws is not None else (c0.y + 7.0)
                        sang = math.radians(360.0 * paddle_t * (1.0 if ix == 0 else -ix))
                        srad = sh_local_sign * (5.0 if ix == 0 else 10.0)
                        aim = (ahx + math.sin(sang) * srad, ahy - math.cos(sang) * srad)  # y↓ 取反
                    speed = 5.0
                    quickness = 0.5

            hand.update(sx, sy, aim, speed=speed, quickness=quickness)

    def _beam_hand_target(self, j, anim, axis):
        """爬杆 / 站顶的手目标。"""
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        if anim == "ClimbOnBeam":
            px = getattr(b, "pole_x", c1.x)
            flip = b.facing
            ph = self.anim_frame / 20.0 * 2.0 * math.pi
            b_j1 = (j == 1)
            b_fp = (flip == 1)
            f = math.cos(ph) if (b_j1 != b_fp) else math.sin(ph)
            cond = (b_j1 == b_fp)
            off_y_up = (-3.0 if cond else 3.0) + 6.0 * f
            hx = px + (-flip if cond else flip)
            hy = c0.y - off_y_up
            return (hx, hy), HUNT_SPEED, HAND_QUICKNESS
        if anim in ("HangFromBeam", "GetUpOnBeam"):
            beam_y = getattr(b, "pole_y", c0.y)
            sh = 10.0 + 3.0 * math.sin(2.0 * math.pi * self.anim_frame / 20.0)
            hx = c0.x + (-1.0 if j == 0 else 1.0) * sh
            return (hx, beam_y), HUNT_SPEED, HAND_QUICKNESS
        sway = math.sin(2.0 * math.pi * self.balance_counter / 300.0)
        relx = -20.0 + 40.0 * j
        rely_up = -4.0 - 6.0 * sway * (-1.0 if j == 0 else 1.0)
        if anim == "StandOnBeam" and self.disbalance < 40.0:
            s = (40.0 - self.disbalance) / 40.0
            rely_up = rely_up * (1.0 - s) - s * 15.0
            relx = relx * (1.0 - s)
        ox, oy = _rot(relx, -rely_up, axis)
        return (c0.x + ox, c0.y + oy), 5.0, 0.2

    def _shoulder(self, sign, spine_ang):
        """肩点 = draw0 + 绕轴旋转 (±4.5,+3.5)。"""
        ox, oy = _rot(sign * SHOULDER_OFF_X, SHOULDER_OFF_Y, spine_ang)
        return self.draw0[0] + ox, self.draw0[1] + oy

    def tail_root_world(self):
        """尾网根世界坐标 = 75% 臀 + 25% 上身。"""
        return ((self.draw1[0] * 3.0 + self.draw0[0]) / 4.0,
                (self.draw1[1] * 3.0 + self.draw0[1]) / 4.0)

    def mouth_world(self):
        return (self.head.x + self.face_offset[0],
                self.head.y + self.face_offset[1])

    def _family_frames(self, atlas_key, prefix):
        def idx(name):
            m = re.search(r'(\d+)$', name)
            return int(m.group(1)) if m else -1
        names = [n for n in self.atlas.atlases[atlas_key].frame_names()
                 if re.sub(r'\d+$', '', n) == prefix]
        return sorted(names, key=idx)

    def _face_angle_index(self):
        look_ox = self.face_offset[0]
        look_oy = self.face_offset[1] - 2.0
        look_mag = math.hypot(look_ox, look_oy)
        axis_x = (self.head.x - self.draw1[0]) * (1.0 - look_mag / 3.0)
        axis_y = self.head.y - self.draw1[1]
        ang = abs(_ang_from_up(axis_x, axis_y))
        return int(round(ang / 22.5))

    def _head_frame_index(self):
        """HeadB 帧号单一真值源：sleep > dead > Crawl > Stand&&moving > ZeroG > 角度基线。"""
        b = self.body
        if self.sleep_curl > 0.0:
            return int(clampf(int(_lerp(7.0, 4.0, self.sleep_curl)), 0, 8))
        if self.dead or self.stunned:
            return 0
        if b.bodyMode == "Crawl":
            return 7
        if b.bodyMode == "Stand" and (b.is_moving() or b.move_dir != 0):
            return 6
        if b.bodyMode == "ZeroG":
            return 0
        return int(round(abs(self.head_angle / 360.0 * 34.0)))

class _Rng:
    """确定性 LCG（blink/face 用）。"""
    __slots__ = ("s",)

    def __init__(self, seed):
        self.s = seed & 0xFFFFFFFF

    def _next(self):
        self.s = (1103515245 * self.s + 12345) & 0x7FFFFFFF
        return self.s

    def randint(self, lo, hi):
        if hi <= lo:
            return lo
        return lo + self._next() % (hi - lo)

    def random(self):
        return self._next() / 2147483647.0   # [0,1]
