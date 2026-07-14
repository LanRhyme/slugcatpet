"""蝙蝠渲染状态推进（不画），y↓。"""
from __future__ import annotations
import math

from ..core.units import lerp, clampf
from ..core.gfxmath import _ang_from_up, _rot
from .enums import ItemState

LOWER_CONN = 10.0
LOWER_DROOP = 0.9 * 2.0       # y↓ 取正


def update_render(bat, sub: float) -> None:
    """推进一帧。"""
    bat.last_lower_x, bat.last_lower_y = bat.lower_x, bat.lower_y
    bat.lower_x += bat.lower_vx
    bat.lower_y += bat.lower_vy
    if sub > 0.0 or bat.dead:
        bat.lower_vx *= 0.9
        bat.lower_vy *= 0.9
    else:
        bat.lower_vy += LOWER_DROOP
    if bat.lower_x == bat.x:
        bat.lower_vx += bat._rng.uniform(-0.1, 0.1)       # 重合时抖开
    dx = bat.x - bat.lower_x
    dy = bat.y - bat.lower_y
    dist = math.hypot(dx, dy)
    if dist > 1e-9:
        ux, uy = dx / dist, dy / dist
    else:
        ux, uy = 0.0, 1.0
    vecx = ux * (LOWER_CONN - dist)
    vecy = uy * (LOWER_CONN - dist)
    bat.lower_x -= vecx
    bat.lower_y -= vecy
    bat.lower_vx -= vecx
    bat.lower_vy -= vecy
    if bat.dead:
        _death_wings(bat)
    elif bat.state == ItemState.MOUSE:
        _flutter_wings(bat)
    else:
        _flap_wings(bat)


def _flap_wings(bat) -> None:
    """常态扑翅。"""
    bat.last_steer = bat.steer
    dx, dy = bat.x - bat.lower_x, bat.y - bat.lower_y
    d = math.hypot(dx, dy)
    bat.steer = (dx / d if d > 1e-9 else 0.0) - bat.dir_x
    for w in bat.wings:
        w[1] = w[0]
        w[0] = bat.flap


def _flutter_wings(bat) -> None:
    """被拖拽挣扎乱扑翅。"""
    for w in bat.wings:
        w[1] = w[0]
        w[0] = bat._rng.random()


def _death_wings(bat) -> None:
    """死亡翅垂缓动。"""
    bat.last_steer = bat.steer
    bat.steer *= 0.999
    aim = _ang_from_up(bat.lower_x - bat.x, bat.lower_y - bat.y)
    _, ry = _rot(bat.x - bat.last_x, bat.y - bat.last_y, aim)
    for j, w in enumerate(bat.wings):
        w[1] = w[0]
        w[0] = clampf(lerp(w[0], bat._death_wing[j] - ry * 0.1, 0.3), 0.0, 1.0)
