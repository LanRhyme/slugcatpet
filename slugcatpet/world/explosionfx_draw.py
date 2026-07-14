"""爆炸特效绘制。"""
from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (QBrush, QColor, QLinearGradient, QPainter,
                           QPen, QPolygonF, QRadialGradient)

from ..core.units import inv_lerp, lerp
from .explosionfx import (ExplosionLight, ExplosionSmoke, ExplosionSpikes,
                          FlashingSmoke, ShockWave, SootMark, Spark,
                          split_fx_layers)

_PLUS = QPainter.CompositionMode.CompositionMode_Plus
_OVER = QPainter.CompositionMode.CompositionMode_SourceOver


def _clerp(a, b, t):
    """RGB 三元组 lerp（t 钳 [0,1]）。"""
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return (int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def _smoke_scale(life):
    """烟尺寸曲线：先涨大后收缩。"""
    if life > 0.5:
        return lerp(0.5, 1.0, inv_lerp(1.0, 0.5, life))
    return math.sin(max(life, 0.0) * math.pi)


def _smoke_blobs(s, r, u, sign):
    """主団+随机 lobe 列表：(x,y,半径,权重,相位)；sign 区分两层。"""
    blobs = [(s.x, s.y, r * (1.0 - 0.22 * u), 0.75, 0.0)]
    for ang0, orbit, radf, phase, freq, wrot, erode in s.draw_lobes:
        ang = math.radians(ang0 * sign + s.rotation * wrot
                           + 28.0 * math.sin(phase + u * freq))
        off = r * orbit * (1.0 + 0.35 * u) * (1.0 + 0.15 * math.sin(phase * 1.7 + u * freq * 1.3))
        lr = r * radf * (1.0 - erode * u) * (1.0 + 0.12 * math.cos(phase + u * freq * 0.8))
        if lr > 0.5:
            blobs.append((s.x + math.cos(ang) * off, s.y + math.sin(ang) * off,
                          lr, 0.55, phase))
    return blobs


def _smoke_colors(s, life):
    """两层烟色：COLOR_B→COLOR_A 按寿命 lerp；FlashingSmoke 叠加白闪。"""
    c0 = _clerp(s.COLOR_B, s.COLOR_A, 0.2 + 0.8 * math.sqrt(max(life, 0.0)))
    c1 = _clerp(s.COLOR_B, s.COLOR_A, life)
    if isinstance(s, FlashingSmoke):
        flash = s.flash_t()
        c0 = _clerp(c0, _clerp(s.effect_color, s.white_color, math.pow(flash, 1.2)), flash)
        c1 = _clerp(c1, _clerp(s.effect_color, s.white_color, math.pow(flash, 0.6)), flash)
    return c0, c1


def draw_smoke(p, s):
    life = min(max(s.life, 0.0), 1.0)
    sc = _smoke_scale(life)
    if sc <= 0.0:
        return
    u = 1.0 - life                       # 寿命进度 0→1
    base = min(1.0, math.pow(max(s.life, 0.0), 1.8))
    comp = 0.036 + 0.064 * math.pow(life, 2.2)   # 透明度曲线
    c0, c1 = _smoke_colors(s, life)
    p.setCompositionMode(_OVER)
    p.setPen(Qt.PenStyle.NoPen)
    for col, layer_f, alpha_f, sign in ((c0, 1.1, 0.8, 1.0), (c1, 0.9, 0.6, -1.0)):
        r = 88.0 * s.rad * sc * layer_f
        a = 255.0 * base * alpha_f * comp
        if r <= 0.5 or a < 1.0:
            continue
        for bx, by, br, w, phase in _smoke_blobs(s, r, u, sign):
            aa = int(a * w)
            if aa <= 0:
                continue
            mid = 0.38 + 0.14 * (phase % 1.0)    # 逐 lobe 抖动，外缘碎化
            g = QRadialGradient(QPointF(bx, by), br)
            g.setColorAt(0.0, QColor(*col, aa))
            g.setColorAt(mid, QColor(*col, int(aa * 0.6)))
            g.setColorAt(0.78, QColor(*col, int(aa * 0.2)))
            g.setColorAt(1.0, QColor(*col, 0))
            p.setBrush(QBrush(g))
            p.drawEllipse(QPointF(bx, by), br, br)


def draw_light(p, l):
    life = min(max(l.life, 0.0), 1.0)
    r = l.radius()
    if r <= 0.5:
        return
    c = QPointF(l.x, l.y)
    # 暗盘压底衬亮
    a0 = int(255 * life * l.alpha * 0.5)
    if a0 > 0:
        p.setCompositionMode(_OVER)
        p.setPen(Qt.PenStyle.NoPen)
        g = QRadialGradient(c, r)
        g.setColorAt(0.0, QColor(0, 0, 0, a0))
        g.setColorAt(0.72, QColor(0, 0, 0, a0))
        g.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(g))
        p.drawEllipse(c, r, r)
    # 双层加色光晕，第二层随机偏白
    a1 = int(255 * math.pow(life, 0.5) * l.alpha)
    if a1 <= 0:
        return
    p.setCompositionMode(_PLUS)
    p.setPen(Qt.PenStyle.NoPen)
    col2 = _clerp(l.color, (255, 255, 255), random.random() * math.pow(life, 0.5))
    for col in (l.color, col2):
        g = QRadialGradient(c, r)
        g.setColorAt(0.0, QColor(*col, a1))
        g.setColorAt(1.0, QColor(*col, 0))
        p.setBrush(QBrush(g))
        p.drawEllipse(c, r, r)


def draw_spikes(p, sp):
    p.setCompositionMode(_OVER)
    p.setPen(Qt.PenStyle.NoPen)
    for tip, b1, b2, tip_a, white_t in sp.vertices():
        a = int(255 * tip_a)
        if a <= 0:
            continue
        col = _clerp(sp.color, (255, 255, 255), white_t)
        # 线性渐变近似顶点插值
        g = QLinearGradient(QPointF(*tip), QPointF((b1[0] + b2[0]) / 2, (b1[1] + b2[1]) / 2))
        g.setColorAt(0.0, QColor(*col, a))
        g.setColorAt(1.0, QColor(*col, 0))
        p.setBrush(QBrush(g))
        p.drawPolygon(QPolygonF([QPointF(*tip), QPointF(*b1), QPointF(*b2)]))


def draw_spark(p, s):
    tx, ty = s.ll_x, s.ll_y
    d = math.hypot(s.x - tx, s.y - ty)
    if d < 9.0:                          # 拖尾最短 9px
        if d < 1e-9:
            dx, dy = 0.0, 1.0
        else:
            dx, dy = (tx - s.x) / d, (ty - s.y) / d
        tx, ty = s.x + dx * 9.0, s.y + dy * 9.0
    t = inv_lerp(0.0, 0.1, s.life)       # 濒死拖尾收缩
    tx, ty = lerp(s.x, tx, t), lerp(s.y, ty, t)
    ddx, ddy = s.x - tx, s.y - ty
    dd = math.hypot(ddx, ddy)
    if dd < 1e-9:
        return
    px, py = ddy / dd, -ddx / dd
    p.setCompositionMode(_PLUS)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(*s.color, 255))
    p.drawPolygon(QPolygonF([QPointF(s.x + px, s.y + py),
                             QPointF(s.x - px, s.y - py), QPointF(tx, ty)]))


def draw_shockwave(p, w):
    # shader 效果用双环高光+Plus 近似
    life = min(max(w.life, 0.0), 1.0)
    r = w.radius()
    if r <= 0.5:
        return
    strength = min(1.0, w.intensity * 4.0)
    a = int(255 * strength * (1.0 - life) * 0.9)
    if a <= 0:
        return
    c = QPointF(w.x, w.y)
    p.setCompositionMode(_PLUS)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, a), 2.5))
    p.drawEllipse(c, r, r)
    p.setPen(QPen(QColor(255, 255, 255, int(a * 0.45)), 5.0))
    p.drawEllipse(c, r * 0.88, r * 0.88)


def draw_soot(p, m):
    a = m.alpha()
    if a <= 0.0:
        return
    col = (25, 22, 26)   # 取舍：固定近黑替代调色板
    base = int(200 * a)
    p.setCompositionMode(_OVER)
    p.setPen(Qt.PenStyle.NoPen)
    for ox, oy, r in ((0.0, 0.0, m.rad * 0.72), *m.lobes):
        x, y = m.x + ox * m.flip_x, m.y + oy * m.flip_y
        g = QRadialGradient(QPointF(x, y), r)
        g.setColorAt(0.0, QColor(*col, base))
        g.setColorAt(0.65, QColor(*col, int(base * 0.6)))
        g.setColorAt(1.0, QColor(*col, 0))
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(x, y), r, r)


_DRAW = {ExplosionSmoke: draw_smoke, FlashingSmoke: draw_smoke,
         ExplosionLight: draw_light, ExplosionSpikes: draw_spikes,
         Spark: draw_spark, ShockWave: draw_shockwave, SootMark: draw_soot}


def _draw_sorted(p, fx):
    """按 LAYER 升序绘制一段粒子列表。"""
    for q in sorted(fx, key=lambda q: q.LAYER):
        fn = _DRAW.get(type(q))
        if fn is not None:
            fn(p, q)


def draw_fx_under(p, fx):
    """猫身之下段：焦痕→烟。"""
    _draw_sorted(p, split_fx_layers(fx)[0])


def draw_fx_over(p, fx):
    """猫身之上段：尖刺→火花→光→冲击环。"""
    _draw_sorted(p, split_fx_layers(fx)[1])
