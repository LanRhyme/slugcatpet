"""单只宠物实例。"""
from __future__ import annotations
import math
import random

from .behavior import tuning
from .cats import get as get_cat_def
from .cats.saint.tongue import Tongue
from .control.vmath import dirvec
from .core.creature import SlugcatBody
from .rendering.graphics import SlugcatGraphics
from .rendering.layout import Layout
from .core.tail import Tail
from .core.units import clampf, inv_lerp, lerp, K_VEL
from .world.lamp import WARM_INNER, WARM_RADIUS

TAIL_SNAP = 40.0
TONGUE_POINTS = 20
TONGUE_ROOT_W = 1.8
TONGUE_TIP_W = 0.3

ZEROG_ROOM_GRAVITY = 0.5     # 判为零重力的阈值
# 零重力甩尾
ZEROG_TAIL_RATE = 0.08
ZEROG_TAIL_AMP0 = 0.4
ZEROG_TAIL_AMP1 = 0.16


def _taper(n, root_w, tip_w):
    return [root_w + (tip_w - root_w) * (i / (n - 1)) for i in range(n)]


class PetUnit:
    """一只猫，独立身体/图形/行为。"""

    def __init__(self, window, index: int, pet_id: str, variant: str, init_state: dict,
                 spawn_x: float | None = None):
        self.window = window
        self.index = index
        self.id = pet_id
        self.variant = variant
        self.cat = get_cat_def(variant)     # 种族定义
        self._reincarnate_pending = False
        self._cramp_delay = -1                              # <0 才可再抽
        self._cold_rng = random.Random(0xC01D + index)      # 确定性
        self._kill_dialog = None            # 本猫杀死确认弹窗
        self._kill_cancel_by_saint = False
        self._kill_dismiss_silent = False   # 静默消解，跳过扣好感
        self.controlled = False
        self.behavior = None
        self._build(init_state, spawn_x)
        self._attach_behavior()

    def __getattr__(self, name):
        """无此属性则转发到 window。"""
        if name == "window":
            raise AttributeError(name)
        return getattr(self.window, name)

    # ── 构建 ──
    def _build(self, init_state: dict, spawn_x: float | None = None):
        w = self.window
        self.layout_data = Layout.for_cat(self.cat)   # 部件摆位
        cx = spawn_x if spawn_x is not None else w._WL / 2.0
        floor_y = w._HL
        self.body = SlugcatBody((cx, floor_y), w._WL, floor_y,
                                energy=init_state.get("energy", 1.0),
                                temper=init_state.get("temper", 0.0),
                                food=init_state.get("food"),
                                karma=init_state.get("karma"),
                                stats=self.cat.stats)
        self.body.cold = float(init_state.get("cold", 0.0))
        self.body.visual_floor_y = floor_y
        # 趴姿悬空几何补偿
        from .core import chunkphys as _cp
        _hips_half_w = w.atlas.source_size("base", "HipsA")[0] / 2.0
        _crawl_draw_raise = 4.0  # Crawl 上抬均值
        self.body.crawl_sink = _cp.RAD1 - _hips_half_w + _crawl_draw_raise
        margin = self.layout_data.canvas_w / 2.0
        self.body.walk_min = margin
        self.body.walk_max = w._WL - margin
        self.gfx = SlugcatGraphics(self.body, self.layout_data, w.atlas, cat=self.cat)
        # 让站姿先收敛
        for _ in range(40):
            self.body.step()
            self.gfx.update()
        # 尾巴/舌头（caps.tongue 关则不建）
        ax, ay = self.gfx.tail_root_world()
        self.tail = Tail(ax, ay)
        self.tail.floor_y = floor_y
        self._prev_root = (ax, ay)
        if self.cat.caps.tongue:
            mx, my = self.gfx.mouth_world()
            self.tongue = Tongue(mx, my, TONGUE_POINTS,
                                 _taper(TONGUE_POINTS, TONGUE_ROOT_W, TONGUE_TIP_W))
            self.tongue.floor_y = floor_y
            self.tongue.body = self.body        # 供零重力吐舌自推进
        else:
            self.tongue = None
        self.gfx.tail_segs = self.tail.segs
        self.gfx.tongue = self.tongue
        # 鳃（caps.gills 关则不建）
        if self.cat.caps.gills:
            from .cats.rivulet.gills import Gills
            gh = w.atlas.source_size("base", "LizardScaleA3")[1]
            self.gills = Gills(self.body.chunk0.x, self.body.chunk0.y,
                               self.body.chunk1.x, self.body.chunk1.y, gh)
        else:
            self.gills = None
        self.gfx.gills = self.gills
        self.body.impact_cb = w._shake_impact   # 地形硬撞→窗口抖动
        self._zerog_tail_phase = 0.0

    def _attach_behavior(self):
        try:
            from .behavior.fsm import BehaviorFSM
        except Exception:
            self.behavior = None
            return
        self.behavior = BehaviorFSM(self)

    def respawn(self, preserve=False):
        """重置本猫（preserve=True 保留体征）。"""
        if self.controlled:              # 先退控制，防丢 provider
            from .control.session import exit_control
            exit_control(self)
        self.dismiss_kill_dialog()       # 静默消解挂起弹窗
        w = self.window
        if preserve:
            b = self.body
            init_state = {"energy": b.energy, "temper": b.temper,
                          "food": b.food, "karma": b.karma}
        else:
            init_state = {"energy": 1.0, "temper": 0.0,
                          "food": tuning.FOOD_INIT, "karma": tuning.KARMA_INIT}
        self._build(init_state)
        self._attach_behavior()
        w._prev_dirty = None             # 强制整窗重绘
        w.update()

    # ── 杀死确认弹窗 ──
    def _kill_cancel_button(self):
        box = self._kill_dialog
        return None if box is None else getattr(box, "cancel_btn", None)

    def kill_cancel_target(self):
        """取消按钮中心的世界坐标，缺失返回 None。"""
        btn = self._kill_cancel_button()
        if btn is None:
            return None
        w = self.window
        try:
            g = btn.mapToGlobal(btn.rect().center())
            local = w.mapFromGlobal(g)
            return w.to_logical(local.x(), local.y())
        except Exception:
            return None

    def click_kill_cancel(self):
        """程序点击本猫取消按钮。"""
        btn = self._kill_cancel_button()
        if btn is not None:
            self._kill_cancel_by_saint = True
            btn.click()

    def dismiss_kill_dialog(self):
        """静默消解本猫死亡弹窗。"""
        box = self._kill_dialog
        if box is not None:
            self._kill_dismiss_silent = True
            box.reject()          # 触发 finished 回调

    # ── 每 tick 推进 ──
    def step(self, cursor, cycle_prog):
        if self.controlled and self.body.dead:
            # 死须先退控制再转世
            from .control.session import exit_control
            exit_control(self)
        if self._reincarnate_pending:
            self._reincarnate_pending = False
            self.respawn(preserve=True)   # 体征保留，cold 归 0
            return
        w = self.window
        b, g = self.body, self.gfx
        if self.controlled:
            # FSM 冻结期同步晕态
            g.stunned = b.stun > 0
            g.look_at = None
        elif self.behavior is not None:
            self.behavior.update(cursor)
        elif w.follow_cursor:
            g.look_at = cursor

        if self.tongue is not None:
            mox, moy = g.mouth_world()
            # 游泳态禁舌，落水自救例外
            escaping = (self.behavior is not None and self.behavior.state == "TongueClimb")
            if b.swimming and not escaping:
                self.tongue.retract()
                self.tongue.update(mox, moy, b.chunk0)
                b.suspended = False
            else:
                self.tongue.update(mox, moy, b.chunk0)
                # 尸体不被舌头吊住
                b.suspended = self.tongue.attached and not b.dead and not b.swimming
        else:
            b.suspended = False

        # water_surface 由 window 每 tick 注入
        rg = w.room_gravity
        b.room_gravity = rg
        b.zerog = rg < ZEROG_ROOM_GRAVITY
        if self.tongue is not None:
            self.tongue.room_gravity = rg

        b.step()
        self._cold_update(cycle_prog)
        g.update()
        if self.gills is not None:
            self.gills.update(b.chunk0.x, b.chunk0.y, b.chunk1.x, b.chunk1.y,
                              g.look_dir[0], g.look_dir[1],
                              submerged=b.head_sub > 0.5,
                              flat_anchor=g.gills_flat)
        g.update_tongue_rope()
        self._tick_tail()

    def _cold_update(self, cycle_prog):
        """本猫每 tick 寒冷结算。"""
        w = self.window
        b = self.body

        if b.dead:
            b.cold_gain = 0.0
            return

        blizzard_active = w.blizzard_on and cycle_prog > 0.0
        exposure = tuning.COLD_EXPOSURE

        cold_gain = 0.0
        lamp = w.lamp
        in_warm_zone = False
        d_hip = 0.0
        lamp_range = WARM_RADIUS
        warm_inner = WARM_INNER
        if lamp is not None:
            d_hip = lamp.dist_to(b.chunk1.x, b.chunk1.y)
            in_warm_zone = lamp.in_warm_zone(b.chunk1.x, b.chunk1.y)

        if blizzard_active and not in_warm_zone:
            # (1) 冷度累积
            cg = lerp(0.0, 0.00005, inv_lerp(0.1, 0.95, cycle_prog))
            cg += lerp(0.0, 0.0016, cycle_prog)
            g_div = lerp(9100.0, 5350.0, cycle_prog)
            cg += exposure / g_div
            cg += exposure / 8200.0
            cg = lerp(0.0, cg, inv_lerp(-0.5, 1.0, cycle_prog))
            cg *= inv_lerp(50.0, -10.0, b.total_mass)
            if b.cold > 0.8:
                cg *= 0.5
            cg *= self.cat.personality.cold_gain_fac    # 低=更耐寒
            cg = clampf(cg, -1.0, tuning.COLD_GAIN_CLAMP_HI)             # 勿改
            cold_gain = cg
            b.cold += cg
            # (2) 轻量抽搐
            conscious = b.stun < 10 and not b.dead
            if b.cold >= 0.8 and conscious:
                if cg > tuning.COLD_CRAMP_GAIN_GATE:                     # 勿改
                    if self._cramp_delay < 0:
                        st = int(lerp(5.0, 60.0, b.cold ** 8))   # 满冷→st 60
                        self._cramp_delay = int(self._cold_rng.uniform(
                            300 - b.cold * 240, 500 - b.cold * 200))
                        b.stun = max(b.stun, st)
                else:
                    self._cramp_delay = self._cold_rng.randint(200, 499)
            self._cramp_delay -= 1
            # (3) 冻死
            if b.cold >= 1.0 and b.stun > tuning.COLD_DEATH_STUN and not b.dead:
                if self.behavior is not None and hasattr(self.behavior, "kill_cold"):
                    self.behavior.kill_cold()
        else:
            # 回暖
            if in_warm_zone and b.cold > 0.001:
                f = inv_lerp(lamp_range, warm_inner, d_hip)
                b.cold = max(b.cold - tuning.COLD_LAMP_WARMTH * f, 0.0)
            if b.cold > 1.0:
                b.cold = 1.0
            b.cold = lerp(b.cold, 0.0, tuning.COLD_NATURAL_DECAY)
        b.cold_gain = cold_gain
        b.clamp_cold()

    def _tick_tail(self):
        """尾巴跟随，顺序固定。"""
        b, g = self.body, self.gfx
        rx, ry = g.draw1[0], g.draw1[1]   # 接到臀部渲染位
        if math.hypot(rx - self._prev_root[0], ry - self._prev_root[1]) > TAIL_SNAP:
            self.tail.snap_to(rx, ry)
        # 松弛度：1=下垂摆动，0=贴流线
        if b.chunk0.pinned or b.chunk1.pinned or b.suspended or b.hover:
            looseness = 1.0
        elif b.bodyMode == "Stand":
            vx_norm = abs(b.chunk1.vx) / K_VEL
            looseness = 1.0 - clampf((vx_norm - 1.0) * 0.5, 0.0, 1.0)
        elif b.bodyMode == "Crawl":
            looseness = 1.0
        elif b.bodyMode == "ClimbingOnBeam":
            looseness = 1.0   # 漏此分支尾巴发僵
        elif b.bodyMode == "ZeroG":
            looseness = 1.0   # 漏此分支尾巴发僵
        else:
            looseness = 0.0   # 空中无动画
        # 尾扇出参照点切换
        ref_x, ref_y = b.chunk0.x, b.chunk0.y
        if (b.bodyMode == "Stand"
                and abs(b.chunk0.vx) / K_VEL > 2.0 and abs(b.chunk1.vx) / K_VEL > 2.0):
            ref_x = b.chunk1.x + b.facing * 16.0 * clampf(abs(b.chunk1.vx) / K_VEL - 0.2, 0.0, 1.0)
            ref_y = b.chunk1.y + 4.0
        self.tail.step(rx, ry, b.chunk1.x, b.chunk1.y, ref_x, ref_y, looseness,
                       gravity_norm=self.window.room_gravity)   # 零重力不朝世界下耷拉
        if b.bodyMode == "ZeroG":
            self._apply_zerog_tail_sway(b)
        g._apply_sleep_tail_curl()   # 须在 tail.step 之后
        self._prev_root = (rx, ry)
        if b.animation in ("Roll", "Flip"):
            # 滚/翻尾巴拖尾力
            vx, vy = dirvec(b.chunk0.x, b.chunk0.y, b.chunk1.x, b.chunk1.y)
            f = 6.0
            for seg in self.tail.segs:
                seg.vx += vx * f
                seg.vy += vy * f
                f /= 1.7

    def _apply_zerog_tail_sway(self, b):
        """零重力甩尾。"""
        self._zerog_tail_phase += ZEROG_TAIL_RATE
        ax, ay = b.chunk0.x - b.chunk1.x, b.chunk0.y - b.chunk1.y   # 体轴
        d = math.hypot(ax, ay) or 1.0
        px, py = -ay / d, ax / d                                    # 垂体轴单位向量
        s = math.sin(self._zerog_tail_phase)
        segs = self.tail.segs
        segs[0].vx += px * ZEROG_TAIL_AMP0 * s
        segs[0].vy += py * ZEROG_TAIL_AMP0 * s
        if len(segs) > 1:
            segs[1].vx += px * ZEROG_TAIL_AMP1 * s
            segs[1].vy += py * ZEROG_TAIL_AMP1 * s

    # ── 舌头 ──
    def fire_tongue(self, tx, ty):
        """朝 (tx,ty) 甩/收舌。"""
        if self.tongue is None:
            return
        if self.tongue.is_idle():
            hx, hy, hit = self._ray_hit_edge(self.body.chunk0.x, self.body.chunk0.y, tx, ty)
            mox, moy = self.gfx.mouth_world()
            self.tongue.shoot(mox, moy, hx, hy, hit)
        else:
            self.tongue.retract()

    def fire_tongue_at(self, px, py) -> bool:
        """直接朝世界点钉舌，返回是否射出。"""
        if self.tongue is None:
            return False
        mox, moy = self.gfx.mouth_world()
        return self.tongue.shoot(mox, moy, px, py, hit=True)

    def fire_tongue_at_obj(self, fruit) -> bool:
        """射舌粘住果子，返回是否射出。"""
        if self.tongue is None:
            return False
        mox, moy = self.gfx.mouth_world()
        return self.tongue.shoot(mox, moy, fruit.x, fruit.y, hit=True, obj=fruit)

    def _ray_hit_edge(self, mx, my, cx, cy):
        w = self.window
        WL, H = w._WL, w._HL
        dx, dy = cx - mx, cy - my
        d0 = math.hypot(dx, dy)
        ux, uy = (0.0, -1.0) if d0 < 1e-6 else (dx / d0, dy / d0)
        eps = 1e-6
        best = None
        if uy < -eps:
            t = (0.0 - my) / uy
            if t > 0 and 0 <= mx + ux * t <= WL:
                best = t
        if ux < -eps:
            t = (0.0 - mx) / ux
            if t > 0 and 0 <= my + uy * t <= H and (best is None or t < best):
                best = t
        if ux > eps:
            t = (WL - mx) / ux
            if t > 0 and 0 <= my + uy * t <= H and (best is None or t < best):
                best = t
        # 射程用 tongue.total
        if best is not None and best <= self.tongue.total:
            return mx + ux * best, my + uy * best, True
        ex = clampf(mx + ux * self.tongue.total, 0.0, WL)
        ey = clampf(my + uy * self.tongue.total, 0.0, H)
        return ex, ey, False
