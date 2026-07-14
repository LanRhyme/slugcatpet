"""爆炸特效族粒子推进；y↓，40Hz。"""
from __future__ import annotations

import math
import random

from ..core.units import lerp, inv_lerp

WHITE = (255, 255, 255)

# 取舍：焦痕/烟画猫身下，避免遮挡
UNDER_LAYER_MAX = 1


def split_fx_layers(fx):
    """(under, over)：按 LAYER 分猫身下/上两组。"""
    under = [q for q in fx if q.LAYER <= UNDER_LAYER_MAX]
    over = [q for q in fx if q.LAYER > UNDER_LAYER_MAX]
    return under, over


def rnv():
    """随机单位方向向量。"""
    a = random.random() * 2.0 * math.pi
    return (math.sin(a), math.cos(a))


def _dirvec(ax, ay, bx, by):
    """a→b 单位方向；重合→(0,0)。"""
    dx, dy = bx - ax, by - ay
    d = math.hypot(dx, dy)
    if d < 1e-9:
        return (0.0, 0.0)
    return (dx / d, dy / d)


class ExplosionSmoke:
    """爆炸烟：vel*=0.9，向牵引点吸引。"""
    LAYER = 1
    # 取舍：无调色板，固定暖灰替代
    COLOR_A = (92, 78, 70)
    COLOR_B = (176, 162, 150)

    def __init__(self, x, y, vx, vy, size, floor_y=None):
        self.life = size
        self.last_life = size
        nx, ny = _dirvec(0.0, 0.0, vx, vy)
        self.x = x + nx * (60.0 * random.random())
        self.y = y + ny * (60.0 * random.random())
        self.vx, self.vy = vx, vy
        # y↓ 取负=偏上
        self.get_to_x = x + lerp(-50.0, 50.0, random.random())
        self.get_to_y = y - lerp(-100.0, 400.0, random.random())
        self.rad = lerp(0.6, 1.5, random.random()) * size
        self.rotation = random.random() * 360.0
        self.rot_vel = lerp(-6.0, 6.0, random.random())
        # 取舍：寿命压缩到 40-55 tick
        self.lifetime = lerp(40.0, 55.0, random.random())
        self.floor_y = floor_y
        # draw_lobes[i] = (基准角,轨道偏移比,半径比,相位,波动频率,rotation耦合,侵蚀速率)
        self.draw_lobes = [(random.random() * 360.0,
                            lerp(0.35, 0.7, random.random()),
                            lerp(0.4, 0.68, random.random()),
                            random.random() * 2.0 * math.pi,
                            lerp(2.0, 5.0, random.random()),
                            lerp(-1.0, 1.0, random.random()),
                            lerp(0.15, 0.55, random.random()))
                           for _ in range(random.randrange(2, 4))]

    def update(self):
        self.vx *= 0.9
        self.vy *= 0.9
        dx, dy = _dirvec(self.x, self.y, self.get_to_x, self.get_to_y)
        m = random.random() * 0.04
        self.vx += dx * m
        self.vy += dy * m
        self.rotation += self.rot_vel * math.hypot(self.vx, self.vy)
        self.last_life = self.life
        self.life -= 1.0 / self.lifetime
        alive = self.last_life > 0.0
        self.x += self.vx
        self.y += self.vy
        if self.floor_y is not None and self.y > self.floor_y:  # 无 tile 地形：仅地板反弹近似
            self.y = self.floor_y
            self.vy = -abs(self.vy)
        return alive


class FlashingSmoke(ExplosionSmoke):
    """白闪烟：出生白闪，color_fade_time 帧内衰减回烟色。"""

    def __init__(self, x, y, vx, vy, size, white_color, effect_color,
                 color_fade_time, floor_y=None):
        super().__init__(x, y, vx, vy, size, floor_y)
        self.white_color = white_color
        self.effect_color = effect_color
        self.color_fade_time = float(color_fade_time)
        self.col = 0.0

    def update(self):
        alive = super().update()
        self.col += 1.0
        return alive

    def flash_t(self):
        """白闪强度 0-1。"""
        return inv_lerp(self.color_fade_time, 0.5, self.col)


class ExplosionLight:
    """爆炸光：平坦暗盘+双层加色光晕。"""
    LAYER = 4

    def __init__(self, x, y, rad, alpha, lifetime, color):
        self.x, self.y = x, y
        self.rad = rad
        self.alpha = alpha
        self.lifetime = int(lifetime)
        self.color = color
        self.life = 1.0
        self.last_life = 0.0

    def update(self):
        self.last_life = self.life
        self.life -= 1.0 / self.lifetime
        return self.last_life >= 0.0

    def radius(self):
        return math.pow(max(self.life, 0.0), 0.5) * self.rad


class ExplosionSpikes:
    """尖刺环三角网格。"""
    LAYER = 2

    def __init__(self, x, y, spikes, inner_rad, lifetime, width, length, color):
        self.x, self.y = x, y
        self.inner_rad = inner_rad
        self.lifetime = float(lifetime)
        self.color = color
        self.time = 0
        self.spikes = int(spikes * lerp(0.8, 1.2, random.random()))
        base = random.random() * 360.0
        self.dirs = []
        self.values = []   # values[i] = [length, width, lifetime]
        for i in range(self.spikes):
            deg = (i / self.spikes * 360.0 + base
                   + lerp(-0.5, 0.5, random.random()) * 360.0 / self.spikes)
            r = math.radians(deg)
            self.dirs.append((math.sin(r), math.cos(r)))
            self.values.append([length * lerp(0.6, 1.4, random.random()),
                                width * lerp(0.6, 1.4, random.random()),
                                lifetime * lerp(0.5, 1.5, random.random())])

    def update(self):
        self.time += 1
        return self.time <= self.lifetime * 2.0

    def vertices(self):
        """每刺 (tip, base1, base2, tip_alpha, 白化 t)。"""
        out = []
        for i in range(self.spikes):
            length, width, lt = self.values[i]
            progress = inv_lerp(0.0, lt, float(self.time))     # 0→1 生长进度
            remain = inv_lerp(lt, 0.0, float(self.time))       # 1→0 余寿
            ln = lerp(length * 0.1, length, math.pow(progress, 0.45))
            wd = width * (0.5 + 0.5 * math.sin(progress * math.pi)) * math.pow(remain, 0.3)
            dx, dy = self.dirs[i]
            tip = (self.x + dx * (self.inner_rad + ln), self.y + dy * (self.inner_rad + ln))
            bx = self.x + dx * (self.inner_rad + ln * 0.1)
            by = self.y + dy * (self.inner_rad + ln * 0.1)
            pdx, pdy = _dirvec(tip[0], tip[1], bx, by)
            px, py = pdy, -pdx
            b1 = (bx - px * wd * 0.5, by - py * wd * 0.5)
            b2 = (bx + px * wd * 0.5, by + py * wd * 0.5)
            white_t = math.pow(remain, lerp(0.2, 1.5, progress))
            out.append((tip, b1, b2, math.pow(remain, 0.75), white_t))
        return out


class Spark:
    """Spark：拖尾三角火花，gravity=Lerp(0.4,0.9)、10% 长寿命。"""
    LAYER = 3

    def __init__(self, x, y, vx, vy, color, standard_lifetime, exceptional_lifetime,
                 floor_y=None):
        self.life = 1.0
        self.color = color
        nx, ny = _dirvec(0.0, 0.0, vx, vy)
        self.x = x + nx * (30.0 * random.random())
        self.y = y + ny * (30.0 * random.random())
        self.last_x, self.last_y = x, y
        self.ll_x, self.ll_y = x, y      # 上上帧位置（拖尾端）
        self.vx, self.vy = vx, vy
        self.gravity = lerp(0.4, 0.9, random.random())
        self.lifetime = random.randrange(0, standard_lifetime) if standard_lifetime > 0 else 0
        if random.random() < 0.1:
            self.lifetime = random.randrange(standard_lifetime, exceptional_lifetime)
        self.floor_y = floor_y

    def update(self):
        self.ll_x, self.ll_y = self.last_x, self.last_y
        self.vy += self.gravity          # y↓ 取加
        self.life -= (1.0 / self.lifetime) if self.lifetime > 0 else 2.0
        self.last_x, self.last_y = self.x, self.y
        self.x += self.vx
        self.y += self.vy
        if self.floor_y is not None and self.y >= self.floor_y:
            if self.vy > 0.0:            # 落向地板反弹（无 tile 地形，近似）
                self.y = self.floor_y
                self.vy *= -0.5
                if abs(self.vy) < 3.0:
                    self.life -= 1.0 / 3.0
            else:
                return False
        return self.life > 0.0


class ShockWave:
    """ShockWave：屏幕扭曲用双环高光+Plus 近似替代。"""
    LAYER = 5

    def __init__(self, x, y, size, intensity, lifetime):
        self.x, self.y = x, y
        self.size = size
        self.intensity = intensity
        self.lifetime = int(lifetime)
        self.life = 0.0
        self.last_life = 0.0

    def update(self):
        self.last_life = self.life
        self.life += 1.0 / self.lifetime
        return self.last_life <= 1.0

    def radius(self):
        return math.pow(min(max(self.life, 0.0), 1.0), 0.5) * self.size


class SootMark:
    """静态焦痕。取舍：固定近黑替代调色板，限时淡出替代永驻。"""
    LAYER = 0
    FADE_TICKS = 400     # 淡出总寿命

    def __init__(self, x, y, rad, floor_y=None):
        self.x, self.y = x, y
        self.rad = rad
        self.rotation = random.random() * 360.0
        self.flip_x = (-1.0 if random.random() < 0.5 else 1.0) * lerp(0.9, 1.1, random.random())
        self.flip_y = (-1.0 if random.random() < 0.5 else 1.0) * lerp(0.9, 1.1, random.random())
        # 无 tile 地形，贴地/悬空简化
        near = floor_y is not None and y + min(30.0, rad * 0.3) >= floor_y
        self.fade = 1.0 if near else 0.85
        self.age = 0
        # 不规则焦痕 lobes，一次生成
        self.lobes = [(lerp(-0.45, 0.45, random.random()) * rad,
                       lerp(-0.45, 0.45, random.random()) * rad,
                       lerp(0.35, 0.7, random.random()) * rad) for _ in range(5)]

    def update(self):
        self.age += 1
        return self.age <= self.FADE_TICKS

    def alpha(self):
        """0-1：前 60% 稳态 fade，后 40% 线性淡出。"""
        t = self.age / self.FADE_TICKS
        k = 1.0 if t < 0.6 else max(0.0, 1.0 - (t - 0.6) / 0.4)
        return self.fade * k


def _floor(win):
    return getattr(win, "_HL", None)


def spawn_pyro_jump_fx(win, x, y, direction=0):
    """火箭跳特效：8 烟+光+10 火花；direction 未使用。"""
    fl = _floor(win)
    for _ in range(8):
        dx, dy = rnv()
        m = 5.0 * random.random()
        win.fx.append(ExplosionSmoke(x, y, dx * m, dy * m, 1.0, fl))
    win.fx.append(ExplosionLight(x, y, 160.0, 1.0, 3, WHITE))
    for _ in range(10):
        dx, dy = rnv()
        off = random.random() * 40.0
        m = lerp(4.0, 30.0, random.random())
        win.fx.append(Spark(x + dx * off, y + dy * off, dx * m, dy * m, WHITE, 4, 18, fl))


def spawn_parry_fx(win, x, y):
    """地面爆炸/parry 特效：同火箭跳 + ShockWave(200,0.2,6)。"""
    spawn_pyro_jump_fx(win, x, y)
    win.fx.append(ShockWave(x, y, 200.0, 0.2, 6))


def spawn_pyro_death_fx(win, x, y):
    """自爆特效：焦痕+双层光+尖刺+冲击环+25×火花/烟。"""
    fl = _floor(win)
    win.fx.append(SootMark(x, y, 80.0, fl))
    win.fx.append(ExplosionLight(x, y, 280.0, 1.0, 7, WHITE))
    win.fx.append(ExplosionLight(x, y, 230.0, 1.0, 3, WHITE))
    win.fx.append(ExplosionSpikes(x, y, 14, 30.0, 9.0, 7.0, 170.0, WHITE))
    win.fx.append(ShockWave(x, y, 430.0, 0.045, 5))
    for _ in range(25):
        dx, dy = rnv()
        if fl is not None and y + dy * 20.0 > fl:   # 无 tile 地形，朝地束流翻向近似
            dx, dy = -dx, -dy
        for _ in range(3):
            off = lerp(30.0, 60.0, random.random())
            m = lerp(7.0, 38.0, random.random())
            jx, jy = rnv()
            jm = 20.0 * random.random()
            win.fx.append(Spark(x + dx * off, y + dy * off,
                                dx * m + jx * jm, dy * m + jy * jm, WHITE, 11, 28, fl))
        # 取舍：烟量减到 40% 概率一颗
        if random.random() < 0.4:
            off = 40.0 * random.random()
            m = lerp(4.0, 20.0, math.pow(random.random(), 2.0))
            win.fx.append(FlashingSmoke(x + dx * off, y + dy * off, dx * m, dy * m,
                                        1.0 + 0.05 * random.random(), WHITE, WHITE,
                                        random.randrange(3, 11), fl))


def spawn_overheat_smoke(win, x, y):
    """过热警告单粒子：烟（25% 概率归调用方）。"""
    dx, dy = rnv()
    m = 2.0 * random.random()
    win.fx.append(ExplosionSmoke(x, y, dx * m, dy * m, 1.0, _floor(win)))


def spawn_overheat_spark(win, x, y):
    """过热警告单粒子：火花（50% 概率归调用方）。"""
    dx, dy = rnv()
    win.fx.append(Spark(x, y, dx, dy, WHITE, 4, 8, _floor(win)))
