"""竖/横杆几何实体；攀爬逻辑见 pole_climb.py。"""
from __future__ import annotations

from .enums import ItemState

VERTICAL = "vertical"
HORIZONTAL = "horizontal"

POLE_RAD = 2.0
MIN_LENGTH = 40.0
TOP_MARGIN = 48.0


class Pole:
    """单根杆子：端点+攀爬标记（ax/ay=锚边端，bx/by=光标端）。"""

    __slots__ = ("kind", "ax", "ay", "bx", "by", "state", "has_been_climbed", "_id")

    def __init__(self, kind, ax, ay, bx, by, seed=0):
        self.kind = kind
        self.ax = float(ax)
        self.ay = float(ay)
        self.bx = float(bx)
        self.by = float(by)
        self.state = ItemState.FREE
        self.has_been_climbed = False
        self._id = int(seed)

    # ── 竖杆便捷访问 ──
    @property
    def x(self) -> float:
        return self.bx          # 竖杆 x

    @property
    def top_y(self) -> float:
        return self.by          # 顶端（y 较小）

    def step(self, WL: float, HL: float) -> None:
        """静态，无积分。"""
        return
