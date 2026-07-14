"""渲染层数学工具与常量，坐标系 y↓。"""
from __future__ import annotations
import math

# ── 手臂 / 尾 / 舌渲染常量 ──
SHOULDER_OFF_X = 4.5
SHOULDER_OFF_Y = 3.5                # y↓
ARM_DIV = 2.0
ARM_MAX = 12
TAIL_RAD = (6.0, 4.0, 2.5, 1.0)
TONGUE_WIDTH_SCALE = 0.4            # 调校值，勿改回


def _hsl2rgb(h, sl, l):
    """HSL→RGB，输入输出均 0..1 float。"""
    r = g = b = l
    v_max = l * (1.0 + sl) if l <= 0.5 else l + sl - l * sl
    if v_max > 0.0:
        v_min = l + l - v_max
        chroma_ratio = (v_max - v_min) / v_max
        h6 = h * 6.0
        sector = int(h6)
        frac = h6 - sector
        delta = v_max * chroma_ratio * frac
        rising = v_min + delta
        falling = v_max - delta
        if sector == 0:   r, g, b = v_max, rising, v_min
        elif sector == 1: r, g, b = falling, v_max, v_min
        elif sector == 2: r, g, b = v_min, v_max, rising
        elif sector == 3: r, g, b = v_min, falling, v_max
        elif sector == 4: r, g, b = rising, v_min, v_max
        elif sector == 5: r, g, b = v_max, v_min, falling
    return r, g, b


def _ang_from_up(dx, dy):
    """方向相对『上』(0,-1) 的角（度，Qt 同号：顺时针正）。"""
    return math.degrees(math.atan2(dx, -dy))


def _rot(lx, ly, deg):
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    return lx * c - ly * s, lx * s + ly * c


def _lerp(a, b, t):
    return a + (b - a) * t


def _catmull(p0, p1, p2, p3, t):
    """Catmull-Rom 插值，p1→p2 段 t∈[0,1] 处的点。"""
    t2 = t * t
    t3 = t2 * t
    return 0.5 * ((2.0 * p1)
                  + (-p0 + p2) * t
                  + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
                  + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3)
