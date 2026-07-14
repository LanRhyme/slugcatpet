"""东张西望：兴趣衰减换目标，偶尔瞟随机点或谁也不看。"""
from __future__ import annotations
import math

from ..behavior import tuning


class ObjectLooker:
    def __init__(self, rng, look_fac=1.0):
        self.rng = rng
        self.look_fac = look_fac
        self.mode = "nothing"     # "cursor"/对象引用/"point"/"nothing"
        self.point = None         # mode=="point" 时的冻结点
        self.point_interest = 0.0
        self.time_looking = 0

    def _how_interesting(self, head, pt, base, vel):
        dx, dy = pt[0] - head[0], pt[1] - head[1]
        dist = math.hypot(dx, dy)
        interest = base
        if dist < tuning.LOOK_DIST_NEAR:
            interest *= 0.5 * vel + 1.5
        denom = 0.005 * (dist ** 1.5) + 0.995
        return interest / denom

    def _current_interest(self, head, candidates):
        if self.mode == "point":
            return self.point_interest
        for key, pt, base, vel in candidates:
            if key == self.mode:
                return self._how_interesting(head, pt, base, vel)
        return 0.0

    def _look_at_nothing(self):
        self.mode = "nothing"
        self.point = None
        self.time_looking = 0

    def update(self, head, candidates, world_w, world_h):
        """推进一 tick，返回当前 look 点或 None。"""
        self.time_looking += 1
        # 对象已消失 → 谁也不看
        if self.mode not in ("nothing", "point") and not any(c[0] == self.mode for c in candidates):
            self._look_at_nothing()
        # 偶尔瞟屏幕随机点
        if self.rng.random() < tuning.LOOK_GLANCE_PROB * self.look_fac:
            self.point = (self.rng.uniform(0.0, world_w), self.rng.uniform(0.0, world_h * 0.5))
            self.point_interest = tuning.LOOK_GLANCE_INTEREST
            self.mode = "point"
            self.time_looking = 0
        if self.time_looking > 1 and self.rng.random() < tuning.LOOK_UPDATE_PROB * self.look_fac:
            bonus = 0.5 if self.time_looking < tuning.LOOK_INTEREST_DECAY_TICKS else -0.5
            best = self._current_interest(head, candidates) + bonus
            for key, pt, base, vel in candidates:
                hi = self._how_interesting(head, pt, base, vel)
                if hi > best:
                    best = hi
                    self.mode = key
                    self.point = None
                    self.time_looking = 0
            if best < tuning.LOOK_MIN_INTEREST and self.rng.random() < 0.5:
                self._look_at_nothing()
        if self.rng.random() < tuning.LOOK_NOTHING_PROB:
            self._look_at_nothing()
        return self.look_point(candidates)

    def look_point(self, candidates):
        if self.mode == "nothing":
            return None
        if self.mode == "point":
            return self.point
        for key, pt, base, vel in candidates:
            if key == self.mode:
                return pt
        return None
