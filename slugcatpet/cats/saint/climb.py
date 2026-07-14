"""舌头爬墙 + 吊顶：TongueClimber 攀墙到顶，CeilingHanger 吊顶摆晃，均基于舌头弹簧锚点。"""
from __future__ import annotations
import math

from ...core.units import clampf
from ...behavior import tuning

# 爬墙/吊顶常量（px/tick）
CLIMB_SHOOT_V = 46.7
CLIMB_IDEAL = 50.0
CLIMB_IDEAL_MIN = 25.0
CLIMB_RELEASE_DIST = 55.0
HANG_IDEAL = 50.0

CEIL_CENTER_LO = 0.25
CEIL_CENTER_HI = 0.75
TRAVERSE_MAX_HOPS = 12


class TongueClimber:
    def __init__(self, win, side, target=None, stop_dist=None):
        self.win = win
        self.body = win.body
        self.tongue = win.tongue
        self.side = 1 if side > 0 else -1     # 1=右墙 / -1=左墙
        self.target = target                  # 趋暖目标坐标，None 为自由玩耍
        self.stop_dist = stop_dist            # 到目标此距内停止
        self.phase = "shoot"                  # shoot → reel → settle → (ceiling)
        self.fails = 0
        self.timer = 0
        self.giveup = False
        self.jitter = 0
        self.tv_hops = 0                       # 沿天花板朝中间已挪的跳数
        self.tongue.set_targets(shoot_v=CLIMB_SHOOT_V, ideal=CLIMB_IDEAL,
                                total=200.0, reel_rate=3.0)

    def _wall_x(self):
        return (self.win._WL) if self.side > 0 else 0.0

    def _aim_up_wall(self):
        """朝墙边上方发射。"""
        c0 = self.body.chunk0
        self.jitter = (self.jitter * 1103515245 + 12345) & 0x7FFF
        jy = ((self.jitter % 100) / 100.0 - 0.5) * 10.0
        self.win.fire_tongue(self._wall_x(), c0.y - 105.0 + jy)

    def update(self):
        self.timer += 1
        c0 = self.body.chunk0
        tg = self.tongue

        # 到目标距离内停止
        if self.target is not None and self.stop_dist is not None:
            if math.hypot(c0.x - self.target[0], c0.y - self.target[1]) <= self.stop_dist:
                return True

        # 触发吊顶阈值取 _HL*0.5 与射程 85% 的较小值
        ceil_trigger = min(self.win._HL * 0.5, self.tongue.total * 0.85)
        if (self.phase not in ("ceiling", "ceil_wait",
                               "tv_settle", "tv_drop", "tv_shoot")
                and c0.y < ceil_trigger):
            self.phase = "ceiling"

        if self.phase == "shoot":
            if tg.is_idle():
                self._aim_up_wall()
                self.tongue.set_targets(ideal=CLIMB_IDEAL)
                self.phase = "reel"
                self.timer = 0
            return False

        if self.phase == "reel":
            if tg.attached:
                d = math.hypot(c0.x - tg.anchor[0], c0.y - tg.anchor[1])
                if d < CLIMB_RELEASE_DIST:
                    tg.retract()
                    self.body.chunk0.vy -= 1.5
                    self.phase = "settle"
                    self.timer = 0
                    self.fails = 0
                else:
                    self.tongue.set_targets(
                        ideal=max(CLIMB_IDEAL_MIN, self.tongue.ideal - 0.5))
            elif tg.is_idle():
                self.fails += 1
                if self.fails >= 3:
                    self.giveup = True
                self.phase = "shoot"
            return False

        if self.phase == "settle":
            if self.timer > 8:
                self.phase = "shoot"
            return False

        if self.phase == "ceiling":
            if tg.attached:
                tg.retract()  # 仍附着先松开
            elif tg.is_idle():
                self.win.fire_tongue(c0.x, c0.y - self.win._HL)
                self.phase = "ceil_wait"
                self.timer = 0
            return False

        if self.phase == "ceil_wait":
            if tg.attached:
                self.tongue.set_targets(ideal=HANG_IDEAL, reel_rate=3.0)
                if self._anchor_centered():
                    return True
                self.phase = "tv_settle"
                self.timer = 0
                self.tv_hops = 0
                return False
            if tg.is_idle() and self.timer > 4:
                self.phase = "ceiling"
            return False

        if self.phase == "tv_settle":
            self.tongue.set_targets(ideal=HANG_IDEAL, reel_rate=3.0)
            ax, ay = tg.anchor if tg.anchor else (c0.x, 0.0)
            dist = math.hypot(c0.x - ax, c0.y - ay)
            if (dist < HANG_IDEAL + 22.0 and abs(c0.x - ax) < 30.0) or self.timer > 90:
                self.phase = "tv_drop"
                self.timer = 0
            return False

        if self.phase == "tv_drop":
            if tg.attached:
                tg.retract()
            elif tg.is_idle() and self.timer > 6:
                if self.tv_hops >= TRAVERSE_MAX_HOPS:
                    return True
                self.win.fire_tongue(self._traverse_target(), 0.0)
                self.tv_hops += 1
                self.phase = "tv_shoot"
                self.timer = 0
            return False

        if self.phase == "tv_shoot":
            if tg.attached:
                self.tongue.set_targets(ideal=HANG_IDEAL, reel_rate=3.0)
                if self._anchor_centered():
                    return True
                self.phase = "tv_settle"
                self.timer = 0
            elif tg.is_idle() and self.timer > 6:
                if self.tv_hops >= TRAVERSE_MAX_HOPS:
                    return True
                self.win.fire_tongue(self._traverse_target(), 0.0)
                self.tv_hops += 1
                self.timer = 0
            return False

        return False

    def _anchor_centered(self):
        """舌头锚点是否到位：趋暖→近灯泡 x；玩耍→屏幕中间 50% 区间。"""
        a = self.tongue.anchor
        if a is None:
            return False
        if self.target is not None:
            return abs(a[0] - self.target[0]) < 60.0
        WL = self.win._WL
        return WL * CEIL_CENTER_LO <= a[0] <= WL * CEIL_CENTER_HI

    def _traverse_target(self):
        """下一跳的天花板锚点 x：趋暖→朝灯泡 x；玩耍→朝屏幕中心，受舌头射程限制。"""
        c0 = self.body.chunk0
        WL = self.win._WL
        center = self.target[0] if self.target is not None else WL * 0.5
        reach = math.sqrt(max(1.0, self.tongue.total ** 2 - (c0.y + 5.0) ** 2)) * 0.85
        direction = 1.0 if center >= c0.x else -1.0
        step = min(reach, abs(center - c0.x))
        return clampf(c0.x + direction * step, 20.0, WL - 20.0)


class CeilingHanger:
    def __init__(self, win, side, rng, target_x=None):
        self.win = win
        self.body = win.body
        self.tongue = win.tongue
        self.side = 1 if side > 0 else -1
        self.target_x = target_x          # 趋暖目标 x，None 往中间
        self.rng = rng
        self.next = rng.randint(120, 320)   # 距下次小动作的间隔 tick
        self.timer = 0
        self.sub = None
        self.sub_t = 0
        self._sway_amp = 0.5
        self._sway_half = 12
        self._sway_dir = 1
        self._vtarget = HANG_IDEAL
        self.tongue.set_targets(ideal=HANG_IDEAL, reel_rate=3.0)

    def update(self):
        self.timer += 1
        tg = self.tongue
        # 掉落交回行为层，bigmove 期除外
        if not tg.attached and self.sub != "bigmove":
            return True
        if self.sub is None and self.timer >= self.next:
            self.timer = 0
            self.next = self.rng.randint(120, 320)
            r = self.rng.random()
            if r < 0.45:
                self.sub, self.sub_t = "sway", self.rng.randint(27, 60)
                self._sway_amp = self.rng.uniform(tuning.CEIL_SWAY_AMP_MIN, tuning.CEIL_SWAY_AMP_MAX)
                self._sway_half = self.rng.randint(tuning.CEIL_SWAY_HALF_MIN, tuning.CEIL_SWAY_HALF_MAX)
                self._sway_dir = 1 if self.rng.random() < 0.5 else -1
            elif r < 0.8:
                self.sub, self.sub_t = "vmove", self.rng.randint(27, 60)
                self._vtarget = HANG_IDEAL + self.rng.uniform(-tuning.CEIL_VMOVE_RANGE,
                                                              tuning.CEIL_VMOVE_RANGE)
            else:
                self.sub, self.sub_t = "bigmove", 0
        if self.sub == "sway":
            d = self._sway_dir if (self.timer // self._sway_half) % 2 == 0 else -self._sway_dir
            self.body.chunk0.vx += self._sway_amp * d
            self.sub_t -= 1
            if self.sub_t <= 0:
                self.sub = None
        elif self.sub == "vmove":
            tg.set_targets(ideal=tg.ideal + (self._vtarget - tg.ideal) * 0.1)
            self.sub_t -= 1
            if self.sub_t <= 0:
                tg.set_targets(ideal=HANG_IDEAL)
                self.sub = None
        elif self.sub == "bigmove":
            # 松舌后重射偏中间位置
            return self._bigmove()
        return False

    def _bigmove(self):
        tg = self.tongue
        c0 = self.body.chunk0
        if not hasattr(self, "_bm_phase"):
            self._bm_phase = "drop"
            self._bm_t = 0
            self._bm_tries = 0
            tg.retract()
        self._bm_t += 1
        if self._bm_phase == "drop":
            if self._bm_t > 8:
                toward = (1.0 if self.target_x >= c0.x else -1.0) if self.target_x is not None else -self.side
                self.win.fire_tongue(c0.x + toward * 40.0, c0.y - self.win._HL)
                self._bm_phase = "reshoot"
                self._bm_t = 0
                self._bm_tries += 1
        elif self._bm_phase == "reshoot":
            if tg.attached:
                tg.set_targets(ideal=HANG_IDEAL)
                del self._bm_phase
                self.sub = None
            elif tg.is_idle() and self._bm_t > 4:
                if self._bm_tries >= 4:  # 连射不中则放弃
                    tg.retract()
                    del self._bm_phase
                    return True
                toward = (1.0 if self.target_x >= c0.x else -1.0) if self.target_x is not None else -self.side
                self.win.fire_tongue(c0.x + toward * 40.0, c0.y - self.win._HL)
                self._bm_t = 0
                self._bm_tries += 1
        return False
