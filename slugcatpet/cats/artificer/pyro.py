"""工匠手操爆炸跳（y 已翻转）。"""
from __future__ import annotations

import math
import random

from ...core.units import inv_lerp, lerp
from ...world.explosionfx import (spawn_overheat_smoke, spawn_overheat_spark,
                                  spawn_parry_fx, spawn_pyro_death_fx,
                                  spawn_pyro_jump_fx)


def _dirvec(ax, ay, bx, by):
    """a→b 单位方向；重合→(0,0)。本地实现避免拉入 Qt。"""
    dx, dy = bx - ax, by - ay
    d = math.hypot(dx, dy)
    if d < 1e-9:
        return (0.0, 0.0)
    return (dx / d, dy / d)

CAPACITY = 10           # counter≥此→自爆
WARN_AT = 5             # 过热警告阈（随 CAPACITY 走 max(1,容量-5)）
OVERHEAT_AT = 7         # 眩晕惩罚阈（随 CAPACITY 走 max(1,容量-3)）
JUMP_COOLDOWN = 150.0
PARRY_COOLDOWN = 40.0
PARRY_STONE_R = 300.0
PARRY_CAT_R = 200.0
PARRY_STUN = 80
PARRY_KNOCK = 30.0
DEATH_RAD = 350.0       # 自爆力场：半径/力/最低眩晕
DEATH_FORCE = 26.2
DEATH_MIN_STUN = 160.0

# 需与 session.RESET_TABLE 同步（有测试断言）
PYRO_DEFAULTS: dict[str, object] = {
    "_ctrl_pyro_jumped": False,      # 复位前不可再爆
    "_ctrl_pyro_counter": 0,         # 随时间回落
    "_ctrl_pyro_cooldown": 0.0,
    "_ctrl_pyro_parry_cd": 0.0,
}


def ensure(body) -> None:
    """惰性补齐 pyro 状态字段（正常入口已按 RESET_TABLE 置默认）。"""
    for k, v in PYRO_DEFAULTS.items():
        if not hasattr(body, k):
            setattr(body, k, v)


def _push_angle(ax, ay, bx, by):
    """爆炸推角：a→b 方向朝「上」插值 20%；pet 上=(0,-1)。"""
    dx, dy = _dirvec(ax, ay, bx, by)
    if dx == 0.0 and dy == 0.0:
        return (0.0, -1.0)
    a = math.atan2(dx, -dy) * 0.8       # 收 20%
    return (math.sin(a), -math.cos(a))


def pyro_explosion(pet, body) -> None:
    """工匠自爆的爆炸部分（不含死亡终态）：特效+力场推邻猫+抖窗。"""
    body._ctrl_pyro_counter = CAPACITY
    c0 = body.chunk0
    x = lerp(c0.x, c0.last_x, 0.35)          # 当前位与上帧位 35% 回插
    y = lerp(c0.y, c0.last_y, 0.35)
    spawn_pyro_death_fx(pet, x, y)
    for other in getattr(pet, "pets", ()):
        if other is pet or getattr(other, "body", None) is None:
            continue
        is_art = getattr(getattr(other, "cat", None), "key", None) == "artificer"
        frc = DEATH_FORCE * (0.25 if is_art else 1.0)   # 工匠受力×0.25
        best = 0.0
        for ch in (other.body.chunk0, other.body.chunk1):
            d = math.hypot(ch.x - x, ch.y - y)
            if d >= DEATH_RAD:
                continue
            t = inv_lerp(DEATH_RAD, DEATH_RAD * 0.25, d)
            if t <= 0.0:
                continue
            pxv, pyv = _push_angle(x, y, ch.x, ch.y)
            imp = frc / ch.mass * t
            ch.vx += pxv * imp
            ch.vy += pyv * imp
            ch.x += pxv * imp * 0.1
            ch.y += pyv * imp * 0.1
            best = max(best, t)
        if best > 0.0 and not is_art:
            ticks = int(DEATH_MIN_STUN * inv_lerp(0.0, 0.5, best))
            beh = getattr(other, "behavior", None)
            if beh is not None:
                beh.apply_stun(ticks)
            else:
                other.body.stun = max(getattr(other.body, "stun", 0), ticks)
    cb = getattr(body, "impact_cb", None)          # 窗口抖动
    if cb is not None:
        cb(c0, (0, 1), DEATH_FORCE, 1.3, 0.0, 6.0)


def tick_fuel(pet, body) -> None:
    """每 tick 燃料回落+冷却+过热警告。"""
    if body._ctrl_pyro_counter > 0:
        body._ctrl_pyro_cooldown -= 1.0
        if body._ctrl_pyro_cooldown <= 0.0:
            body._ctrl_pyro_cooldown = 40.0 if body._ctrl_pyro_counter >= WARN_AT else 60.0
            body._ctrl_pyro_counter -= 1
    body._ctrl_pyro_parry_cd -= 1.0
    if body._ctrl_pyro_counter >= WARN_AT:
        c0 = body.chunk0
        if random.random() < 0.25:
            spawn_overheat_smoke(pet, c0.x, c0.y)
        if random.random() < 0.5:
            spawn_overheat_spark(pet, c0.x, c0.y)


def fire_air_jump(pet, body, ix, iy) -> None:
    """空中爆跳发射。"""
    c0 = body.chunk0
    spawn_pyro_jump_fx(pet, c0.x, c0.y, ix)
    if body.bodyMode == "ZeroG" or body.room_gravity == 0.0:
        _zerog_burst(body, ix, iy)
    else:
        body.pyro_boost(ix, iy, overheat=body._ctrl_pyro_counter >= OVERHEAT_AT)
    body._ctrl_pyro_counter += 1
    body._ctrl_pyro_cooldown = JUMP_COOLDOWN
    apply_penalties(pet, body)


def _zerog_burst(body, ix, iy) -> None:
    """零重力爆冲（y 翻号）：无输入随机方向，vel 9/8。"""
    nx, ny = float(ix), float(iy)            # 上=+1，写 vy 时取负（y↓ 约定）
    while nx == 0.0 and ny == 0.0:
        nx = 0.0 if random.random() <= 0.33 else (1.0 if random.random() <= 0.5 else -1.0)
        ny = 0.0 if random.random() <= 0.33 else (1.0 if random.random() <= 0.5 else -1.0)
    c0, c1 = body.chunk0, body.chunk1
    c0.vx, c0.vy = 9.0 * nx, -9.0 * ny
    c1.vx, c1.vy = 8.0 * nx, -8.0 * ny


def apply_penalties(pet, body) -> None:
    """过热惩罚：达 OVERHEAT_AT 眩晕，达 CAPACITY 自爆。"""
    n = body._ctrl_pyro_counter
    if n >= OVERHEAT_AT:
        body.stun = max(body.stun, 60 * (n - (OVERHEAT_AT - 1)))
    if n >= CAPACITY:
        _pyro_death(pet, body)


def _pyro_death(pet, body) -> None:
    """过热自爆：触发爆炸 + 死亡终态。"""
    pyro_explosion(pet, body)
    beh = getattr(pet, "behavior", None)
    if beh is not None:
        beh.kill()
    else:
        body.die()


class PyroController:
    """挂在 body._ctrl_pyro 的工匠控制器；world/pets/fx 经 pet 转发取。"""

    def __init__(self, pet):
        self.pet = pet
        ensure(pet.body)

    def update(self, body, inp0, inp1, want_pre, can_pre) -> None:
        """每 ctrl tick：回落/过热警告 → 触发变体 → 复位爆跳标记。"""
        tick_fuel(self.pet, body)
        # 双路径触发：pckp+跳跃缓冲，或 K 边沿承担特殊键
        trigger = (want_pre > 0 and inp0.pckp) or (inp0.pckp and not inp1.pckp)
        low_grav = body.bodyMode == "ZeroG" or body.room_gravity <= 0.1   # 零/低重力豁免：压下也可空中爆跳
        if (trigger and not body._ctrl_pyro_jumped and can_pre <= 0
                and (inp0.y >= 0 or low_grav)
                and body.bodyMode != "Crawl" and not body.on_pole):
            self._air_jump(body, inp0)
        elif (trigger and (inp0.y < 0 or body.bodyMode == "Crawl")
                and (can_pre > 0 or inp0.y < 0)
                and not body._ctrl_pyro_jumped and body._ctrl_pyro_parry_cd <= 0.0):
            self._ground_parry(body, can_pre)
        # 复位：接地/杆/贴墙（chunk.cx±1 近似）或低重力松键
        if (body._ctrl_can_jump > 0 or body.on_pole
                or body.chunk0.cx != 0 or body.chunk1.cx != 0
                or ((body.bodyMode == "ZeroG" or body.room_gravity <= 0.5)
                    and (body._ctrl_want_jump == 0 or not inp0.pckp))):
            body._ctrl_pyro_jumped = False

    def _air_jump(self, body, inp0) -> None:
        """变体 A 空中火箭跳：置爆跳标记后委托 fire_air_jump。"""
        body._ctrl_pyro_jumped = True
        fire_air_jump(self.pet, body, inp0.x, inp0.y)

    def _ground_parry(self, body, can_pre) -> None:
        """变体 B 地面爆炸+parry：离地下按补速、计数、反弹飞石、击退+眩晕邻猫。"""
        c0 = body.chunk0
        if can_pre <= 0:                         # 离地下按
            body._ctrl_pyro_jumped = True
            c0.vy = -8.0
            body.chunk1.vy = -6.0
            body.jump_boost = 6.0
        if body._ctrl_pyro_counter <= WARN_AT:
            body._ctrl_pyro_counter += 2
        else:
            body._ctrl_pyro_counter += 1
        body._ctrl_pyro_parry_cd = PARRY_COOLDOWN
        body._ctrl_pyro_cooldown = JUMP_COOLDOWN
        px, py = c0.x, c0.y
        spawn_parry_fx(self.pet, px, py)
        # 反弹 PARRY_STONE_R 内飞行石头
        for st in getattr(self.pet, "stones", ()):
            if not getattr(st, "fling", False):
                continue
            if math.hypot(st.x - px, st.y - py) >= PARRY_STONE_R:
                continue
            st.fling = False
            st.thrown_by_saint = False
            dx, dy = _dirvec(px, py, st.x, st.y)
            st.vx, st.vy = dx * 20.0, dy * 20.0
            st.spin = lerp(-100.0, 100.0, random.random()) * lerp(0.05, 1.0, getattr(st, "room_gravity", 1.0))
        # 击退+眩晕 PARRY_CAT_R 内其他猫
        for other in self._other_cats():
            oc = other.body.chunk0
            if math.hypot(oc.x - px, oc.y - py) >= PARRY_CAT_R:
                continue
            self._stun_other(other, PARRY_STUN)
            dx, dy = _dirvec(px, py, oc.x, oc.y)
            oc.vx, oc.vy = dx * PARRY_KNOCK, dy * PARRY_KNOCK
        apply_penalties(self.pet, body)

    def _other_cats(self):
        """在场其他猫；缺属性的测试假对象返回空。"""
        for other in getattr(self.pet, "pets", ()):
            if other is self.pet or getattr(other, "body", None) is None:
                continue
            yield other

    def _stun_other(self, other, ticks) -> None:
        """砸晕先例：有 FSM 走 apply_stun（入 Stunned 态），否则直写 body.stun。"""
        beh = getattr(other, "behavior", None)
        if beh is not None:
            beh.apply_stun(int(ticks))
        else:
            other.body.stun = max(other.body.stun, int(ticks))
