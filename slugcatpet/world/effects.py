"""Runtime visual effects and cursor hijack helpers for ``PetWindow``."""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter


class EffectsMixin:
    def add_spark(self, x, y, vx, vy, white=True, life=80):
        self.sparks.append([x, y, vx, vy, float(life), float(life), white])

    def add_shockwave(self, x, y, maxr, flash=False):
        life = 8.0 if flash else 12.0
        self.shockwaves.append([x, y, 0.0, float(maxr), life, life, flash])

    def _cursor_to_device(self, logical_x, logical_y):
        dpr = self.devicePixelRatioF()
        return ((self._area.x() + logical_x * self._scale) * dpr,
                (self._area.y() + logical_y * self._scale) * dpr)

    def start_cursor_hijack(self, logical_x, logical_y, lock_ticks=None):
        from ..platform.cursorfx import CursorHijack

        dpr = self.devicePixelRatioF()
        dev_x, dev_y = self._cursor_to_device(logical_x, logical_y)
        kw = {} if lock_ticks is None else {"lock_ticks": lock_ticks}
        self.cursor_hijack = CursorHijack(
            dev_x, dev_y, self._area.width() * dpr, self._area.height() * dpr,
            self._area.x() * dpr, self._area.y() * dpr, **kw)

    def start_cursor_hold(self, logical_x, logical_y, max_ticks):
        from ..platform.cursorfx import CursorHijack

        dpr = self.devicePixelRatioF()
        dev_x, dev_y = self._cursor_to_device(logical_x, logical_y)
        self.cursor_hijack = CursorHijack(
            dev_x, dev_y, self._area.width() * dpr, self._area.height() * dpr,
            self._area.x() * dpr, self._area.y() * dpr,
            mode="hold", watchdog_max=max_ticks)
        return self.cursor_hijack

    def move_cursor_hold(self, logical_x, logical_y):
        hj = self.cursor_hijack
        if hj is not None and hj.mode == "hold" and hj.active:
            hj.hold_at(*self._cursor_to_device(logical_x, logical_y))

    def stop_cursor_hijack(self):
        if self.cursor_hijack is not None:
            self.cursor_hijack.release()
            self.cursor_hijack = None

    def _update_fx(self):
        alive = []
        for s in self.sparks:
            s[0] += s[2]
            s[1] += s[3]
            s[3] += 0.45
            s[2] *= 0.93
            s[3] *= 0.93
            s[4] -= 1.0
            if s[4] > 0:
                alive.append(s)
        self.sparks = alive

        sw = []
        for w in self.shockwaves:
            w[4] -= 1.0
            t = 1.0 - w[4] / w[5]
            w[2] = w[3] * (t ** 0.5)
            if w[4] > 0:
                sw.append(w)
        self.shockwaves = sw

        # fx: update() 返回 False 即剔除
        if self.fx:
            self.fx = [q for q in self.fx if q.update()]

        # 无水面则清空
        if self.bubbles:
            surf = self.water_surface
            if surf is None:
                self.bubbles = []
            else:
                self.bubbles = [b for b in self.bubbles
                                if b.update(surf.level_at(b.x), self._bubble_rng)]

        if self.cursor_hijack is not None and not self.cursor_hijack.update():
            self.cursor_hijack = None

    def _draw_fx_under(self, p):
        # 焦痕/烟层，画在猫身体之下
        if not self.fx:
            return
        from .explosionfx_draw import draw_fx_under
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        draw_fx_under(p, self.fx)
        p.restore()

    def _draw_fx(self, p):
        # 各猫独占全屏特效（如业力眼）
        pet_fx = [fx for fx in (pet.behavior.exclusive_fx()
                                for pet in self.pets if pet.behavior is not None)
                  if fx is not None]
        if not (self.shockwaves or self.sparks or self.fx or pet_fx):
            return
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        from PySide6.QtGui import QPen
        for w in self.shockwaves:
            a = int(200 * (w[4] / w[5]))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(255, 255, 255, a), 1.4))
            p.drawEllipse(QPointF(w[0], w[1]), w[2], w[2])
        p.setPen(Qt.PenStyle.NoPen)
        for s in self.sparks:
            a = int(230 * (s[4] / s[5]))
            p.setBrush(QColor(255, 255, 240, a) if s[6] else QColor(*self.layout_data.tint, a))
            p.drawEllipse(QPointF(s[0], s[1]), 0.9, 0.9)
        # 尖刺/火花/光/环层
        if self.fx:
            from .explosionfx_draw import draw_fx_over
            draw_fx_over(p, self.fx)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        for fx in pet_fx:
            fx.draw(p)
        p.restore()
