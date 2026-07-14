"""向量辅助（Roll/Flip 力矩用），y↑ 手性不做翻转；角度基准 0°=+Y 顺时针增。"""
from __future__ import annotations
import math


def normalize(x: float, y: float):
    """单位化，零向量→(0,0)。"""
    d = math.hypot(x, y)
    if d < 1e-9:
        return (0.0, 0.0)
    return (x / d, y / d)


def dirvec(ax: float, ay: float, bx: float, by: float):
    """a→b 单位方向向量；重合→(0,0)。"""
    return normalize(bx - ax, by - ay)


def perpendicular(ax: float, ay: float, bx: float, by: float):
    """垂直于 a→b 的单位向量。"""
    dx, dy = dirvec(ax, ay, bx, by)
    return (dy, -dx)


def degvec(deg: float):
    """角度→单位向量，0°=+Y 顺时针增。"""
    r = deg * math.pi / 180.0
    return (math.sin(r), math.cos(r))
