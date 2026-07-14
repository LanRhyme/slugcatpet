"""溪流招牌鳃：6 片鳞锚头 chunk，随视线/体轴扇形摆动。内部 y↑，入口/渲染各转一次 y。"""
from __future__ import annotations
import math


# 向量辅助（y↑）
def _rotate_vec_deg(vx, vy, deg):
    r = -math.radians(deg)                      # 取负：旋向取反
    c, s = math.cos(r), math.sin(r)
    return vx * c - vy * s, vx * s + vy * c


def _dir_vec(ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    d = math.hypot(dx, dy)
    if d < 1e-9:
        return 0.0, 1.0                         # 重合返 (0,1)
    return dx / d, dy / d


def _vec_to_deg(vx, vy):
    return math.degrees(math.atan2(vx, vy))     # atan2(x,y)，正上=0°


def _clamp_mag(vx, vy, m):
    d = math.hypot(vx, vy)
    if d > m and d > 1e-9:
        return vx / d * m, vy / d * m
    return vx, vy


def _lerp(a, b, t):
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)   # t 钳 [0,1]
    return a + (b - a) * t


def _lerp_vec(ax, ay, bx, by, t):
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)   # t 钳 [0,1]
    return ax + (bx - ax) * t, ay + (by - ay) * t


def _inv_lerp(a, b, v):
    if a == b:
        return 0.0
    t = (v - a) / (b - a)
    return 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)


# 鳃形状参数（固定采样值）
_GILL_RIGOR = 0.5873646        # 拉拽响应/阻尼插值 t
_GILL_SIZE_FAC = 1.310689      # 长/宽插值共乘
_GILL_WIDTH_FAC = 0.1542603
_GILL_BACK_FAC = 0.1759363     # ×每排后倾率=该排后倾度
_GILL_ROW_ANCHOR_Y = (0.03570603, 0.02899241, 0.02639332)   # 每排锚高（占身高比例）
_GILL_ROW_LEN_FAC = (0.9722961, 0.6056554, 0.7223744)
_GILL_ROW_BACK_FAC = (0.3644831, 0.9129724, 0.4567381)


class _Scale:
    """单片鳃鳞：显式速度质点 + 定长点约束（内部 y↑）。"""
    __slots__ = ("x", "y", "lx", "ly", "vx", "vy", "length", "width")

    def __init__(self, x, y, length, width):
        self.x = self.lx = x
        self.y = self.ly = y
        self.vx = self.vy = 0.0
        self.length = length
        self.width = width

    def connect_to_point(self, px, py, conn):
        # 定长点约束：拉回距 conn 处，速度同步
        dist = math.hypot(self.x - px, self.y - py)
        ux, uy = _dir_vec(self.x, self.y, px, py)
        vx, vy = ux * (conn - dist), uy * (conn - dist)
        self.x -= vx
        self.y -= vy
        self.vx -= vx
        self.vy -= vy

    def update(self, submerged: bool = False):
        damp = 0.5 if submerged else 0.9
        self.vx *= damp
        self.vy *= damp
        self.lx, self.ly = self.x, self.y
        self.x += self.vx
        self.y += self.vy


class Gills:
    """鳃扇：6 片鳞（3 排×2 侧），锚头 chunk 扇形张开 90°，随 look/体轴偏摆。"""

    def __init__(self, head_x, head_y, hip_x, hip_y, graphic_height):
        self.rigor = _GILL_RIGOR
        self.graphic_height = graphic_height        # 渲染纵向缩放=length/此值
        self.scales: list[_Scale] = []
        self.scales_y: list[float] = []             # 各鳞锚高（占身高比例）
        self.backwards: list[float] = []
        hx, hy = head_x, -head_y                     # y↓→y↑；初值锚头避免出生闪跳
        for row in range(len(_GILL_ROW_ANCHOR_Y)):
            length = _lerp(2.5, 15.0, _GILL_SIZE_FAC * _GILL_ROW_LEN_FAC[row])
            width = _lerp(0.65, 1.2, _GILL_WIDTH_FAC * _GILL_SIZE_FAC)
            back = _GILL_BACK_FAC * _GILL_ROW_BACK_FAC[row]
            for _ in range(2):
                self.scales.append(_Scale(hx, hy, length, width))
                self.scales_y.append(_GILL_ROW_ANCHOR_Y[row])
                self.backwards.append(back)

    def update(self, head_x, head_y, hip_x, hip_y, look_x, look_y, submerged=False):
        """驱动一帧；submerged→水下阻尼。"""
        hx0, hy0 = head_x, -head_y
        hipx, hipy = hip_x, -hip_y
        look_deg = _vec_to_deg(look_x, -look_y)
        look_amt = abs(look_deg)
        rigor = self.rigor
        n = len(self.scales)
        half = n // 2
        fan_deg = 90.0
        gap_deg = fan_deg / half
        pull_denom = _lerp(5.0, 1.5, rigor)
        vel_damp = _lerp(1.0, 0.8, rigor)
        # 用体轴代替世界上向：桌宠会横身/反重力
        bux, buy = _dir_vec(hipx, hipy, hx0, hy0)
        for i in range(n):
            sc = self.scales[i]
            posx, posy = hx0, hy0
            slot = i % half
            side = 5.0 if i >= half else -5.0          # 右半+5/左半-5，对应体轴垂向偏移
            posx += buy * side                          # 体轴垂向=(buy,-bux)
            posy += -bux * side
            base = slot * gap_deg - fan_deg / 2.0     # 槽内均布，居中 ±45°
            outx, outy = _rotate_vec_deg(bux, buy, base + 90.0)
            fanx, fany = _rotate_vec_deg(bux, buy, base)
            dvx, dvy = _dir_vec(hipx, hipy, posx, posy)    # 髋→头方向（已偏±5）
            ax, ay = _lerp_vec(fanx, fany, dvx, dvy, look_amt)
            if self.scales_y[i] < 0.2:                # 恒真：低位鳞外推
                factor = (_inv_lerp(0.2, 0.0, self.scales_y[i]) ** 2) * 2.0
                ax -= outx * factor
                ay -= outy * factor
            ax, ay = _lerp_vec(ax, ay, fanx, fany, self.backwards[i])
            d = math.hypot(ax, ay)
            if d > 1e-9:
                ax, ay = ax / d, ay / d
            length = sc.length
            tipx, tipy = posx + ax * length, posy + ay * length
            if math.hypot(sc.x - tipx, sc.y - tipy) >= length / 2.0:   # 超半长→拉回定长半径内
                dirx, diry = _dir_vec(sc.x, sc.y, tipx, tipy)
                over = math.hypot(sc.x - tipx, sc.y - tipy) - length / 2.0
                sc.x += dirx * over
                sc.y += diry * over
                sc.vx += dirx * over
                sc.vy += diry * over
            cmx, cmy = _clamp_mag(tipx - sc.x, tipy - sc.y, 10.0)
            sc.vx += cmx / pull_denom
            sc.vy += cmy / pull_denom
            sc.vx *= vel_damp
            sc.vy *= vel_damp
            sc.connect_to_point(posx, posy, length)
            sc.update(submerged)
