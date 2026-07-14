"""飞升超度 Ascension：冲击波→悬浮回正→追锁蓄能→闪→劫持光标。"""
from __future__ import annotations
import math

from ...core.units import K_VEL, K_IMP, clampf

T_ASCEND_TIMEOUT = 1200

# 起跳腾空（仅地面触发）
LAUNCH_TICKS = 14
LAUNCH_SPEED = 11.0 * K_VEL

# 业力图标追逐（px/tick）
HOMING_RANGE = 450.0
LOCK_DIST = 40.0
GAIN = 0.02
GAIN_LOCKED = 0.25
STEP_MIN = 2.5 * K_VEL
STEP_MAX = 10.0 * K_VEL
STEP_MAX_LOCKED = 100.0 * K_VEL

# 蓄能（/tick）
KILLWAIT_RATE = 0.035
KILLFAC_RATE = 0.025

# 闪
FLASH_RADIUS = 60.0
SPARK_COUNT = 20
SPARK_SPEED_MAX = 40.0 * K_VEL
SPARK_LIFE_MIN, SPARK_LIFE_MAX = 30, 120   # 40Hz

# 视觉常量
NUM_GOD_PIPS = 12

GUARD_ICON_COLOR = (255, 221, 132)


class Ascension:
    def __init__(self, win):
        self.win = win
        self.body = win.body
        grounded = self.body.on_floor()
        self.body.hover = True
        self.body.suspended = False
        self.timer = 0
        self.launch = LAUNCH_TICKS if grounded else 0   # 地面先窜起，空中跳过
        self.upright = 15

        self.homing_range = max(HOMING_RANGE, math.hypot(win._WL, win._HL))

        c0 = self.body.chunk0
        self.fx = c0.x
        self.fy = c0.y - 60.0
        self.killWait = 0.0
        self.killFac = 0.0
        self.lockon = False
        self.flashed = False
        self.flash_t = 0
        self.bobp = 0.0
        # mouse=burst偏移滞后；mark=平滑body位
        self.rubber_mouse_x = 0.0
        self.rubber_mouse_y = 0.0
        bx, by = self.body.chunk0.x, self.body.chunk0.y
        self.rubber_mark_x = bx
        self.rubber_mark_y = by
        # 淡入 / 半径缓动
        self.rubber_alpha_emblem = 0.0
        self.rubber_alpha_pips = 0.0
        self.rubber_radius = 6.0         # 缓动到 15

        # 4 条触手，X 形 45/135/225/315°
        from .tentacles import GhostTentacle
        self.darken = 0.0        # 变暗因子 0..1
        self.tentacles_visible = 0
        rx, ry = self._body_root()
        self.tentacles = [GhostTentacle(rx, ry, length=100.0, seed=i) for i in range(4)]

        if self.launch > 0:
            self.body.chunk0.vy -= LAUNCH_SPEED
            self.body.chunk1.vy -= LAUNCH_SPEED
        else:
            self._enter_burst()

    def _enter_burst(self):
        """进入冲击波 + 白色溅射。"""
        win, c1 = self.win, self.body.chunk1
        win.add_shockwave(c1.x, c1.y, 100.0)
        for i in range(10):
            ang = (i / 10.0) * 2 * math.pi
            sp = 2.67 + (14.0 - 2.67) * ((i * 7 % 10) / 10.0)
            win.add_spark(c1.x, c1.y, math.cos(ang) * sp, math.sin(ang) * sp, white=True)

    def _body_root(self):
        """触手根锚 = chunk0（上半身）。"""
        c0 = self.body.chunk0
        return (c0.x, c0.y)

    def _hip_pos(self):
        """臀部光斑锚 = (chunk1*2+chunk0)/3。"""
        c0, c1 = self.body.chunk0, self.body.chunk1
        return ((c1.x * 2.0 + c0.x) / 3.0, (c1.y * 2.0 + c0.y) / 3.0)

    def update(self, cursor):
        self.timer += 1
        if self.launch > 0:
            self.launch -= 1
            self._tick_tentacles()
            if self.launch == 0:
                self._reach_hover()
            return False
        self._hover_body()
        self._tick_tentacles()
        if not self.flashed:
            self._chase_charge(cursor)
            if self.killFac >= 1.0:
                self._flash()
            elif self.timer >= T_ASCEND_TIMEOUT:
                return self._exit(hijack=False)
        else:
            # 闪后短暂停留 → 落下
            if self.timer - self.flash_t > 8:
                return self._exit(hijack=True)
        return False

    def _reach_hover(self):
        """腾空到位：同步业力图标/橡皮筋锚，避免位置突跳。"""
        self._enter_burst()
        c0 = self.body.chunk0
        self.fx, self.fy = c0.x, c0.y - 60.0
        self.rubber_mark_x, self.rubber_mark_y = c0.x, c0.y

    def _tick_tentacles(self):
        """推进 4 条触手；触手纯图形，绝不施力。"""
        target_vis = 0 if (self.upright > 0) else 4
        if self.tentacles_visible < target_vis and (self.timer % 18 == 0):
            self.tentacles_visible += 1
        if self.tentacles_visible > target_vis:
            self.tentacles_visible = target_vis
        target_darken = 0.0 if self.flashed else (0.85 if self.tentacles_visible > 0 else 0.0)
        if self.tentacles_visible > 0 and self.darken == 0.0:
            self.darken = 0.01
        self.darken += (target_darken - self.darken) * 0.04
        if self.darken < 0.005 and target_darken == 0.0:
            self.darken = 0.0
        if self.darken <= 0.0:
            return
        from .tentacles import deg_to_vec_qt
        rx, ry = self._body_root()
        for i, t in enumerate(self.tentacles):
            t.update()
            dvx, dvy = deg_to_vec_qt(45.0 + 90.0 * i)
            t.set_position(rx + dvx * 8.0, ry + dvy * 8.0)
            if i >= self.tentacles_visible:
                t.inactive_update()
            else:
                t.active_update()

    def _hover_body(self):
        c0, c1 = self.body.chunk0, self.body.chunk1
        if self.upright > 0:
            self.upright -= 1
            mx = (c0.x + c1.x) * 0.5
            my = (c0.y + c1.y) * 0.5
            half = self.body.conn_rest * 0.5
            k = 0.25
            c0.x += (mx - c0.x) * k
            c0.y += ((my - half) - c0.y) * k
            c1.x += (mx - c1.x) * k
            c1.y += ((my + half) - c1.y) * k
            c0.vx *= 0.5
            c0.vy *= 0.5
            c1.vx *= 0.5
            c1.vy *= 0.5
        else:
            self.bobp += 1.0 / 120.0
            c0.vy -= 0.05
            c1.vy += 0.05

    def _chase_charge(self, cursor):
        if cursor is None:
            return
        cx, cy = cursor
        dx, dy = cx - self.fx, cy - self.fy
        dist = math.hypot(dx, dy)
        if 1e-6 < dist < self.homing_range:
            gain = GAIN_LOCKED if self.lockon else GAIN
            mx = STEP_MAX_LOCKED if self.lockon else STEP_MAX
            step = min(clampf(dist * gain, STEP_MIN, mx), dist)
            self.fx += dx / dist * step
            self.fy += dy / dist * step
        # 进 LOCK_DIST → 锁定蓄能；出 → 清零
        if dist < LOCK_DIST:
            self.lockon = True
            self.killWait = min(self.killWait + KILLWAIT_RATE, 1.0)
            if self.killWait >= 1.0:
                self.killFac = min(self.killFac + KILLFAC_RATE, 1.0)
        else:
            self.lockon = False
            self.killWait = 0.0
            self.killFac = 0.0
        bx, by = self.body.chunk0.x, self.body.chunk0.y
        burst_x = self.fx - bx                # burst 横向裸偏移
        burst_y = (self.fy + 60.0) - by
        follow = 0.3 if self.lockon else 0.15
        self.rubber_mouse_x += (burst_x - self.rubber_mouse_x) * follow
        self.rubber_mouse_y += (burst_y - self.rubber_mouse_y) * follow
        # 平滑 body 位置，突跳 >100px 立即同步
        if math.hypot(bx - self.rubber_mark_x, by - self.rubber_mark_y) > 100.0:
            self.rubber_mark_x = bx
            self.rubber_mark_y = by
        else:
            self.rubber_mark_x += (bx - self.rubber_mark_x) * 0.15
            self.rubber_mark_y += (by - self.rubber_mark_y) * 0.25
        # 半径缓动 + 淡入
        self.rubber_radius += (15.0 - self.rubber_radius) * 0.045
        if self.rubber_radius < 5.0:
            self.rubber_radius = 15.0
        self.rubber_alpha_emblem += (1.0 - self.rubber_alpha_emblem) * 0.05
        self.rubber_alpha_pips += (1.0 - self.rubber_alpha_pips) * 0.05

    def _flash(self):
        self.flashed = True
        self.flash_t = self.timer
        win = self.win
        win.add_shockwave(self.fx, self.fy, FLASH_RADIUS, flash=True)
        for i in range(SPARK_COUNT):
            ang = (i / SPARK_COUNT) * 2 * math.pi + (i * 0.37)
            sp = ((i * 13 % 20) / 20.0) * SPARK_SPEED_MAX
            win.add_spark(self.fx, self.fy, math.cos(ang) * sp, math.sin(ang) * sp,
                          white=True, life=SPARK_LIFE_MIN + (i * 9 % (SPARK_LIFE_MAX - SPARK_LIFE_MIN)))
        win.start_cursor_hijack(self.fx, self.fy)

    def _exit(self, hijack):
        self.body.hover = False
        return True

    def abort(self):
        """飞升中止：释放悬浮 + 劫持。"""
        self.body.hover = False
        self.win.stop_cursor_hijack()

    def draw_under(self, p, ts):
        """身体下层：幽灵触手 + 臀部扭曲光斑。在 gfx.draw_sprites 前调用。"""
        if self.darken > 0.0:
            self._draw_ghost_distortion(p)
            self._draw_tentacles(p, ts)

    def _draw_tentacles(self, p, ts):
        """4 条幽灵触手，加色混合。"""
        from ...rendering.primitives import ribbon
        from PySide6.QtGui import QPainter
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        for i, t in enumerate(self.tentacles):
            if i >= self.tentacles_visible:
                continue
            pts, hws, cols = t.build_centerline(ts)
            ribbon(p, pts, hws, cols)
        p.restore()

    def _draw_ghost_distortion(self, p):
        """臀部扭曲光斑。"""
        from PySide6.QtGui import QColor, QRadialGradient, QBrush, QPainter
        from PySide6.QtCore import QPointF, Qt
        hx, hy = self._hip_pos()
        radius = 15.0 * self.darken * 8.0            # 16px 贴图，半径≈scale*8
        if radius < 1.0:
            return
        a = int(70 * self.darken)
        grad = QRadialGradient(QPointF(hx, hy), radius)
        grad.setColorAt(0.0, QColor(120, 200, 180, a))
        grad.setColorAt(1.0, QColor(120, 200, 180, 0))
        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawEllipse(QPointF(hx, hy), radius, radius)
        p.restore()

    def draw(self, p):
        """光斑、守护眼、god pips。flashed 后不画；触手在 draw_under。"""
        if self.flashed:
            return
        from PySide6.QtGui import QPainter
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        flat_x, flat_y = self.fx, self.fy   # 光斑位 = body + burst
        # 眼位 = rubber_mark + rubber_mouse，-60 向上偏移
        eye_x = self.rubber_mark_x + self.rubber_mouse_x
        eye_y = self.rubber_mark_y - 60.0 + self.rubber_mouse_y
        self._draw_flat_light(p, flat_x, flat_y)
        self._draw_guard_eye(p, eye_x, eye_y, self.rubber_alpha_emblem)
        self._draw_god_pips(p, eye_x, eye_y, self.rubber_alpha_pips, self.rubber_radius)

    def _draw_flat_light(self, p, cx, cy):
        """蓄能光斑：scale 随蓄能从 50 收到 2，alpha=f³。"""
        f = self.killFac
        if f <= 0.0:
            return
        from PySide6.QtGui import QColor, QRadialGradient, QBrush, QPainter
        from PySide6.QtCore import QPointF, Qt
        scale = 50.0 + (2.0 - 50.0) * math.sqrt(f)
        radius = scale * 8.0                           # 16px 贴图，半径≈scale*8
        alpha = f ** 3.0
        grad = QRadialGradient(QPointF(cx, cy), radius)
        grad.setColorAt(0.0, QColor(255, 255, 255, int(alpha * 255)))
        grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.save()
        # 加色发光：用 Plus 近似
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawEllipse(QPointF(cx, cy), radius, radius)
        p.restore()

    def _draw_guard_eye(self, p, cx, cy, alpha=1.0):
        """guardEye 图标，固定暖金色，勿改回。"""
        from PySide6.QtGui import QColor
        from PySide6.QtCore import QPointF
        a = max(0, min(255, int(alpha * 255)))
        if a <= 0:
            return
        atlas = getattr(self.win, "atlas", None)
        if atlas is None:
            return
        key = atlas.find_atlas("guardEye")
        if key is None:
            return
        tint = QColor(*GUARD_ICON_COLOR, a)
        pm = atlas.sprite(key, "guardEye", tint)
        p.save()
        p.drawPixmap(QPointF(cx - pm.width() * 0.5, cy - pm.height() * 0.5), pm)
        p.restore()

    def _draw_god_pips(self, p, cx, cy, alpha=1.0, radius=15.0):
        """12 个 WormEye god pips，固定暖金色，勿改回。"""
        from PySide6.QtGui import QColor
        from PySide6.QtCore import QPointF
        a = max(0, min(255, int(alpha * 255)))
        if a <= 0:
            return
        atlas = getattr(self.win, "atlas", None)
        if atlas is None:
            return
        key = atlas.find_atlas("WormEye")
        if key is None:
            return
        lit = int(self.killWait * NUM_GOD_PIPS)
        if lit <= 0:
            return
        tint = QColor(*GUARD_ICON_COLOR, a)
        pm = atlas.sprite(key, "WormEye", tint)
        hw, hh = pm.width() * 0.5, pm.height() * 0.5
        # pips 是普通 sprite → SourceOver（同 guardEye，不加色）
        p.save()
        for i in range(lit):
            # 绕原点顺时针转 i*360/N 度
            ang = math.radians(-(i * (360.0 / NUM_GOD_PIPS)))
            cos_a = math.cos(ang)
            sin_a = math.sin(ang)
            ox = radius * cos_a - radius * sin_a   # 旋转的向量为 (radius, radius)
            oy = radius * sin_a + radius * cos_a
            p.drawPixmap(QPointF(cx + ox - hw, cy + oy - hh), pm)
        p.restore()
