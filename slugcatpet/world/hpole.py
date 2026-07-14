"""横杆借力控制器：swing→reel→grip→pullup→stand 状态机；update() 返回 True=结束。"""
from __future__ import annotations

import math

from ..behavior import tuning

# 各阶段计时/距离/速度常量
CONN = 17.0
SWAY_TICKS = 55
GRIP_IDEAL = 9.0
GRIP_DIST = 16.0
REEL_RATE = 2.0
REEL_TIMEOUT = 240
HANG_TICKS = 28
PULLUP_TICKS = 22
STAND_HOVER = 5.0
STAND_TICKS = 200
WALK_SPEED = 1.4
WALK_MARGIN = 14.0
TURN_PERIOD = 20
TURN_PROB = 0.5
JUMP_DOWN_VY = 2.0
AIRGRAB_TIMEOUT = 90


class HPoleController:
    def __init__(self, win, pole, rng=None):
        self.win = win
        self.body = win.body
        self.gfx = win.gfx
        self.tongue = win.tongue
        self.pole = pole
        self.rng = rng
        self.phase = "swing" if self.tongue is not None else "airgrab"
        self.timer = 0
        self.giveup = False
        self._walk_dir = 1
        self._stand_t = 0
        self._pause = 0
        self._swing_t = 0
        self.disbalance = 0.0
        self._sway_c = 0.0
        self._wobble_target = 45.0
        # 锚点固定到杆
        lo, hi = self._extent()
        if self.tongue is not None:
            a = self.tongue.anchor
            ax = a[0] if a is not None else (lo + hi) * 0.5
        else:
            ax = self.body.chunk0.x
        self._anchor = (max(lo + 2.0, min(hi - 2.0, ax)), pole.ay)

    # 杆几何
    def _extent(self):
        return min(self.pole.ax, self.pole.bx), max(self.pole.ax, self.pole.bx)

    def update(self):
        self.timer += 1
        m = getattr(self, "_phase_" + self.phase, None)
        if m is None:
            return True
        return m()

    # 无舌前段：贴杆即抓，超时放弃
    def _phase_airgrab(self):
        b = self.body
        lo, hi = self._extent()
        ax = max(lo + 2.0, min(hi - 2.0, b.chunk0.x))
        ay = self.pole.ay
        if math.hypot(b.chunk0.x - ax, b.chunk0.y - ay) <= GRIP_DIST:
            self._anchor = (ax, ay)
            self._grip(ax, ay)
            self.phase = "hang"
            self.timer = 0
            return False
        if self.timer > AIRGRAB_TIMEOUT:
            self.giveup = True
            return True
        return False

    # 前段：舌头吊杆
    def _phase_swing(self):
        tg = self.tongue
        if tg is None or not tg.attached:         # 舌头掉了 → 放弃
            self.giveup = True
            return True
        tg.anchor = self._anchor  # 固定锚点
        if self.timer > SWAY_TICKS:
            self.phase = "reel"
            self.timer = 0
        return False

    def _phase_reel(self):
        tg = self.tongue
        if tg is None or not tg.attached:
            self.giveup = True
            return True
        ax, ay = self._anchor
        tg.anchor = self._anchor
        tg.set_targets(ideal=GRIP_IDEAL, reel_rate=REEL_RATE)  # 降目标绳长
        if abs(self.body.chunk0.y - ay) <= GRIP_DIST or self.timer > REEL_TIMEOUT:
            self._grip(ax, ay)
            self.phase = "hang"
            self.timer = 0
        return False

    # 换手
    def _grip(self, ax, ay):
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        if self.tongue is not None:
            self.tongue.retract()
            self.tongue.reset_config()
        b.suspended = False
        b.on_pole = True
        b.standing = True
        b.animation = "HangFromBeam"
        b.pole_x = ax
        b.pole_y = ay  # 手抓点 y
        b.facing = 1 if c0.x >= c1.x else -1
        # 上身钉杆线
        c0.pinned = True
        c0.x = ax
        c0.y = ay
        c0.vx = c0.vy = 0.0
        # 下身解钉自由垂
        c1.pinned = False

    def _phase_hang(self):
        b = self.body
        c0 = b.chunk0
        ax, ay = b.pole_x, self.pole.ay
        c0.x = ax  # 上身钉杆线
        c0.y = ay
        c0.vx = c0.vy = 0.0
        if self.timer > HANG_TICKS:
            self.phase = "pullup"
            self.timer = 0
            self._pullup_from = (b.chunk1.x, b.chunk1.y)
        return False

    # 引体
    def _phase_pullup(self):
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        b.animation = "GetUpOnBeam"
        ax, ay = b.pole_x, self.pole.ay
        t = min(1.0, self.timer / float(PULLUP_TICKS))
        tt = t * t * (3.0 - 2.0 * t)              # smoothstep
        # 终态：脚钉杆面上，身在其上
        c1.pinned = True
        feet_top_y = ay - STAND_HOVER
        body_top_y = feet_top_y - CONN
        fx0, fy0 = self._pullup_from
        c1.x = ax
        c1.y = fy0 + (feet_top_y - fy0) * tt
        c1.vx = c1.vy = 0.0
        c0.x = ax
        c0.y = ay + (body_top_y - ay) * tt
        c0.vx = c0.vy = 0.0
        if self.timer >= PULLUP_TICKS:
            self.phase = "stand"
            self.timer = 0
            self._stand_t = 0
            b.animation = "StandOnBeam"
            self._walk_dir = 1 if (self.rng is None or self.rng.random() < 0.5) else -1
        return False

    # 站杆面平衡走
    def _phase_stand(self):
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        ax_lo, ax_hi = self._extent()
        ay = self.pole.ay
        self._stand_t += 1
        feet_y = ay - STAND_HOVER
        lo, hi = ax_lo + WALK_MARGIN, ax_hi - WALK_MARGIN
        can_walk = hi > lo
        # 低概率：翻到杆下再上来
        if (can_walk and self._pause <= 0 and self.rng is not None
                and self.rng.random() < tuning.HP_HANG_PROB):
            self._enter_swing_under()
            return False
        # 走走停停
        if self._pause > 0:
            self._pause -= 1
            walking = False
        else:
            walking = can_walk
            if (can_walk and self.rng is not None
                    and self.rng.random() < tuning.HP_PAUSE_PROB):
                self._pause = self.rng.randint(tuning.HP_PAUSE_MIN, tuning.HP_PAUSE_MAX)
                walking = False
        if walking:
            if (self._stand_t % TURN_PERIOD == 0 and self.rng is not None
                    and self.rng.random() < TURN_PROB):
                self._walk_dir = -self._walk_dir
            nx = c1.x + WALK_SPEED * self._walk_dir
            if nx <= lo:
                nx, self._walk_dir = lo, 1
            elif nx >= hi:
                nx, self._walk_dir = hi, -1
            c1.x = nx
            b.facing = 1 if self._walk_dir > 0 else -1
        c1.y = feet_y
        c1.vx = WALK_SPEED * (1.0 if walking else 0.0) * b.facing
        c1.vy = 0.0
        # 走时晃身平衡
        if walking:
            if self._stand_t % tuning.HP_RETARGET_TICKS == 0 and self.rng is not None:
                self._wobble_target = self.rng.uniform(tuning.HP_WOBBLE_MIN, tuning.HP_WOBBLE_MAX)
            target = self._wobble_target
        else:
            target = 0.0
        self.disbalance += (target - self.disbalance) * 0.1
        roll = self.rng.random() if self.rng is not None else 0.5
        self._sway_c += 1.0 + self.disbalance / 40.0 * (1.0 + roll)
        if self._sway_c > tuning.BAL_COUNTER_WRAP:
            self._sway_c -= tuning.BAL_COUNTER_WRAP
        # 平衡摆动只在绘制层加，避免物理层重复偏移
        c0.x = c1.x
        c0.y = feet_y - CONN
        c0.vx = c0.vy = 0.0
        self.gfx.disbalance = self.disbalance
        self.gfx.balance_counter = self._sway_c
        self.gfx.look_at = (c0.x + b.facing * 60.0, c0.y)
        if self._stand_t > STAND_TICKS:
            self._jump_down()
            return True
        return False

    def _enter_swing_under(self):
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        b.animation = "HangFromBeam"
        b.pole_x = c1.x
        b.pole_y = self.pole.ay
        c0.pinned = True
        c0.x = c1.x
        c0.y = self.pole.ay
        c0.vx = c0.vy = 0.0
        c1.pinned = False
        self._swing_t = 0
        self.phase = "swing_under"

    def _phase_swing_under(self):
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        c0.pinned = True
        c0.x = b.pole_x
        c0.y = self.pole.ay
        c0.vx = c0.vy = 0.0
        self._swing_t += 1
        c1.vx += 0.4 * (1.0 if (self._swing_t // 14) % 2 == 0 else -1.0)
        if self._swing_t > tuning.HP_HANG_TICKS:
            self.phase = "pullup"
            self.timer = 0
            self._pullup_from = (c1.x, c1.y)
        return False

    def _jump_down(self):
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        c0.pinned = False
        c1.pinned = False
        b.on_pole = False
        b.animation = None
        c1.vy += JUMP_DOWN_VY
        c0.vy += JUMP_DOWN_VY
        c0.vx += b.facing * 1.0
        self._reset_pose()

    def _reset_pose(self):
        self.gfx.hand_aim["l"] = None
        self.gfx.hand_aim["r"] = None
        self.gfx.disbalance = 0.0

    # 打断清理
    def release(self):
        b = self.body
        b.chunk0.pinned = False
        b.chunk1.pinned = False
        b.on_pole = False
        b.animation = None
        if self.tongue is not None:
            if self.tongue.attached:
                self.tongue.retract()
            self.tongue.reset_config()
        b.suspended = False
        self._reset_pose()
