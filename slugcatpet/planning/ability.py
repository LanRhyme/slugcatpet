"""能力三问接口：can_touch / can_stay 回 Estimate，make_controller 回执行控制器。"""
from __future__ import annotations
import math

from dataclasses import dataclass

from ..behavior import tuning

# 控制器与执行器共用的状态字符串
RUNNING = "running"
DONE = "done"
GIVEUP = "giveup"
HOLD = "hold"          # 到位持续维持驻留：不重规划/不计超时/不计失败

# PlanExecutor 对消费方的返回值（HOLD 之外与控制器状态同名）
HOLDING = "holding"

# 规划模式
MODE_TOUCH = "touch"
MODE_STAY = "stay"


@dataclass(frozen=True)
class Estimate:
    """粗线性代价：预估耗时 tick / 预估体力开销。"""
    time_est: float
    energy_est: float


@dataclass
class Candidate:
    """一条已过体力门槛的候选方案。"""
    ability_key: str
    time_est: float
    energy_est: float
    _factory: object

    def make_controller(self):
        return self._factory()


class Ability:
    """能力基类；控制器协议：update() -> running|done|giveup，cancel() 清理。"""
    key = ""

    def __init__(self, pet):
        self.pet = pet

    def can_touch(self, goal):
        return None

    def can_stay(self, goal):
        return None

    def make_controller(self, goal):
        raise NotImplementedError


class PointTarget:
    """reach_for 兼容的点目标（.x/.y）。"""
    __slots__ = ("x", "y")

    def __init__(self, x, y):
        self.x = x
        self.y = y


def walk_band(pet):
    """可行走 x 区间 [xmin, xmax]。"""
    body = pet.body
    xmin = getattr(body, "walk_min", None)
    xmax = getattr(body, "walk_max", None)
    return (0.0 if xmin is None else xmin,
            pet._WL if xmax is None else xmax)


def reach_assist(pet, goal, gx, gy):
    """近目标探身：距目标 < arm_full_reach*REACH_GATE_K 才伸臂。"""
    body = pet.body
    c0 = body.chunk0
    if math.hypot(gx - c0.x, gy - c0.y) < body.arm_full_reach * tuning.REACH_GATE_K:
        tgt = goal.obj if goal.obj is not None else PointTarget(gx, gy)
        body.reach_for(tgt, "r" if gx >= c0.x else "l")
