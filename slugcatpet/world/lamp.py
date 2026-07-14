"""暖灯：串杆+灯泡+flicker；暖区半径物理/行为两层共用。"""
from __future__ import annotations
import math
import random

from .enums import ItemState
from ..behavior.tuning import (COLD_ARRIVE_FRAC, COLD_LAMP_RANGE, COLD_LAMP_SCALE,
                      COLD_WARMTH_INNER)

GLOW_BASE_RADIUS = 250.0 * COLD_LAMP_SCALE

WARM_RADIUS = COLD_LAMP_RANGE * COLD_LAMP_SCALE
WARM_INNER = COLD_WARMTH_INNER * COLD_LAMP_SCALE
ARRIVE_RADIUS = WARM_RADIUS * COLD_ARRIVE_FRAC      # 比暖区更严，防越界停留


def _lerp_tick(frm: float, to: float, fac: float, tick: float) -> float:
    """Lerp 逼近目标，按 tick 限速。"""
    frm = frm + (to - frm) * fac
    if frm < to:
        return min(to, frm + tick)
    return max(to, frm - tick)


class Lamp:
    """单盏暖灯：anchor=挂载边端，bulb=灯泡端(暖源)。"""

    __slots__ = ("anchor_x", "anchor_y", "bulb_x", "bulb_y", "edge",
                 "state", "_id", "_rng", "_flicker")

    def __init__(self, anchor_x, anchor_y, bulb_x, bulb_y, edge, seed=0):
        self.anchor_x = float(anchor_x)
        self.anchor_y = float(anchor_y)
        self.bulb_x = float(bulb_x)
        self.bulb_y = float(bulb_y)
        self.edge = edge
        self.state = ItemState.FREE
        self._id = int(seed)
        self._rng = random.Random(0x1A39 ^ (int(seed) * 2654435761 & 0xFFFFFFFF))
        # flicker: [cur, prev, target] × 2
        self._flicker = [[1.0, 1.0, 1.0], [1.0, 1.0, 1.0]]

    @property
    def bulb(self):
        return (self.bulb_x, self.bulb_y)

    # 供通用 .x/.y 取坐标接口用
    @property
    def x(self):
        return self.bulb_x

    @property
    def y(self):
        return self.bulb_y

    def dist_to(self, x: float, y: float) -> float:
        return math.hypot(x - self.bulb_x, y - self.bulb_y)

    def in_warm_zone(self, x: float, y: float) -> bool:
        return self.dist_to(x, y) < WARM_RADIUS

    def step(self):
        """逐 tick 推进 flicker，纯视觉。"""
        rng = self._rng
        for f in self._flicker:
            f[1] = f[0]
            sign = 1.0 if rng.random() < 0.5 else -1.0
            f[0] += (rng.random() ** 3) * 0.1 * sign
            f[0] = _lerp_tick(f[0], f[2], 0.05, 1.0 / 30.0)
            if rng.random() < 0.2:
                sign2 = 1.0 if rng.random() < 0.5 else -1.0
                f[2] = 1.0 + (rng.random() ** 3) * 0.2 * sign2
            f[2] = f[2] + (1.0 - f[2]) * 0.01

    def glow_radius(self) -> float:
        return GLOW_BASE_RADIUS * max(0.0, self._flicker[0][0])
