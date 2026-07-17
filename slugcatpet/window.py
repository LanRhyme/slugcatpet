"""全屏透明置顶桌宠窗，固定步长物理+插值渲染。"""
from __future__ import annotations
import os
import random
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer, QElapsedTimer, QRect, QPoint, QPointF, QRectF
from PySide6.QtGui import QPainter, QColor, QGuiApplication, QCursor

from .behavior import tuning
from .rendering.atlas import AtlasSet
from .rendering.layout import Layout
from .rendering.primitives import blit
from .petunit import PetUnit
from .core import chunkphys
from .core.units import clampf, lerp
from .core.water import WaterSurface
from .world.effects import EffectsMixin
from .world.items import ItemInteractionMixin
from .world.enums import ItemState

MAX_PETS = 3

STONE_FAST_REDRAW = 3.0    # 速度超此整窗重绘

GRAV_EASE = 0.08              # 重力缓动率（~1s 过渡）

# 地板下渲染余量
GROUND_INSET = 16.0

# 窗口抖动
SHAKE_DECAY = 0.8
SHAKE_MAX = 6.0
SHAKE_EPS = 0.05


def compute_geometry(area: QRect, geo: QRect, canvas_scale: int) -> dict:
    """算地面/窗口几何。"""
    s = canvas_scale or 1
    avail_below = max(0, (geo.y() + geo.height()) - (area.y() + area.height()))
    inset_dev = avail_below if avail_below > 0 else int(round(GROUND_INSET * s))
    return {"WL": area.width() / s, "HL": area.height() / s, "ground_inset": inset_dev,
            "win_w": area.width(), "win_h": area.height() + inset_dev}


def _clamp_chunk_to_bounds(c, WL, HL):
    """chunk 夹进边界。"""
    r = max(c.rad, 1.0)
    if c.x < r:
        c.x = r
    elif c.x > WL - r:
        c.x = WL - r
    if c.y + r > HL:
        c.y = HL - r
        if c.vy > 0:
            c.vy = 0.0


def _clamp_item_to_bounds(o, WL, HL):
    """物体夹进边界。"""
    r = getattr(o, "rad", 0.0)
    if o.x < r:
        o.x = r
    elif o.x > WL - r:
        o.x = WL - r
    if o.y + r > HL:
        o.y = HL - r
        if o.vy > 0:
            o.vy = 0.0


class PetWindow(EffectsMixin, ItemInteractionMixin, QWidget):
    def __init__(self, layout: Layout | None = None, debug: bool | None = None,
                 params=None):
        super().__init__()
        self._params = params or {}
        self.atlas = AtlasSet()
        self.layout_data = layout or Layout.load()
        if debug is None:
            debug = os.environ.get("SLUGCATPET_DEBUG") not in (None, "", "0")
        self.debug = debug

        flags = (Qt.WindowType.FramelessWindowHint
                 | Qt.WindowType.WindowStaysOnTopHint
                 | Qt.WindowType.Tool)
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, not self.debug)
        if self.debug:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        s = self.layout_data.canvas_scale
        screen = QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        geo = screen.geometry()
        geom = compute_geometry(area, geo, s)
        self._area = area                     # 工作区（不含下延带）
        self._scale = s
        self._WL = geom["WL"]
        self._HL = geom["HL"]                  # 地板线=工作区底边，下延后不变
        self._ground_inset = geom["ground_inset"] / s if s else 0.0
        self.resize(geom["win_w"], geom["win_h"])
        self.move(area.x(), area.y())

        # 特效层
        self.sparks = []         # [x,y,vx,vy,life,maxlife,white]
        self.shockwaves = []     # [x,y,r,maxr,life,maxlife,flash]
        self.fx = []
        self.bubbles = []
        self._bubble_rng = random.Random(0xB0BB1E)
        self.cursor_hijack = None
        self._hud = None
        self._pets_changed_cb = None
        self._open_settings_cb = None
        self._hotkey_filter = None
        self._control_hud = None         # 非 None 即有受控会话

        self.world_version = 0                 # 放/清道具、环境变化时 +1
        self.geometry_version = 0              # 路径前提变更（杆/灯/工作区）时 +1

        # 放果子
        self.fruits = []
        self._place_mode = False
        self._place_kind = None
        self._fruit_seed = 0
        self._dragged_fruit = None
        self._drag_last = None

        # 放石头
        self.stones = []
        self._stone_seed = 0
        self._dragged_stone = None
        self._stone_drag_last = None
        self._stun_rng = random.Random(98765)

        # 放黏菌
        self.slimemolds = []
        self._slimemold_seed = 0
        self._dragged_slimemold = None
        self._slime_drag_last = None
        self._slime_preview = None

        # 放蝙蝠
        self.batflies = []
        self._batfly_seed = 0
        self._dragged_batfly = None
        self._batfly_drag_last = None

        # 放杆子
        self.poles = []
        self._pole_seed = 0

        # 寒冷系统
        self.blizzard_on = not tuning.COLD_BLIZZARD_DEFAULT_OFF
        self.blizzard_timer = 0
        self.lamp = None
        self._lamp_seed = 0
        self.cold_cycle_prog = 0.0
        # Snow 氛围
        from .world.snow import Snowfall
        self.snow_on = tuning.SNOW_ENABLED
        self._snow = Snowfall(tuning.SNOW_MAX_FLAKES, tuning.SNOW_VIGNETTE_MAX, seed=0x5)

        # 无重力
        self.room_gravity = 1.0
        self.gravity_target = 1.0
        self.zerog_on = False

        # 水环境
        self.water_on = False
        self.water_y = None            # 越小越高；None=无水
        self.water_target = None
        self.water_surface = None

        self._shake = [0.0, 0.0]

        self._prev_dirty = None
        self._fx_active_prev = False
        self._fx_active = False
        self.follow_cursor = True
        self.pets = []
        self._build_pets()

        self._clock = QElapsedTimer()
        self._clock.start()
        self._last_ms = self._clock.elapsed()
        self._t = 0.0
        self._phys_acc = 0.0
        self._ts = 1.0                  # 0..1 插值因子
        self._hwnd = 0
        self._passthrough = None        # None 强制首次同步

        self.anim = QTimer(self)
        self.anim.setTimerType(Qt.TimerType.PreciseTimer)
        self.anim.setInterval(self._INT_FAST)
        self.anim.timeout.connect(self._tick)
        self.anim.start()

    # ── 构建：多宠 ──
    def _build_pets(self):
        """按存档与环境变量建猫。"""
        saved = self._params.get("pets")
        saved = list(saved) if isinstance(saved, list) and saved else None
        n = len(saved) if saved else 1
        env = os.environ.get("SLUGCATPET_PETS")
        if env:
            try:
                n = int(env)
            except ValueError:
                pass
        n = max(1, min(n, MAX_PETS))
        for i in range(n):
            state = saved[i] if saved and i < len(saved) else {}
            init_state = {"energy": state.get("energy", 1.0),
                          "temper": state.get("temper", 0.0),
                          "food": state.get("food", tuning.FOOD_INIT),
                          "karma": state.get("karma", tuning.KARMA_INIT),
                          "cold": state.get("cold", 0.0)}
            pet_id = state.get("id") or f"pet-{i}"
            variant = state.get("variant", "saint")
            spawn_x = self._WL * (i + 1) / (n + 1)   # n=1 时退化为 WL/2
            pet = PetUnit(self, i, pet_id, variant, init_state, spawn_x=spawn_x)
            if state.get("dead") and pet.behavior is not None:
                pet.behavior.enter_dead()
            self.pets.append(pet)

    # ── 单猫兼容别名 ──
    @property
    def body(self):
        return self.pets[0].body if self.pets else None

    @property
    def gfx(self):
        return self.pets[0].gfx if self.pets else None

    @property
    def tail(self):
        return self.pets[0].tail if self.pets else None

    @property
    def tongue(self):
        return self.pets[0].tongue if self.pets else None

    @property
    def behavior(self):
        return self.pets[0].behavior if self.pets else None

    # ── 坐标 ──
    def to_logical(self, dx, dy):
        return dx / self._scale, dy / self._scale

    def cursor_logical(self):
        g = self.mapFromGlobal(QCursor.pos())
        return self.to_logical(g.x(), g.y())

    # ── 动态穿透 ──
    def _update_passthrough(self):
        if self.debug:
            return
        if self._place_mode:
            return        # 放置模式接管点击，勿翻转
        from .control.mouse import is_over
        cur = self.cursor_logical()
        active = any(pet.behavior is not None and pet.behavior.grab.active for pet in self.pets)
        over_body = any(
            ((pet.behavior is None) or not pet.behavior.blocks_interaction())
            and is_over(pet.body, pet.gfx, cur, pad=6.0)
            for pet in self.pets)
        dragging_fruit = self._dragged_fruit is not None
        over_fruit = self._fruit_at(cur) is not None
        dragging_stone = self._dragged_stone is not None
        over_stone = self._stone_at(cur) is not None
        dragging_slime = self._dragged_slimemold is not None
        over_slime = self._slimemold_at(cur) is not None
        dragging_batfly = self._dragged_batfly is not None
        over_batfly = self._batfly_at(cur) is not None
        want = not (active or dragging_fruit or over_fruit or dragging_stone or over_stone
                    or dragging_slime or over_slime or dragging_batfly or over_batfly or over_body)
        if want != self._passthrough:
            self._passthrough = want
            if not self._hwnd:
                self._hwnd = int(self.winId())
            from .control.mouse import set_passthrough
            set_passthrough(self._hwnd, want)

    # ── 帧循环 ──
    _PHYS_DT = 1.0 / 40.0
    _MAX_TICKS = 4             # 防时间螺旋
    _MAX_DT = 0.1
    _INT_FAST = 25           # ms
    _INT_SLOW = 66
    _MOTION_STILL = 1.2
    MAX_FRUITS = 3
    MAX_STONES = 3

    def _scene_moving(self):
        """是否有物体在运动（供帧率自适应）。"""
        if self.room_gravity < 1.0:      # 无重力缓动中，保持高帧
            return True
        if self.water_surface is not None:   # 涨落或波未静，保持高帧
            if self.water_y != self.water_target or self.water_surface.energy() > tuning.WATER_STILL_EPS:
                return True
        for pet in self.pets:
            b = pet.body
            if (abs(b.chunk0.vx) + abs(b.chunk0.vy)
                    + abs(b.chunk1.vx) + abs(b.chunk1.vy)) > self._MOTION_STILL:
                return True
        for f in self.fruits:
            if abs(f.vx) + abs(f.vy) > self._MOTION_STILL:
                return True
        for s in self.stones:
            if abs(s.vx) + abs(s.vy) > self._MOTION_STILL:
                return True
        for m in self.slimemolds:
            if abs(m.vx) + abs(m.vy) > self._MOTION_STILL:
                return True
        for b in self.batflies:
            if abs(b.vx) + abs(b.vy) > self._MOTION_STILL:
                return True
        return False

    def edibles(self):
        """可食物体聚合（果+黏菌+蝙蝠）。"""
        return [*self.fruits, *self.slimemolds, *self.batflies]

    def _tick(self):
        now = self._clock.elapsed()
        dt = (now - self._last_ms) / 1000.0
        self._last_ms = now
        if dt <= 0.0:
            return
        if not self.isVisible():
            return
        self._update_passthrough()
        self._advance(min(dt, self._MAX_DT))
        region = self._update_region()
        dragging = self._dragged_fruit is not None or self._dragged_stone is not None
        grabbing = any(pet.behavior is not None and pet.behavior.grab.active for pet in self.pets)
        active = (self._fx_active or dragging or grabbing or self.isActiveWindow()
                  or self._scene_moving())
        want_iv = self._INT_FAST if active else self._INT_SLOW
        if self.anim.interval() != want_iv:
            # Precise 保平滑，Coarse 省功耗
            self.anim.stop()
            self.anim.setTimerType(Qt.TimerType.PreciseTimer if active
                                   else Qt.TimerType.CoarseTimer)
            self.anim.setInterval(want_iv)
            self.anim.start()
        if region is None:
            self.update()
        else:
            self.update(region)

    def _update_region(self):
        """整窗或脏矩形决策（None=整窗）。"""
        # 特效等超出包围盒需整窗刷
        pet_fx = any(pet.behavior is not None and pet.behavior.exclusive_fx() is not None
                     for pet in self.pets)
        fast_stone = any(s.state == ItemState.FREE and (abs(s.vx) + abs(s.vy)) > STONE_FAST_REDRAW
                         for s in self.stones)
        snow_active = self.snow_on and self._snow.active
        shake_active = self._shake[0] != 0.0 or self._shake[1] != 0.0
        fx_active = (pet_fx or self.sparks or self.shockwaves or self.fx or self.bubbles
                     or self.cursor_hijack is not None or self._place_mode or fast_stone
                     or self._any_kill_dialog()   # 舌头跨屏够弹窗
                     or snow_active
                     or shake_active)
        # 零重力/蝙蝠已含在 _dirty_rect，不放这里
        self._fx_active = bool(fx_active)
        if fx_active:
            self._prev_dirty = None   # 避免下一帧 united 出错误的小框
            self._fx_active_prev = True
            return None
        if self._fx_active_prev:
            # 特效落沿，再整窗刷一次清残影
            self._fx_active_prev = False
            self._prev_dirty = None
            return None
        r = self._dirty_rect()
        upd = r if self._prev_dirty is None else r.united(self._prev_dirty)
        self._prev_dirty = r
        return upd

    def _advance(self, dt):
        """dt 累加器推进物理，存插值因子。"""
        self._t += dt
        self._phys_acc += dt
        phys_dt = self._PHYS_DT
        ticks = 0
        while self._phys_acc >= phys_dt and ticks < self._MAX_TICKS:
            self._phys_acc -= phys_dt
            ticks += 1
            self._do_tick()
        # 余量/步长，[0,1)
        self._ts = min(self._phys_acc / phys_dt, 1.0)

    # ── 环境让位 ──
    def freeze_tick(self):
        """冻结物理 tick。"""
        self.anim.stop()

    def resume_tick(self):
        """解冻，重启 tick。"""
        self._last_ms = self._clock.elapsed()
        self.anim.start()

    # ── 环境适应 ──
    def apply_workspace(self, area, geo):
        """工作区变化，重算几何并夹回物体。"""
        geom = compute_geometry(area, geo, self._scale)
        self.world_version += 1
        self.geometry_version += 1
        self._area = area
        self._WL = geom["WL"]
        self._HL = geom["HL"]
        self._ground_inset = geom["ground_inset"] / self._scale if self._scale else 0.0
        self.resize(geom["win_w"], geom["win_h"])
        self.move(area.x(), area.y())
        self._reground(geom["WL"], geom["HL"])
        self._prev_dirty = None
        self.update()

    def _reground(self, WL, HL):
        """同步各猫与物体到新地面。"""
        for pet in self.pets:
            margin = pet.layout_data.canvas_w / 2.0
            b = pet.body
            b.W = WL
            b.H = HL
            b._floor_h = HL
            b.walk_min = margin
            b.walk_max = WL - margin
            b.visual_floor_y = HL
            _clamp_chunk_to_bounds(b.chunk0, WL, HL)
            _clamp_chunk_to_bounds(b.chunk1, WL, HL)
            pet.tail.floor_y = HL
            if pet.tongue is not None:
                pet.tongue.floor_y = HL
        for obj in (*self.fruits, *self.stones, *self.slimemolds, *self.batflies):
            _clamp_item_to_bounds(obj, WL, HL)

    def _do_tick(self):
        """推进一个物理 tick。"""
        # 抖动衰减，须在 impact 前
        self._shake[0] *= SHAKE_DECAY
        self._shake[1] *= SHAKE_DECAY
        if abs(self._shake[0]) + abs(self._shake[1]) < SHAKE_EPS:
            self._shake[0] = self._shake[1] = 0.0
        cur = self.cursor_logical()

        # 躲杀期间周期性抬窗到弹窗之上
        if self._any_kill_dialog():
            self._kill_raise_t = getattr(self, "_kill_raise_t", 0) + 1
            if self._kill_raise_t % 8 == 1:
                try:
                    self.raise_()
                except Exception:
                    pass

        self._zerog_update()
        cycle_prog = self._cold_update_world()
        self._water_update()          # 须在 pet.step 前

        for pet in self.pets:
            pet.step(cur, cycle_prog)

        self._tick_fruits()
        self._tick_stones()
        self._tick_slimemolds()
        self._tick_batflies()
        self._water_splash_detect()   # 须在物体积分后

        self._collide_objects()

        if self.lamp is not None:
            self.lamp.step()

        if self.snow_on:
            self._snow.step(self.cold_cycle_prog, self._WL, self._HL)

        self._update_fx()

    def set_zerog(self, on):
        """开/关无重力；开时摘掉所有果柄。"""
        self.zerog_on = bool(on)
        self.gravity_target = 0.0 if on else 1.0
        if self.zerog_on:
            for f in self.fruits:
                f.stalk = None
                if f.state == ItemState.HANGING:
                    f.state = ItemState.FREE

    def _zerog_update(self):
        """room_gravity 缓动向 target 并注入物体。"""
        rg = self.room_gravity + (self.gravity_target - self.room_gravity) * GRAV_EASE
        if abs(rg - self.gravity_target) < 1e-3:
            rg = self.gravity_target
        self.room_gravity = rg
        for f in self.fruits:
            f.room_gravity = rg
        for s in self.stones:
            s.room_gravity = rg
        for m in self.slimemolds:
            m.room_gravity = rg
        for b in self.batflies:
            b.room_gravity = rg

    def set_water(self, on):
        """开/关水。"""
        self.water_on = bool(on)
        self.water_target = (self._HL - self._HL * tuning.WATER_FULL_DEPTH) if on else self._HL
        if on and self.water_surface is None:
            self.water_y = self._HL
            self.water_surface = WaterSurface(self._WL, self._HL, tuning.WATER_SPACING)

    def spawn_bubble(self, x, y, vx, vy):
        """生成一个上浮气泡。"""
        if self.water_surface is None or len(self.bubbles) >= tuning.BUBBLE_MAX:
            return
        from .world.bubbles import Bubble
        self.bubbles.append(Bubble(x, y, vx, vy, self._bubble_rng))

    def _water_update(self):
        """water_y 逼近 target 并推进水面。"""
        surf = self.water_surface
        if surf is None:
            return
        rate = self._HL * tuning.WATER_FULL_DEPTH / tuning.WATER_EASE_TICKS
        target = self.water_target
        moving = abs(self.water_y - target) > 1e-6
        if self.water_y < target:
            self.water_y = min(self.water_y + rate, target)
        elif self.water_y > target:
            self.water_y = max(self.water_y - rate, target)
        # 排空到底则释放
        if not self.water_on and self.water_y >= self._HL - 0.5:
            self.water_surface = None
            self.water_y = None
            self.bubbles = []
            for o in (*self.fruits, *self.stones, *self.slimemolds, *self.batflies):
                o.water_y = None
            for pet in self.pets:
                pet.body.water_surface = None
                pet.body.bubble_cb = None
            return
        surf.base_y = self.water_y
        if moving:                                   # 注满/排空搅面
            if self.water_on:
                surf.waterfall_hit(0.0, self._WL, tuning.WATER_FLOW)
            else:
                surf.drain_affect(0.0, self._WL, tuning.WATER_FLOW)
        surf.step()
        for o in (*self.fruits, *self.stones, *self.slimemolds, *self.batflies):
            o.water_y = surf.level_at(o.x)
        for pet in self.pets:
            pet.body.water_surface = surf
            pet.body.bubble_cb = self.spawn_bubble

    def _water_splash_detect(self):
        """穿越水面激起入水溅。"""
        surf = self.water_surface
        if surf is None or surf.splash_stop > 0:
            return
        objs = []
        for pet in self.pets:
            b = pet.body
            objs.append(b.chunk0)
            objs.append(b.chunk1)
        for f in self.fruits:
            if f.state in (ItemState.FREE, ItemState.HANGING):
                objs.append(f)
        for s in self.stones:
            if s.state == ItemState.FREE:
                objs.append(s)
        for m in self.slimemolds:
            if m.state in (ItemState.FREE, ItemState.HANGING):
                objs.append(m)
        for b in self.batflies:
            if b.state == ItemState.FREE:
                objs.append(b)
        for o in objs:
            lvl = surf.level_at(o.x)
            vy = o.vy
            if vy > 3.0 and o.last_y < lvl <= o.y:
                pass                                 # 向下穿越（y↓）
            elif vy < -3.0 and o.last_y > lvl >= o.y:
                pass                                 # 向上穿越
            else:
                continue
            impulse = lerp(vy * o.rad * lerp(o.mass, 1.0, 0.3) / 3.0, 10.0, 0.5)
            if abs(impulse) > abs(vy):
                impulse = vy
            surf.splash(o.x, impulse)
            if abs(impulse) > 5.0:
                surf.ripple_ring(o.x)
            surf.splash_stop = 10
            break                                    # 每 tick 只溅一次

    def _shake_impact(self, chunk, direction, speed, strength, ix, iy):
        """地形硬撞回调，累加抖动偏移。"""
        self._shake[0] = clampf(self._shake[0] + ix, -SHAKE_MAX, SHAKE_MAX)
        self._shake[1] = clampf(self._shake[1] + iy, -SHAKE_MAX, SHAKE_MAX)

    def _cold_update_world(self):
        """暴风雪三角计时推进，返回 cycle_prog。"""
        cycle_prog = 0.0
        if self.blizzard_on:
            self.blizzard_timer += 1
            if self.blizzard_timer >= tuning.COLD_BLIZZARD_TOTAL:
                self.blizzard_on = False
                self.blizzard_timer = 0
                if self.env_target == "blizzard":     # 自停后目标回落，防被重新点燃
                    self.env_target = "none"
                sp = getattr(self, "_settings_panel", None)
                if sp is not None and hasattr(sp, "refresh_env"):
                    sp.refresh_env()
            else:
                ramp = tuning.COLD_BLIZZARD_RAMP
                hold_end = tuning.COLD_BLIZZARD_TOTAL - ramp
                t = self.blizzard_timer
                if t < ramp:
                    cycle_prog = t / ramp
                elif t < hold_end:
                    cycle_prog = 1.0
                else:
                    cycle_prog = 1.0 - (t - hold_end) / ramp
        self.cold_cycle_prog = cycle_prog
        return cycle_prog

    def _tick_fruits(self):
        """推进放果子物理。"""
        self._step_fruit_drag()
        if self.fruits:
            for f in self.fruits:
                f._impact_cb = self._shake_impact
                f.step(self._WL, self._HL)
            self.fruits = [f for f in self.fruits if f.state != ItemState.EATEN]

    def _tick_stones(self):
        """推进放石头物理。"""
        self._step_stone_drag()
        if self.stones:
            for s in self.stones:
                s._impact_cb = self._shake_impact
                s.step(self._WL, self._HL)
            self._step_stone_hit()
            self._step_stone_cursor_hit()
            self.stones = [s for s in self.stones if s.state != ItemState.GONE]

    def _tick_slimemolds(self):
        """推进放黏菌物理。"""
        self._step_slimemold_drag()
        if self.slimemolds:
            for m in self.slimemolds:
                m._impact_cb = self._shake_impact
                m.step(self._WL, self._HL)
            self.slimemolds = [m for m in self.slimemolds if m.state != ItemState.EATEN]

    def _tick_batflies(self):
        """推进放蝙蝠物理。"""
        self._step_batfly_drag()
        if self.batflies:
            for b in self.batflies:
                b._impact_cb = self._shake_impact
                b.step(self._WL, self._HL)
            self._step_batfly_shove()
            self.batflies = [b for b in self.batflies if b.state != ItemState.EATEN]

    def _collide_objects(self):
        """物体间通用碰撞互推。"""
        chunkphys.collide_objects([*(pet.body for pet in self.pets),
                                   *self.fruits, *self.stones, *self.slimemolds])

    # ── 按猫杀死编排 ──
    def _any_kill_dialog(self):
        return any(getattr(p, "_kill_dialog", None) is not None for p in self.pets)

    def request_kill(self, pet):
        """弹该猫的杀死确认弹窗。"""
        if pet.behavior is None or pet._kill_dialog is not None:
            return
        from .i18n import t
        from .ui.dialogs import ConfirmDialog
        from .ui.catmenu import pet_label
        dlg = ConfirmDialog(t("dlg_confirm_title"),
                            t("dlg_kill_text", name=pet_label(pet, list(self.pets))),
                            t("dlg_kill_yes"), t("dlg_kill_no"), parent=self)
        dlg.finished.connect(lambda result, p=pet: self._on_pet_kill_finished(p, result))
        pet._kill_dialog = dlg            # 供 FSM 舌点取消
        n = sum(1 for p in self.pets if p is not pet and p._kill_dialog is not None)
        dlg.place_center(offset=QPoint(48 * n, 48 * n))   # 多弹窗错位
        dlg.show()
        dlg.activateWindow()              # Esc 即刻可用
        try:
            self.raise_()                 # 提到弹窗之上
        except Exception:
            pass

    def _on_pet_kill_finished(self, pet, result):
        from PySide6.QtWidgets import QDialog
        box = pet._kill_dialog
        pet._kill_dialog = None
        silent = pet._kill_dismiss_silent
        pet._kill_dismiss_silent = False
        do_kill = (result == QDialog.DialogCode.Accepted)
        by_saint = pet._kill_cancel_by_saint
        pet._kill_cancel_by_saint = False
        if box is not None:
            box.deleteLater()
        if pet.behavior is None:
            return
        if do_kill:
            pet.behavior.kill()
        elif not silent:                  # 静默消解不扣好感
            pet.behavior.kill_threat_canceled(by_saint)

    # ── 增删猫 ──
    def add_pet(self, variant="saint"):
        """新增一只猫，满员返回 None。"""
        if len(self.pets) >= MAX_PETS:
            return None
        used_idx = {p.index for p in self.pets}
        used_id = {p.id for p in self.pets}
        k = 0
        while k in used_idx or f"pet-{k}" in used_id:   # 取首个空缺整数
            k += 1
        init_state = {"energy": 1.0, "temper": 0.0, "food": tuning.FOOD_INIT,
                      "karma": tuning.KARMA_INIT, "cold": 0.0}
        margin = self.layout_data.canvas_w / 2.0
        lo, hi = margin, max(margin + 1.0, self._WL - margin)
        spawn_x = clampf(random.uniform(lo, hi), 0.0, self._WL)
        pet = PetUnit(self, k, f"pet-{k}", variant, init_state, spawn_x=spawn_x)
        self.pets.append(pet)
        self._prev_dirty = None
        self._after_pets_changed()
        return pet

    def remove_pet(self, pet):
        """移除一只猫，成功返回 True。"""
        if len(self.pets) <= 1 or pet not in self.pets:
            return False
        if getattr(pet, "controlled", False):
            self.stop_control()               # 先退出控制再移除
        self._drop_carried(pet)
        pet.dismiss_kill_dialog()             # 静默消解挂起弹窗
        if pet.behavior is not None:          # 收尾行为控制器
            try:
                pet.behavior._break_active_controllers()
                pet.behavior.grab.force_release()
            except Exception:
                pass
        self.pets.remove(pet)
        self._prev_dirty = None
        self._after_pets_changed()
        return True

    def _drop_carried(self, pet):
        """持有物原地转 free。"""
        b = pet.body
        if b.carried_fruit is not None:
            b.carried_fruit.stalk = None
            b.carried_fruit.state = "free"
            b.carried_fruit.held_by_hand = None
            b.release_fruit()
        if b.carried_stone is not None:
            b.release_stone(to_free=True)

    def _after_pets_changed(self):
        hud = self._hud
        if hud is not None and hasattr(hud, "rebuild_rows"):
            hud.rebuild_rows()
        if self._pets_changed_cb is not None:
            try:
                self._pets_changed_cb()
            except Exception:
                pass
        self.update()

    # ── 单猫操作菜单 ──
    def open_cat_menu(self, pet, global_pos):
        from .ui.catmenu import build_cat_menu
        menu = build_cat_menu(pet, self.pets, open_settings=self.open_settings, parent=self)
        menu.exec(global_pos)

    def open_settings(self):
        if self._open_settings_cb is not None:
            self._open_settings_cb()

    # ── 手动操控 ──
    def controlled_pet(self):
        """当前受控猫；无则 None。"""
        for pet in self.pets:
            if getattr(pet, "controlled", False):
                return pet
        return None

    def start_control(self, pet):
        """开始控制该猫。"""
        if pet is None or pet not in self.pets or getattr(pet, "controlled", False):
            return
        if pet._kill_dialog is not None:
            return
        beh = pet.behavior
        if beh is None or beh.is_truly_dead() or beh.is_reincarnating() or beh.blocks_interaction():
            return
        self.stop_control()
        from .control.session import enter_control
        from .ui.controlhud import ControlHud
        hud = ControlHud(self, pet)
        enter_control(pet, hud.current_input)
        self._control_hud = hud
        hud.show()      # 须同步执行，勿 QTimer 推迟

    def stop_control(self):
        """退出控制（幂等）。"""
        hud = self._control_hud
        self._control_hud = None
        pet = self.controlled_pet()
        if pet is not None:
            from .control.session import exit_control
            exit_control(pet)
        if hud is not None:
            hud.close()
            hud.deleteLater()

    def _dirty_rect(self):
        """计算全部在场物体的脏矩形，绘制取 last..cur 插值。"""
        xs, ys = [], []

        def put(x, y, lx, ly):
            xs.append(x); ys.append(y)
            xs.append(lx); ys.append(ly)

        for pet in self.pets:
            b, g = pet.body, pet.gfx
            for c in (b.chunk0, b.chunk1):
                put(c.x, c.y, c.last_x, c.last_y)
            put(g.head.x, g.head.y, g.head.lx, g.head.ly)
            for h in g.hands:
                put(h.x, h.y, h.lx, h.ly)
            xs.append(2.0 * b.chunk1.x - g.head.x)       # 镜像极值
            xs.append(2.0 * b.chunk1.last_x - g.head.lx)
            for s_ in pet.tail.segs:
                put(s_.x, s_.y, s_.lx, s_.ly)
            if pet.tongue is not None:
                for px, py in pet.tongue.positions():
                    xs.append(px); ys.append(py)
            rope = getattr(g, "_tongue_rope", None)
            if rope is not None:
                for px, py in rope:
                    xs.append(px); ys.append(py)
        for f in self.fruits:
            r = f.rad
            put(f.x - r, f.y - r, f.last_x - r, f.last_y - r)
            put(f.x + r, f.y + r, f.last_x + r, f.last_y + r)
            if f.stalk is not None:
                for px, py in f.stalk.points():
                    xs.append(px); ys.append(py)
        for st in self.stones:
            r = st.rad
            put(st.x - r, st.y - r, st.last_x - r, st.last_y - r)
            put(st.x + r, st.y + r, st.last_x + r, st.last_y + r)
        for m in self.slimemolds:
            gr = 70.0
            put(m.x - gr, m.y - gr, m.last_x - gr, m.last_y - gr)
            put(m.x + gr, m.y + gr, m.last_x + gr, m.last_y + gr)
            for t in m.tendrils:
                xs.append(t[0]); ys.append(t[1])
        for b in self.batflies:
            wr = 40.0                      # 翅展 pad
            put(b.x - wr, b.y - wr, b.last_x - wr, b.last_y - wr)
            put(b.x + wr, b.y + wr, b.last_x + wr, b.last_y + wr)
            put(b.lower_x - wr, b.lower_y - wr, b.last_lower_x - wr, b.last_lower_y - wr)
            put(b.lower_x + wr, b.lower_y + wr, b.last_lower_x + wr, b.last_lower_y + wr)
        for pl in self.poles:
            xs.append(pl.ax); xs.append(pl.bx)
            ys.append(pl.ay); ys.append(pl.by)
        lamp = self.lamp
        if lamp is not None:
            gr = lamp.glow_radius()
            xs.append(lamp.anchor_x); xs.append(lamp.bulb_x)
            ys.append(lamp.anchor_y); ys.append(lamp.bulb_y)
            xs.append(lamp.bulb_x - gr); xs.append(lamp.bulb_x + gr)
            ys.append(lamp.bulb_y - gr); ys.append(lamp.bulb_y + gr)
        surf = self.water_surface
        if surf is not None:
            # 仅涨落/波动时并入全宽水带
            if self.water_y != self.water_target or surf.energy() > tuning.WATER_STILL_EPS:
                xs.append(0.0); xs.append(self._WL)
                ys.append(self.water_y - 40.0); ys.append(self._HL + self._ground_inset)
        s = self._scale
        pad = 60
        x0 = int((min(xs) - pad) * s); y0 = int((min(ys) - pad) * s)
        x1 = int((max(xs) + pad) * s); y1 = int((max(ys) + pad) * s)
        return QRect(x0, y0, x1 - x0, y1 - y0)

    def _draw_water(self, p):
        """绘制水体与水面高光。"""
        from PySide6.QtGui import QPolygonF, QPen
        surf = self.water_surface
        n = surf.n
        WL = self._WL
        bottom = self._HL + self._ground_inset
        base = surf.base_y
        h = surf.height
        pts = []
        for i in range(n):
            x = surf.point_x(i)
            if x > WL:
                x = WL
            pts.append((x, base + h[i]))
        poly = QPolygonF()
        for x, y in pts:
            poly.append(QPointF(x, y))
        poly.append(QPointF(WL, bottom))
        poly.append(QPointF(0.0, bottom))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(*tuning.WATER_BODY_RGBA))
        p.drawPolygon(poly)
        if self.bubbles:
            self._draw_bubbles(p)
        # 一次性画折线，防重叠叠 alpha
        pen = QPen(QColor(*tuning.WATER_SURFACE_RGBA))
        pen.setWidthF(2.0)
        p.setPen(pen)
        line = QPolygonF()
        for x, y in pts:
            line.append(QPointF(x, y))
        p.drawPolyline(line)

    def _draw_bubbles(self, p):
        """绘制溺水气泡。"""
        ts = self._ts
        p.save()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.setOpacity(tuning.BUBBLE_OPACITY)
        for b in self.bubbles:
            x = b.last_x + (b.x - b.last_x) * ts
            y = b.last_y + (b.y - b.last_y) * ts
            sc = b.full_size * tuning.BUBBLE_DRAW_SCALE
            blit(p, self.atlas, "LizardBubble5", x, y, 0.0, sc, sc,
                 tuning.BUBBLE_RGBA, ax=0.5, ay=0.5)
        p.restore()

    def paintEvent(self, _):
        # 图层序：果绳/烟 → 猫身 → 杆/手 → 果石黏菌蝠 → 水 → 灯 → 特效 → 雪
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            p.scale(self._scale, self._scale)
            if self._shake[0] or self._shake[1]:
                p.translate(self._shake[0], self._shake[1])

            if self.fruits:
                self._draw_fruit_ropes(p)

            self._draw_fx_under(p)

            for pet in self.pets:
                fx = pet.behavior.exclusive_fx() if pet.behavior is not None else None
                if fx is not None:
                    fx.draw_under(p, self._ts)
                pet.gfx.draw_sprites(p, self.atlas, timeStacker=self._ts)

            if self.poles:
                self._draw_poles(p)
            for pet in self.pets:
                pet.gfx._draw_hand_grips(p, self.atlas, self._ts)

            if self.fruits:
                self._draw_fruits(p)
            if self.stones:
                self._draw_stones(p)
            if self.slimemolds:
                self._draw_slimemolds(p)
            if self.batflies:
                self._draw_batflies(p)

            if self.water_surface is not None:
                self._draw_water(p)

            if self.lamp is not None:
                self._draw_lamp(p)

            self._draw_fx(p)

            if self.snow_on:
                self._snow.draw(p, self._WL, self._HL, self._scale)

            if self._place_mode:
                self._draw_place_hint(p)

        finally:
            p.end()

    def mousePressEvent(self, e):
        if self._place_mode:
            if e.button() == Qt.MouseButton.LeftButton:
                lx, ly = self.to_logical(e.position().x(), e.position().y())
                if self._place_kind in ("vpole", "hpole"):
                    self.place_pole(lx, ly, self._place_kind)
                elif self._place_kind == "stone":
                    self.place_stone(lx, ly)
                elif self._place_kind == "lamp":
                    self.place_lamp(lx, ly)
                elif self._place_kind == "slimemold":
                    self.place_slimemold(lx, ly)
                elif self._place_kind == "batfly":
                    self.place_batfly(lx, ly)
                else:
                    self.place_fruit(lx, ly)
            elif e.button() == Qt.MouseButton.RightButton:
                self._exit_place_mode()
            return
        if not self.pets:
            return
        if e.button() == Qt.MouseButton.RightButton:
            # 右键命中区同左键抓取
            pos = self.to_logical(e.position().x(), e.position().y())
            from .control.mouse import hit_test, GRAB_PAD
            for pet in self.pets:
                if pet.behavior is not None and pet.behavior.blocks_interaction():
                    continue
                name, _ = hit_test(pet.body, pet.gfx, pos, pad=GRAB_PAD)
                if name is not None:
                    self.open_cat_menu(pet, e.globalPosition().toPoint())
                    return
            return
        if e.button() == Qt.MouseButton.LeftButton:
            pos = self.to_logical(e.position().x(), e.position().y())
            grabbed = False
            for pet in self.pets:
                if getattr(pet, "controlled", False):
                    continue        # 受控猫禁左键抓取
                if pet.behavior is not None and pet.behavior.on_press(pos):
                    grabbed = True
                    break
            if not grabbed:
                # 蝙蝠优先级最高
                if not self._begin_batfly_drag(pos):
                    if not self._begin_fruit_drag(pos):
                        if not self._begin_stone_drag(pos):
                            self._begin_slimemold_drag(pos)

    def keyPressEvent(self, e):
        if self._place_mode and e.key() == Qt.Key.Key_Escape:
            self._exit_place_mode()
            return
        super().keyPressEvent(e)

    def mouseReleaseEvent(self, e):
        if not self.pets:
            return
        if e.button() == Qt.MouseButton.LeftButton:
            for pet in self.pets:
                if pet.behavior is not None:
                    pet.behavior.on_release()
            self._end_fruit_drag()
            self._end_stone_drag()
            self._end_slimemold_drag()
            self._end_batfly_drag()
