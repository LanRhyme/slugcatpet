"""果取薄应用：选果/够取交规划层驱动，接触抓取与 grabbed→carry_fall→eat 留本地。"""
from __future__ import annotations
import math

from ..behavior import tuning
from ..planning import GIVEUP, PlanExecutor, TongueSnatch, obj_goal
from ..cats.personality import DIET_VEGETARIAN, DIET_SPECIAL, DIET_CARNIVORE

# 取食/啃咬参数
MEAT_PREF = 0.6
EAT_INTERVAL = 15
EAT_APPROACH = 12
EAT_HOLD_POSE = 0.25
EAT_CHOMP_POSE = 1.0
BITE_HEAD_NUDGE = 2.0
CARRY_FALL_TIMEOUT = 200

_EDIBLE_STATES = ("free", "hanging")


def _dist(ax, ay, bx, by):
    return math.hypot(bx - ax, by - ay)


def _seg_point_dist(ax, ay, bx, by, px, py):
    """点 (px,py) 到线段 (a,b) 的最近距。"""
    dx, dy = bx - ax, by - ay
    d2 = dx * dx + dy * dy
    if d2 < 1e-9:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / d2
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _edible_goal(obj):
    """可食目标 Goal：离开 free/hanging 即失效。"""
    return obj_goal(obj, valid=lambda o: o.state in _EDIBLE_STATES, contact="grasp")


def fetch_candidates(planner, edibles, diet=None):
    """选果候选：可达且不冷却的 (obj, goal, 预估耗时)，按耗时升序。"""
    out = []
    for f in edibles:
        if f.state not in _EDIBLE_STATES:
            continue
        if not getattr(f, "fetch_ready", True):
            continue    # 飞行中蝙蝠够不到
        meat = getattr(f, "is_meat", False)
        if meat and diet in (DIET_VEGETARIAN, DIET_SPECIAL):
            continue    # 素食/圣徒不自主吃肉
        g = _edible_goal(f)
        if planner.in_cooldown(g):
            continue
        cands = planner.touch_candidates(g)
        if cands:
            time_est = cands[0].time_est
            if meat and diet == DIET_CARNIVORE:
                time_est *= MEAT_PREF
            out.append((f, g, time_est))
    out.sort(key=lambda item: item[2])
    return out


def fetch_ready(planner, edibles, diet=None):
    """触发闸用：早退版 fetch_candidates，仅返回可达列表。"""
    out = []
    for f in edibles:
        if f.state not in _EDIBLE_STATES:
            continue
        if not getattr(f, "fetch_ready", True):
            continue
        if getattr(f, "is_meat", False) and diet in (DIET_VEGETARIAN, DIET_SPECIAL):
            continue
        g = _edible_goal(f)
        if planner.in_cooldown(g):
            continue
        if planner.any_touch(g):
            out.append(f)
    return out


class FruitFetcher:
    def __init__(self, win, planner, diet=None):
        self.win = win
        self.body = win.body
        self.tongue = win.tongue
        self.planner = planner
        self.diet = diet

        self.target = None
        self.phase = "select"
        self.eaten = 0
        self.giveup = False
        self.timer = 0
        self.grab_side = "r"
        self.eat_counter = 0
        self._eat_approaching = False
        self._bit_this_cycle = False
        self._executor = None
        self._giveup_pending = False
        self._goal = None
        self._snatch = TongueSnatch(win)

    def _chunk0(self):
        return self.body.chunk0

    def _grab_dist(self):
        """果到扫掠线段/持物手最近距，防高速跨过抓取圈漏判。"""
        f = self.target
        c0 = self._chunk0()
        d = _seg_point_dist(c0.last_x, c0.last_y, c0.x, c0.y, f.x, f.y)
        hx, hy = self.body._carry_pos(self.grab_side)
        d = min(d, _dist(hx, hy, f.x, f.y))
        return d

    def _try_grab(self):
        """够取判定，命中则抓果转 carry_fall。"""
        if self._grab_dist() < tuning.GRAB_REACH:
            self._reset_tongue()
            if getattr(self.target, "stuck_pos", None) is not None:
                self.target.stuck_pos = None    # 抓取瞬间剥离黏菌
            self.body.grab_fruit(self.target, self.grab_side)
            self.phase = "grabbed"
            self.timer = 0
            return True
        return False

    def _reset_tongue(self):
        """舌头收缩与悬停清理。"""
        if self.tongue is not None:
            self.tongue.retract()
            self.tongue.reset_config()
        self.body.suspended = False

    def _pick_grab_side(self):
        """选更近的抓取手。"""
        return "r" if self.target.x >= self._chunk0().x else "l"

    def _drop_executor(self):
        if self._executor is not None:
            self._executor.cancel()
            self._executor = None

    def release(self):
        """外部中断：终止执行器 + 收回补救舌头。"""
        self._snatch.abort()
        self._drop_executor()

    def update(self) -> bool:
        """推进一 tick，完成返回 True。"""
        self.timer += 1
        m = getattr(self, "_phase_" + self.phase, None)
        if m is None:
            return True
        return m()

    def _phase_select(self):
        # 候选空 + 曾放弃 → giveup
        cands = fetch_candidates(self.planner, self.win.edibles(), diet=self.diet)
        if not cands:
            self.giveup = self._giveup_pending
            return True
        self.target, goal, _ = cands[0]
        self.grab_side = self._pick_grab_side()
        self._giveup_pending = False
        self._goal = goal
        self._snatch.reset()
        self._executor = PlanExecutor(self.win, self.planner, goal)
        self.timer = 0
        self.phase = "approach"
        return False

    def _phase_approach(self):
        # 执行器驱动够取，每 tick 自查抓取
        f = self.target
        if f.state not in _EDIBLE_STATES:
            self._snatch.abort()
            self._drop_executor()
            self.phase = "select"
            return False
        self.grab_side = self._pick_grab_side()
        if self._try_grab():
            self._snatch.abort()
            self._drop_executor()
            return False
        # 补救层需在 try_grab 后、executor 前抢射
        self._snatch.update(self._goal)
        if self._snatch.holding():
            # 持有补救舌头时暂停 executor，防裸 retract 撕舌
            return False
        if self._executor.update() == GIVEUP:
            self._snatch.abort()
            self._executor = None
            self.target = None
            self._giveup_pending = True
            self.phase = "select"
        return False

    def _phase_grabbed(self):
        self._reset_tongue()
        self.body.suspended = False
        self.phase = "carry_fall"
        self.timer = 0
        return False

    def _phase_carry_fall(self):
        f = self.body.carried_fruit
        if f is None:
            self.phase = "select"
            return False
        # 悬空卡死兜底超时
        if self.timer > CARRY_FALL_TIMEOUT and f.stalk is not None:
            f.stalk = None
        if self.body.on_floor():
            self.phase = "eat"
            self.timer = 0
            self.eat_counter = 0
            self._eat_approaching = True
            self._bit_this_cycle = False
        return False

    def _phase_eat(self):
        f = self.body.carried_fruit
        if f is None:
            self.phase = "select"
            return False
        self.win.gfx.look_at = (f.x, f.y)
        self.eat_counter += 1

        # 预咬摆动
        if self._eat_approaching:
            self.body.eat_raise = EAT_HOLD_POSE * min(1.0, self.eat_counter / EAT_APPROACH)
            if self.eat_counter >= EAT_APPROACH:
                self._eat_approaching = False
                self.eat_counter = 0
                self._bit_this_cycle = False
            return False

        # 咀嚼周期，峰值咬一口
        phase = min(1.0, self.eat_counter / EAT_INTERVAL)
        pulse = math.sin(phase * math.pi)
        self.body.eat_raise = EAT_HOLD_POSE + (EAT_CHOMP_POSE - EAT_HOLD_POSE) * pulse
        if self.eat_counter >= EAT_INTERVAL // 2 and not self._bit_this_cycle:
            self._bit_this_cycle = True
            self._bite_head_nudge(f)
            if self.body.bite_carried():
                f.state = "eaten"
                self.eaten += 1
                self.body.temper_shift(tuning.TEMPER_FEED)
                self.body.food_eat(1)
                self.body.energy_change(tuning.EN_EAT_RESTORE)
                self.body.release_fruit()
                if self.body.food >= self.body.food_max:
                    return True
                self.phase = "select"
                self.timer = 0
                return False
        if self.eat_counter >= EAT_INTERVAL:
            self.eat_counter = 0
            self._bit_this_cycle = False
        return False

    def _bite_head_nudge(self, f):
        """每口头部朝果轻推。"""
        g = self.win.gfx
        dx, dy = f.x - g.head.x, f.y - g.head.y
        d = math.hypot(dx, dy)
        if d > 1e-6:
            g.head.vx += dx / d * BITE_HEAD_NUDGE
            g.head.vy += dy / d * BITE_HEAD_NUDGE
