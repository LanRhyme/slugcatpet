"""雪花粒子 + 边缘霜冻 vignette，强度随 cycle_prog。"""
from __future__ import annotations
import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPixmap, QRadialGradient

from ..core.units import lerp, clampf

_INTENSITY_PEAK = 1.8

VIGNETTE_COLOR = (220, 235, 255)
FLAKE_COLOR = (245, 250, 255)
FLAKE_R_MIN = 0.6
FLAKE_R_MAX = 1.8


def snowfall_intensity(cycle_prog: float) -> float:
    """降雪强度，随 cycle_prog 升（峰值~1.8）。"""
    a = lerp(0.0, 0.6, cycle_prog * 2.0)
    b = clampf((cycle_prog * 3.0) ** 2.5, 0.0, 3.0) * 0.4
    return a + b


class _Flake:
    __slots__ = ("x", "y", "vy", "drift", "phase", "phase_v", "sway", "r", "alpha")


class Snowfall:
    """稀疏雪花池+边缘霜冻 vignette；纯视觉，无碰撞。"""

    def __init__(self, max_flakes, vignette_max, seed=0):
        self.max_flakes = int(max_flakes)
        self.vignette_max = int(vignette_max)
        self._rng = random.Random(0x5170 ^ (int(seed) * 2654435761 & 0xFFFFFFFF))
        self._flakes = []          # 长度随强度伸缩
        self.intensity = 0.0
        self._vignette_pm = None   # 满强度预渲染缓存，尺寸变自动重建
        self._vignette_key = None

    @property
    def active(self) -> bool:
        return self.intensity > 0.001 or bool(self._flakes)

    def _new_flake(self, WL, HL, spread) -> _Flake:
        """生成一片雪花；spread=True 时 y 散布全高。"""
        rng = self._rng
        f = _Flake()
        f.r = rng.uniform(FLAKE_R_MIN, FLAKE_R_MAX)
        depth = (f.r - FLAKE_R_MIN) / (FLAKE_R_MAX - FLAKE_R_MIN)  # 0=远小 1=近大，越近越快越亮
        f.vy = lerp(1.1, 2.8, depth)
        f.drift = rng.uniform(-0.4, 0.4)
        f.phase = rng.uniform(0.0, 2.0 * math.pi)
        f.phase_v = rng.uniform(0.02, 0.06)
        f.sway = rng.uniform(2.0, 7.0)
        f.alpha = lerp(110.0, 220.0, depth)
        f.x = rng.uniform(0.0, WL)
        f.y = rng.uniform(-20.0, HL) if spread else rng.uniform(-30.0, -5.0)
        return f

    def step(self, cycle_prog, WL, HL):
        """推进雪花物理，按强度伸缩密度。"""
        self.intensity = snowfall_intensity(cycle_prog)
        norm = min(self.intensity / _INTENSITY_PEAK, 1.0)
        target = int(round(self.max_flakes * norm))

        kept = []
        for f in self._flakes:
            f.y += f.vy
            f.x += f.drift
            f.phase += f.phase_v
            if f.y > HL + 15.0:
                if len(kept) < target:
                    nf = self._new_flake(WL, HL, spread=False)
                    nf.x = self._rng.uniform(0.0, WL)
                    kept.append(nf)
            else:
                kept.append(f)
        first = not self._flakes
        while len(kept) < target:
            kept.append(self._new_flake(WL, HL, spread=first))
        self._flakes = kept

    def _vignette(self, WL, HL, scale):
        """满强度 vignette 预渲染缓存；绘制时按 setOpacity 调强度。"""
        key = (int(round(WL * scale)), int(round(HL * scale)))
        if self._vignette_key != key:
            pm = QPixmap(key[0], key[1])
            pm.fill(QColor(0, 0, 0, 0))
            painter = QPainter(pm)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.scale(scale, scale)
            rad = math.hypot(WL, HL) * 0.5
            grad = QRadialGradient(QPointF(WL * 0.5, HL * 0.5), rad)
            grad.setColorAt(0.72, QColor(*VIGNETTE_COLOR, 0))
            grad.setColorAt(1.0, QColor(*VIGNETTE_COLOR, self.vignette_max))
            painter.setBrush(QBrush(grad))
            painter.drawRect(QRectF(0.0, 0.0, WL, HL))
            painter.end()
            pm.setDevicePixelRatio(scale)
            self._vignette_pm = pm
            self._vignette_key = key
        return self._vignette_pm

    def draw(self, p, WL, HL, scale=1.0):
        """绘制边缘霜冻 vignette + 雪花，最上层 overlay。"""
        if not self.active:
            return
        norm = min(self.intensity / _INTENSITY_PEAK, 1.0)
        if norm <= 0.0 and not self._flakes:
            return
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        if norm > 0.0 and self.vignette_max > 0:
            p.save()
            p.setOpacity(p.opacity() * norm)
            p.drawPixmap(QPointF(0.0, 0.0), self._vignette(WL, HL, scale))
            p.restore()
        cr, cg, cb = FLAKE_COLOR
        for f in self._flakes:
            a = int(f.alpha * norm)
            if a <= 0:
                continue
            dx = f.x + math.sin(f.phase) * f.sway
            p.setBrush(QColor(cr, cg, cb, min(255, a)))
            p.drawEllipse(QPointF(dx, f.y), f.r, f.r)
        p.restore()
