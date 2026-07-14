"""slugcat 尾巴：4 段显式速度质点，绳套约束+扇出力，坐标系 y↓。"""
from __future__ import annotations
import math

from .units import K_IMP, damp60, clampf


class TailSeg:
    """尾段（显式速度质点）。"""
    __slots__ = ("x", "y", "lx", "ly", "vx", "vy", "rad", "conn", "sfric", "affect", "stretched")

    def __init__(self, x, y, rad, conn, sfric, affect):
        self.x = self.lx = x
        self.y = self.ly = y
        self.vx = self.vy = 0.0
        self.rad = rad
        self.conn = conn
        self.sfric = sfric
        self.affect = affect
        self.stretched = 1.0

    @property
    def srad(self) -> float:          # 拉伸变细，下限 0.2×
        return self.rad * self.stretched


class Tail:
    """slugcat 尾巴：4 段 + 每帧驱动。"""
    RAD = (6.0, 4.0, 2.5, 1.0)
    CONN = (4.0, 7.0, 7.0, 7.0)
    SFRIC = 0.85
    AFFECT = (1.0, 0.5, 0.5, 0.5)

    def __init__(self, root_x: float, root_y: float):
        self.segs = [TailSeg(root_x, root_y + sum(Tail.CONN[:i + 1]),
                             Tail.RAD[i], Tail.CONN[i], Tail.SFRIC, Tail.AFFECT[i])
                     for i in range(4)]
        self.floor_y = None
        # 可调旋钮：存每 tick 原始量，施加时按需 ×K_IMP
        self.fan = 28.0                             # 扇出力，逐段 ÷2
        self.leash = 9.0                            # 拴绳长度，不换算
        self.grav_taut, self.grav_loose = 0.1, 0.5
        self.damp_taut, self.damp_loose = 0.75, 0.95

    def snap_to(self, root_x: float, root_y: float) -> None:
        """整尾吸附到根部初始直线（重置）。"""
        for i, s in enumerate(self.segs):
            s.x = s.lx = root_x
            s.y = s.ly = root_y + sum(Tail.CONN[:i + 1])
            s.vx = s.vy = 0.0
            s.stretched = 1.0

    def step(self, root_x, root_y, hip_x, hip_y, head_x, head_y,
             loose_base: float, gravity_norm: float = 1.0) -> None:
        """推进一帧。"""
        segs = self.segs
        loose = loose_base
        rx, ry = head_x, head_y            # ref，初值=head
        px, py = hip_x, hip_y             # prev2，初值=hip
        F = self.fan * K_IMP
        # 约束写 pos ×1，写 vel ×K_IMP
        KI = K_IMP
        for l, s in enumerate(segs):
            s.lx, s.ly = s.x, s.y
            s.x += s.vx
            s.y += s.vy                    # 阻尼=1，不衰减
            s.stretched = 1.0
            if l == 0:
                d = math.hypot(root_x - s.x, root_y - s.y)
                if d > s.conn and d > 1e-9:
                    ux, uy = (root_x - s.x) / d, (root_y - s.y) / d
                    over = s.conn - d
                    cx, cy = ux * over, uy * over
                    s.x -= cx; s.y -= cy                       # ×1
                    s.vx -= cx * KI; s.vy -= cy * KI           # ×K_IMP
                    s.stretched = clampf((s.conn / (d * 0.5) + 2.0) / 3.0, 0.2, 1.0)
            else:                                               # 段间按 affect 分给上一段
                prev = segs[l - 1]
                d = math.hypot(prev.x - s.x, prev.y - s.y)
                if d > s.conn and d > 1e-9:
                    ux, uy = (prev.x - s.x) / d, (prev.y - s.y) / d
                    over = s.conn - d
                    a = s.affect
                    cs_x, cs_y = ux * over * (1.0 - a), uy * over * (1.0 - a)
                    cp_x, cp_y = ux * over * a, uy * over * a
                    s.x -= cs_x; s.y -= cs_y                   # ×1
                    s.vx -= cs_x * KI; s.vy -= cs_y * KI      # ×K_IMP
                    prev.x += cp_x; prev.y += cp_y             # 回拉上一段 ×1
                    prev.vx += cp_x * KI; prev.vy += cp_y * KI  # ×K_IMP
                    s.stretched = clampf((s.conn / (d * 0.5) + 2.0) / 3.0, 0.2, 1.0)
            # 地面碰撞，约束后扇出前
            if self.floor_y is not None:
                lim = self.floor_y - s.rad
                if s.y > lim:
                    s.y = lim
                    if s.vy > 0.0:
                        s.vy = 0.0
                    s.vx *= s.sfric
            damp = damp60(self.damp_taut + (self.damp_loose - self.damp_taut) * loose)
            s.vx *= damp
            s.vy *= damp
            g = (self.grav_taut + (self.grav_loose - self.grav_taut) * loose) * gravity_norm
            s.vy += g * K_IMP                              # y↓
            loose = (loose * 10.0 + 1.0) / 11.0           # 尾尖比尾根更飘
            ld = self.leash * (l + 1)                      # 长度量，不换算
            dxh, dyh = s.x - hip_x, s.y - hip_y
            dh = math.hypot(dxh, dyh)
            if dh > ld and dh > 1e-9:
                s.x = hip_x + dxh / dh * ld
                s.y = hip_y + dyh / dh * ld
            fdx, fdy = s.x - rx, s.y - ry                 # ref→seg 方向
            fd = math.hypot(fdx, fdy)
            if fd < 0.5:                                  # 防爆下限，勿改
                fd = 0.5
            inv = F / (fd * fd)
            s.vx += fdx * inv
            s.vy += fdy * inv
            F *= 0.5
            rx, ry = px, py                               # ref ← prev2
            px, py = s.x, s.y                             # prev2 ← 本段
