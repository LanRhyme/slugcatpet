"""挡路几何纯函数：判 blocker 是否挡在 walker 通往目标的路上，及被顶方顺向让路点。无副作用、可脱离 Qt 单测。"""
from __future__ import annotations

from ..core.creature import WALK_STOP_EPS


def _sign(v: float) -> float:
    return 1.0 if v > 0.0 else (-1.0 if v < 0.0 else 0.0)


def blocks_path(blocker_x, walker_x, walker_target_x, contact_dist) -> bool:
    """blocker 是否正挡在 walker 前进方向上且已接触。"""
    if walker_target_x is None:
        return False
    d = walker_target_x - walker_x
    if abs(d) <= WALK_STOP_EPS:
        return False
    rel = (blocker_x - walker_x) * _sign(d)
    return 0.0 < rel <= contact_dist


def yield_target_x(walker_x, walker_target_x, lo, hi, clear_pad) -> float:
    """被顶方顺向让路目标：让到对方目标点外 clear_pad，clamp 到走带内（对方抵墙时只让到墙边）。"""
    s = _sign(walker_target_x - walker_x)
    return min(max(walker_target_x + s * clear_pad, lo), hi)
