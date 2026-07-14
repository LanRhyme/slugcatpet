"""溺水气泡粒子（y↓）。"""
from __future__ import annotations
import math

DRAG = 0.8
BUOYANCY_MAG = 1.2
MAX_AGE = 600
POP_MARGIN = 10.0
FULL_SIZE_MIN = 0.5
FULL_SIZE_MAX = 1.5


class Bubble:
    """单个气泡。"""
    __slots__ = ("x", "y", "last_x", "last_y", "vx", "vy", "full_size", "age")

    def __init__(self, x, y, vx, vy, rng):
        self.x = self.last_x = float(x)
        self.y = self.last_y = float(y)
        self.vx = float(vx)
        self.vy = float(vy)
        self.full_size = rng.uniform(FULL_SIZE_MIN, FULL_SIZE_MAX)
        self.age = 0

    def update(self, water_y, rng) -> bool:
        """推进一帧，返回是否存活（False=销毁）。"""
        self.last_x, self.last_y = self.x, self.y
        self.vx *= DRAG
        self.vy *= DRAG
        deg = math.radians(-90.0 + 180.0 * rng.random())    # 指向上半圆
        mag = rng.random() * BUOYANCY_MAG
        self.vx += math.sin(deg) * mag
        self.vy += -math.cos(deg) * mag                     # y↓ 取反
        self.x += self.vx
        self.y += self.vy
        self.age += 1
        if self.age > MAX_AGE:
            return False
        return self.y > water_y + POP_MARGIN
