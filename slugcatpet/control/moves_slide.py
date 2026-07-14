"""滑→滚→翻→火箭 动作簇每帧物理 + 共享计数器（控制路径专用，y↓）。perpendicular 返回反号力矩，施力时交换 +=/-=。"""
from __future__ import annotations
import math

from . import vmath
from ..core.units import lerp

# 共享计数器/标志；控制专属，惰性 init
_SLIDE_DEFAULTS = {
    "_ctrl_roll_direction": 0,      # Roll/BellySlide 共享横向符号
    "_ctrl_roll_counter": 0,        # Roll/BellySlide 共享计时
    "_ctrl_whiplash": False,        # 滑铲反向，下次跳变 Flip
    "_ctrl_flip_from_slide": False, # Flip 源自滑铲，力矩 ×2.5
    "_ctrl_rocket_from_belly": False,  # RocketJump 源自滑铲，落地转 Roll
    "_ctrl_exit_belly": 0,          # 滑铲输入不合帧数
    "_ctrl_stop_rolling": 0,        # Roll 卡地帧数，>6 结束
    "_ctrl_super_launch": 0,        # 趴蹲蓄力计数，>=20 超级跳
    "_ctrl_sim_hold": 0,            # 超级跳后自动持跳帧数
    "_ctrl_slide_direction": 0,     # 站立急刹跑向，非 roll_direction
    "_ctrl_init_slide_counter": 0,  # 同向跑累积，门控急刹起始
    "_ctrl_slide_counter": 0,       # 站立急刹计时
    "_ctrl_allow_roll": 0,          # 翻滚许可窗口
    "_ctrl_consistent_dd": 0,       # 连续同向 downDiagonal 帧数
    "_ctrl_fall_speed": 0.0,        # 上一离地帧下坠速度
    "_ctrl_prev_floor": True,       # 上一 tick 是否接地
}

BELLY_PERIOD = 15.0     # 正弦周期
DEFAULT_DYN = 3.6       # Default bodyMode 跑速上限


def ensure(body) -> None:
    for k, v in _SLIDE_DEFAULTS.items():
        if not hasattr(body, k):
            setattr(body, k, v)


def clear_flags(body) -> None:
    """移动主干顶部：按当前 animation 清三 bool，防跨态泄漏。"""
    a = body.animation
    if body._ctrl_rocket_from_belly and a != "RocketJump":
        body._ctrl_rocket_from_belly = False
    if body._ctrl_flip_from_slide and a != "Flip":
        body._ctrl_flip_from_slide = False
    if body._ctrl_whiplash and a != "BellySlide":
        body._ctrl_whiplash = False


def movement_increments(body) -> None:
    """滚动计时递增，含安全网清零。"""
    if body._ctrl_roll_direction != 0:
        body._ctrl_roll_counter += 1
        if body.bodyMode != "Default" or body._ctrl_roll_counter > 200:
            body._ctrl_roll_counter = 0
            body._ctrl_roll_direction = 0


def super_launch_charge(body, move_x, inp0, inp1) -> None:
    """趴姿蓄力扑跳。"""
    c0, c1 = body.chunk0, body.chunk1
    decay_flag = 1 if body._ctrl_super_launch > 0 else 0   # 蓄力衰减标志
    if body.bodyMode == "Crawl" and c0.on_floor and c1.on_floor:
        if move_x == 0 and inp0.y == 0:            # 趴着无方向输入 → 蓄力位
            decay_flag = 0                         # 蓄力位不衰减
            body._ctrl_want_jump = 0               # 压住即时跳
            if inp0.jmp and body._ctrl_super_launch < 20:   # 按住跳 → 逐帧蓄力封顶 20
                body._ctrl_super_launch += 1
        if not inp0.jmp and inp1.jmp:              # 松开跳键那帧
            body._ctrl_want_jump = 1               # 发跳
    # 衰减推迟到 dispatch 后应用，防扑跳失败
    body._ctrl_sl_decay = decay_flag


def skid_update(body, move_x) -> None:
    """站立急刹掉头，Stand 态每帧调。"""
    c0, c1 = body.chunk0, body.chunk1
    sd = body._ctrl_slide_direction
    if body._ctrl_slide_counter > 0:
        body._ctrl_slide_counter += 1
        if body._ctrl_slide_counter > 20 or move_x != -sd:
            body._ctrl_slide_counter = 0
        n = -math.sin(body._ctrl_slide_counter / 20.0 * math.pi * 0.5) + 0.5   # 甩尾反冲曲线
        c0.vx += n * 3.5 * sd - sd * (0.8 if n < 0 else 0.5)
        c1.vx += n * 3.5 * sd + sd * 0.5
    elif move_x != 0:
        if move_x == sd:
            if body._ctrl_init_slide_counter < 30:
                body._ctrl_init_slide_counter += 1
        else:
            # 反向+连跑够久+高速同向 → 起急刹
            if (body._ctrl_init_slide_counter > body.stats.skid_init_thresh
                    and (c0.vx > 0) == (sd > 0) and abs(c0.vx) > 1.0):
                body._ctrl_slide_counter = 1
            else:
                body._ctrl_slide_direction = move_x
            body._ctrl_init_slide_counter = 0
    elif body._ctrl_init_slide_counter > 0:
        body._ctrl_init_slide_counter -= 1


def update_allow_roll(body) -> None:
    """翻滚许可窗口，离地且臀下有空隙时置 15。"""
    if body._ctrl_allow_roll > 0:
        body._ctrl_allow_roll -= 1
    floor = getattr(body, "_floor_h", body.H)
    if (not body.on_floor()) and (floor - body.chunk1.y) > 20.0:
        body._ctrl_allow_roll = 15


def update_consistent_dd(body, inp0, inp1) -> None:
    """连续同向 downDiagonal 帧数累积（门控落地→Roll）。"""
    if inp0.downDiagonal != 0 and inp0.downDiagonal == inp1.downDiagonal:
        body._ctrl_consistent_dd += 1
    else:
        body._ctrl_consistent_dd = 0


def try_land_roll(body, inp0) -> None:
    """落地→Roll 入口，落地边沿处调。"""
    if inp0.downDiagonal == 0 or body.animation == "Roll":
        return
    speed = body._ctrl_fall_speed
    from_flip = body.animation == "Flip"
    from_rocket_belly = body.animation == "RocketJump" and body._ctrl_rocket_from_belly
    if not (speed > 12.0 or from_flip or from_rocket_belly):
        return
    if body._ctrl_allow_roll <= 0:
        return
    if body._ctrl_consistent_dd <= (1 if speed > 24.0 else 6):
        return
    c0, c1 = body.chunk0, body.chunk1
    if from_rocket_belly:                        # chunk 微调，y 翻
        c1.vy -= 3.0
        c1.y -= 3.0
        c0.vy += 3.0
        c0.y += 3.0
    body.animation = "Roll"
    body._ctrl_roll_direction = inp0.downDiagonal
    body._ctrl_roll_counter = 0
    c0.vx = lerp(c0.vx, 9.0 * inp0.x, 0.7)
    c1.vx = lerp(c1.vx, 9.0 * inp0.x, 0.7)
    body.standing = False


def anim_forces(body, move_x, inp0, inp1) -> None:
    """滑簇动画分支每帧力（互斥）。"""
    a = body.animation
    if a == "BellySlide":
        _belly_slide(body, inp0, inp1)
    elif a == "Roll":
        _roll(body, inp0)
    elif a == "RocketJump":
        _rocket_jump(body)
    elif a == "Flip":
        _flip(body)


def _belly_slide(body, inp0, inp1) -> None:
    """滑铲每帧力（平地简化：略穿平台下坠/斜面）。"""
    c0, c1 = body.chunk0, body.chunk1
    body.bodyMode = "Default"
    rd = body._ctrl_roll_direction
    rc = body._ctrl_roll_counter
    if rc < 6 and not body.stats.belly_no_kick:  # 起始后蹬；溪流无后蹬
        c1.vy -= 2.7
        c1.vx -= 9.1 * rd
    else:                                        # 贴地 +0.5
        c1.vy += 0.5
    c0.vx += body.stats.belly_slide_spd * rd * _sin(rc / BELLY_PERIOD)  # 正弦主推进，峰值按种族
    c0.vy += 2.3                                 # 头下压
    for c in (c0, c1):                           # 悬空摩擦
        if c.cy == 0:
            c.vx *= 0.5
    # 退出计数累积
    if inp0.x != rd and inp0.downDiagonal != rd:
        body._ctrl_exit_belly += 1
    else:
        body._ctrl_exit_belly = 0
    if rc > 5 and inp0.x == -rd:                  # 甩尾反跳标志
        body._ctrl_whiplash = True
    jmp_edge = inp0.jmp and not inp1.jmp          # 退出判据
    if ((rc > 8 and body._ctrl_exit_belly > 6)
            or rc > 15
            or (jmp_edge and 0 < rc < body.stats.belly_jump_cancel_window)):
        c0.vy = 0.0
        c1.vy = 0.0
        body._ctrl_roll_direction = 0
        body.animation = None
        body.standing = (inp0.y == 1)            # pet 无天花板，恒真
        for c in (c0, c1):                        # |vel.x|>8 减速
            if abs(c.vx) > 8.0:
                c.vx *= 0.5
                c.vy *= 0.5
    else:
        body.standing = False


def _roll(body, inp0) -> None:
    """翻滚每帧力（平地简化）。"""
    c0, c1 = body.chunk0, body.chunk1
    body.bodyMode = "Default"
    rd = body._ctrl_roll_direction
    # perp 反号，c0 用 -=、c1 用 +=
    perp_x, perp_y = vmath.perpendicular(c1.x, c1.y, c0.x, c0.y)
    c0.vx *= 0.9
    c0.vy *= 0.9
    c1.vx *= 0.9
    c1.vy *= 0.9
    torque_x = perp_x * 2.0 * rd
    torque_y = perp_y * 2.0 * rd
    c0.vx -= torque_x
    c0.vy -= torque_y
    c1.vx += torque_x
    c1.vy += torque_y
    stuck = (c0.cx == rd or c1.cx == rd)          # 滚向撞墙
    if c0.on_floor or c1.on_floor:                 # 接地滚动，前驱 + 郊狼窗口
        c0.vx += 1.1 * rd
        c1.vx += 1.1 * rd
        body._ctrl_can_jump = max(getattr(body, "_ctrl_can_jump", 0), 5)
    else:                                          # 悬空滚，计卡滚
        stuck = True
    body._ctrl_stop_rolling = (body._ctrl_stop_rolling + 1) if stuck else 0
    # 退出判据
    rc = body._ctrl_roll_counter
    head_above = c0.y < c1.y
    if ((((rc > 15 and inp0.y > -1 and inp0.downDiagonal == 0) or rc > 30 or inp0.x == -rd) and head_above)
            or rc > 60
            or body._ctrl_stop_rolling > 6):
        body._ctrl_roll_direction = 0
        body.animation = None
        body.standing = inp0.y > -1


def _rocket_jump(body) -> None:
    """火箭跳每帧力：臀减速、沿速度拉伸成流线、微升，臀触物即结束。"""
    c0, c1 = body.chunk0, body.chunk1
    body.bodyMode = "Default"
    body.standing = False
    c1.vx *= 0.99
    c1.vy *= 0.99
    nx, ny = vmath.normalize(c0.vx, c0.vy)         # 速度已是 pet 空间，直接归一
    c0.vx += nx
    c0.vy += ny
    c1.vx -= nx
    c1.vy -= ny
    c0.vy -= 0.1
    c1.vy -= 0.1
    if c1.cx != 0 or c1.cy != 0:                    # 臀有任意接触 → 结束
        body.animation = None


def _flip(body) -> None:
    """翻跳每帧力：力矩键 _ctrl_slide_direction（非 _ctrl_roll_direction），触物退出。"""
    c0, c1 = body.chunk0, body.chunk1
    body.bodyMode = "Default"
    sd = getattr(body, "_ctrl_slide_direction", 0)   # 滑铲来的 Flip 用残留值
    mult = 0.38 * (2.5 if body._ctrl_flip_from_slide else 1.0)   # 基 0.38，无肾上腺素加成
    torque_x, torque_y = vmath.perpendicular(c1.x, c1.y, c0.x, c0.y)
    k = sd * mult
    torque_x *= k
    torque_y *= k
    # perp 反号，c0 用 +=、c1 用 -=
    c0.vx += torque_x
    c0.vy += torque_y
    c1.vx -= torque_x
    c1.vy -= torque_y
    body.standing = False
    for c in (c0, c1):                              # 触物结束，standing 依头臀高低
        if c.cx != 0 or c.cy != 0:
            body.animation = None
            body.standing = c0.y < c1.y
            break


def _sin(x):
    return math.sin(x * math.pi)
