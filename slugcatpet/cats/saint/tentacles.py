"""幽灵触手 GhostTentacle：飞升时的发光软触手；坐标 y↓。"""
from __future__ import annotations
import math
import random
import colorsys


def deg_to_vec_qt(ang_deg):
    a = math.radians(ang_deg)
    return (math.sin(a), -math.cos(a))


class GhostTentacle:
    """单条软体触手链。"""

    def __init__(self, root_x, root_y, length=100.0, seed=0):
        self.length = float(length)
        n = int(max(1.0, min(200.0, length / 20.0)))
        self.n = n
        rng = random.Random(seed)
        # seg[i] = [px, py, lx, ly, vx, vy]
        self.seg = []
        for _ in range(n):
            vx, vy = deg_to_vec_qt(rng.random() * 360.0)
            r = rng.random()
            self.seg.append([root_x, root_y, root_x, root_y, vx * r, vy * r])
        self.conRad = length / n * 1.5
        self.wind_x = 0.0
        self.wind_y = 0.0
        self.lengthFactor = 0.0
        self.activeUpdateTime = 0
        self.posB = (root_x, root_y)
        self._rng = rng

    def set_position(self, x, y):
        self.posB = (x, y)
        s0 = self.seg[0]
        s0[0] = s0[2] = x
        s0[1] = s0[3] = y

    def _connect(self, A, B):                            # 软距离约束
        a = self.seg[A]
        b = self.seg[B]
        dx = a[0] - b[0]
        dy = a[1] - b[1]
        d = math.hypot(dx, dy)
        if d < 1e-6:
            return
        nx, ny = dx / d, dy / d
        t = 0.0 if self.conRad <= 0 else max(0.0, min(1.0, d / self.conRad))
        m = (self.conRad - d) * 0.5 * t
        mx, my = nx * m, ny * m
        a[0] += mx; a[4] += mx; a[1] += my; a[5] += my
        b[0] -= mx; b[4] -= mx; b[1] -= my; b[5] -= my

    def update(self):  # 弯曲传播 → 风力积分 → 距离约束两遍
        n = self.n
        self.conRad = self.length * self.lengthFactor / n * 1.5
        wvx, wvy = deg_to_vec_qt(self._rng.random() * 360.0)
        r = self._rng.random()
        self.wind_x += wvx * 0.2 * r
        self.wind_y += wvy * 0.2 * r
        wl = math.hypot(self.wind_x, self.wind_y)
        if wl > 1.0:
            self.wind_x /= wl
            self.wind_y /= wl
        for i in range(2, n):
            ax, ay = self.seg[i - 2][0], self.seg[i - 2][1]
            bx, by = self.seg[i][0], self.seg[i][1]
            dx, dy = bx - ax, by - ay
            d = math.hypot(dx, dy)
            vx, vy = (0.0, 1.0) if d < 1e-6 else (dx / d, dy / d)
            self.seg[i - 2][4] -= vx * 0.15
            self.seg[i - 2][5] -= vy * 0.15
            self.seg[i][4] += vx * 0.15
            self.seg[i][5] += vy * 0.15
        pbx, pby = self.posB
        for j in range(n):
            frac = j / (n - 1) if n > 1 else 0.0          # 根 0 → 尖 1
            s = self.seg[j]
            s[2] = s[0]; s[3] = s[1]
            s[0] += s[4]; s[1] += s[5]
            s[4] *= 0.999; s[5] *= 0.999
            s[4] += self.wind_x * 0.005
            s[5] += self.wind_y * 0.005
            if frac > 0.5:                                # 尖半段往根回拉
                rx, ry = pbx - s[0], pby - s[1]
                rl = math.hypot(rx, ry)
                if rl > 40.0:
                    rx, ry = rx / rl * 40.0, ry / rl * 40.0
                w = max(0.0, min(1.0, (frac - 0.75) / 0.25))
                s[4] += rx / 420.0 * w
                s[5] += ry / 420.0 * w
        for k in range(n - 1, 0, -1):
            self._connect(k, k - 1)
        for m in range(1, n):
            self._connect(m, m - 1)

    def active_update(self):                             # 生长
        self.lengthFactor += (1.0 - self.lengthFactor) * 0.01
        self.activeUpdateTime += 1
        if self.activeUpdateTime == 1:
            s0 = self.seg[0]
            for i in range(1, self.n):
                self.seg[i][0] = s0[0]; self.seg[i][1] = s0[1]
                self.seg[i][2] = s0[2]; self.seg[i][3] = s0[3]

    def inactive_update(self):                           # 收缩
        if self.lengthFactor <= 0.01:
            self.lengthFactor = 0.0
        else:
            self.lengthFactor += (0.0 - self.lengthFactor) * 0.01

    @staticmethod
    def _rad(f):  # 纺锤包络半径
        return 0.2 + (1.0 - 0.2) * math.sqrt(max(0.0, min(1.0, math.sin(f * math.pi))))

    @staticmethod
    def _mesh_color(f):                                  # → (r,g,b) 0..255
        f = abs(f - 0.5) * 2.0
        e = 0.5 + 0.5 * (f ** 3)
        h = (0.4 + (0.1 - 0.4) * e) % 1.0
        s = (0.4 + (0.1 - 0.4) * e) % 1.0
        l = 0.1 + (0.02 - 0.1) * max(0.0, min(1.0, (f - 0.7) / 0.3))
        r, g, b = colorsys.hls_to_rgb(h, l, s)
        return (int(r * 255), int(g * 255), int(b * 255))

    def build_centerline(self, ts):
        """返回 (points, halfwidths, colors) 供 render.ribbon 带状填充。"""
        n = self.n

        def lerp_pos(s):
            return (s[2] + (s[0] - s[2]) * ts, s[3] + (s[1] - s[3]) * ts)

        pts = [lerp_pos(s) for s in self.seg]
        hws = [self._rad(i / (n - 1) if n > 1 else 0.0) * 3.0 for i in range(n)]
        cols = [self._mesh_color(i / (n - 1) if n > 1 else 0.0) for i in range(n)]
        return pts, hws, cols
