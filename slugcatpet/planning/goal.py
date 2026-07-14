"""规划目标：点 / 物体统一封装为 pos()+valid()+key()；radius 为达成容差（仅 can_stay 采信）。"""
from __future__ import annotations


class Goal:
    """目标：pos()/valid()/key() + radius 到位容差；contact 声明达成方式，仅补救层读。"""
    __slots__ = ("obj", "radius", "contact", "_pos_fn", "_valid_fn", "_key")

    def __init__(self, pos_fn, valid_fn, key, obj=None, radius=0.0, contact="body"):
        self._pos_fn = pos_fn
        self._valid_fn = valid_fn
        self._key = key
        self.obj = obj
        self.radius = float(radius)
        self.contact = contact

    def pos(self):
        return self._pos_fn()

    def valid(self):
        return bool(self._valid_fn())

    def key(self):
        return self._key


def point_goal(x, y, radius=0.0, contact="body"):
    """固定点目标。"""
    x, y = float(x), float(y)
    return Goal(lambda: (x, y), lambda: True, ("pt", x, y), radius=radius, contact=contact)


def obj_goal(obj, valid=None, radius=0.0, contact="body"):
    """物体目标：坐标随 obj.x/obj.y 每帧更新；valid 为接收 obj 的谓词，缺省恒真。"""
    vf = (lambda: valid(obj)) if valid is not None else (lambda: True)
    return Goal(lambda: (obj.x, obj.y), vf, ("obj", id(obj)), obj=obj,
                radius=radius, contact=contact)
