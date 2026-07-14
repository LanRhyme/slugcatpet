"""躲避被杀控制器 KillDodger：舌头点掉「杀死」确认弹窗的"取消"按钮。"""
from __future__ import annotations
import math

from ...core.units import clampf

# 躲杀阶段常量
REACH_FRAC = 1.0
FIRE_IDEAL = 30.0
FIRE_REEL = 3.0
CLICK_DWELL = 8
APPROACH_TIMEOUT = 200
CLIMB_TIMEOUT = 1200
CLIMB_RETRY_MAX = 5
CLICK_TIMEOUT = 120


class KillDodger:
    def __init__(self, win, rng=None):
        self.win = win
        self.body = win.body
        self.gfx = win.gfx
        self.tongue = win.tongue
        self.phase = "approach"
        self.timer = 0
        self.giveup = False
        self._click_dwell = 0
        self._climber = None            # TongueClimber 实例
        self._climb_side = 0
        self._climb_tries = 0
        self.tongue.reset_config()

    def _reset_tongue(self):
        self.tongue.retract()
        self.tongue.reset_config()
        self.body.suspended = False

    def _mouth_to(self, tx, ty):
        mox, moy = self.gfx.mouth_world()
        return math.hypot(tx - mox, ty - moy)

    def update(self):
        self.timer += 1
        tgt = self.win.kill_cancel_target()
        if tgt is None:                       # 弹窗没了
            return True
        tx, ty = tgt
        b, tg = self.body, self.tongue
        c0 = b.chunk0
        within = self._mouth_to(tx, ty) <= tg.total * REACH_FRAC

        if self.phase == "approach":
            lo = b.walk_min if b.walk_min is not None else 20.0
            hi = b.walk_max if b.walk_max is not None else self.win._WL - 20.0
            b.walk_to(clampf(tx, lo, hi))
            if (b.on_floor() and not b.is_moving()) or self.timer > APPROACH_TIMEOUT:
                b.stop_walk()
                self.phase = "work"
                self.timer = 0
            return False

        if self.phase == "work":
            if within:
                if tg.is_idle():         # 够到 → 射舌收绳
                    tg.set_targets(ideal=FIRE_IDEAL, reel_rate=FIRE_REEL)
                    self.win.fire_tongue_at(tx, ty)
                    self.phase = "clicking"
                    self.timer = 0
                return False
            self._enter_climb(tx)             # 够不到 → 爬墙上顶横移
            return False

        if self.phase == "climb":
            if within:                        # 进射程 → 退爬升回 work
                self._reset_tongue()
                self._climber = None
                self.phase = "work"
                self.timer = 0
                return False
            if self.timer > CLIMB_TIMEOUT:
                self.giveup = True
                return True
            wall_x = b.walk_max if self._climb_side > 0 else b.walk_min
            if wall_x is None:
                wall_x = self.win._WL if self._climb_side > 0 else 0.0
            if self._climber is None:         # 先走到近侧墙脚，再交 TongueClimber
                if b.on_floor() and abs(c0.x - wall_x) > 12.0:
                    b.walk_to(wall_x)
                    return False
                b.stop_walk()
                from .climb import TongueClimber
                self._climber = TongueClimber(self.win, self._climb_side, target=(tx, ty))
                return False
            self._climber.target = (tx, ty)   # 喂实时按钮坐标
            self._climber.update()
            if self._climber.giveup:
                self._reset_tongue()
                self._climber = None
                self._climb_tries += 1
                if self._climb_tries >= CLIMB_RETRY_MAX:
                    self.giveup = True
                    return True
                self.phase = "work"           # 回 work 重判
                self.timer = 0
            return False

        if self.phase == "clicking":
            if tg.attached:                   # 舔到 → 停留后点
                self._click_dwell += 1
                if self._click_dwell >= CLICK_DWELL:
                    self.win.click_kill_cancel()
                    return True
                return False
            if tg.is_idle() or self.timer > CLICK_TIMEOUT:
                self.phase = "work"           # 没附上 → 重试
                self.timer = 0
                self._click_dwell = 0
            return False
        return False

    def _enter_climb(self, tx):
        self._climb_side = -1 if tx < self.win._WL * 0.5 else 1
        self._reset_tongue()
        self._climber = None
        self.phase = "climb"
        self.timer = 0

    def release(self):
        self._climber = None
        if not self.tongue.is_idle():
            self.tongue.retract()
        self.tongue.reset_config()
        self.body.suspended = False
        self.body.stop_walk()
