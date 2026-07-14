"""单位换算：40Hz 物理，系数恒等。"""
from __future__ import annotations

TICK_RATE: float = 40.0
FPS: float = 40.0
_R = TICK_RATE / FPS
K_VEL: float = _R
K_IMP: float = _R * _R
# y 方向符号翻转由调用方负责


def damp60(k_tick: float) -> float:
    """阻尼系数换算。"""
    return k_tick ** _R


def clampf(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else (hi if v > hi else v)


def lerp(a: float, b: float, t: float) -> float:
    """线性插值，t 钳 [0,1]。"""
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return a + (b - a) * t


def inv_lerp(a: float, b: float, v: float) -> float:
    """反向线性插值：返回钳 [0,1]；端点相等→0。"""
    if a == b:
        return 0.0
    t = (v - a) / (b - a)
    return 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
