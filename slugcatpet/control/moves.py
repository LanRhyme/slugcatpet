"""控制态 _movement_update，站立/跑动/跳物理入口。"""
from __future__ import annotations

from ..core import creature as cr
from . import moves_posture as mp
from . import moves_slide as ms
from . import moves_jump as mj


def ctrl_movement_update(body):
    """控制态移动主干；gate 由 creature 侧负责。"""
    c0, c1 = body.chunk0, body.chunk1
    inp = body._ctrl_input
    inp0, inp1 = inp[0], inp[1]

    # 郊狼窗口 + 跳跃预输入双缓冲，勿混 body.canJump
    if getattr(body, "_ctrl_want_jump", None) is None:
        body._ctrl_want_jump = 0
        body._ctrl_can_jump = 0
    if body._ctrl_want_jump > 0:
        body._ctrl_want_jump -= 1
    elif inp0.jmp and not inp1.jmp:
        body._ctrl_want_jump = 5
    if body._ctrl_can_jump > 0:
        body._ctrl_can_jump -= 1

    # 滑簇计数器/标志清理
    ms.ensure(body)
    ms.clear_flags(body)
    if body._ctrl_sim_hold > 0:
        body._ctrl_sim_hold -= 1

    # 翻滚许可维护 + 落地边沿检测
    ms.update_allow_roll(body)
    ms.update_consistent_dd(body, inp0, inp1)
    now_floor = body.on_floor()
    if not now_floor:
        body._ctrl_fall_speed = abs(c1.vy)  # 下坠速度，供落地 impact 近似
        body.crawl_anchor = None            # 离地清趴锚，防落地被旧锚拖回
    if now_floor and not body._ctrl_prev_floor:
        ms.try_land_roll(body, inp0)        # 落地边沿，满足条件进 Roll
    body._ctrl_prev_floor = now_floor

    move_x = inp0.x
    # 强蓄力锁横向：蓄力过半按跳键不能移
    if (getattr(body, "_ctrl_super_launch", 0) > 10
            and inp0.jmp and inp1.jmp and inp[2].jmp and inp0.y < 1):
        move_x = 0
    if move_x > 0:
        body.facing = 1
    elif move_x < 0:
        body.facing = -1
    body.move_dir = move_x           # 同步给 _gait_update，防脸/腿判定误判静止

    mp.toggle_standing(body, inp0, inp1)

    target_sink = 1.0 if not body.standing else 0.0
    body.hip_sink += (target_sink - body.hip_sink) * cr.HIP_SINK_EASE
    body._floor_h = body.H + body.hip_sink * body.crawl_sink

    if body.standing or move_x != 0:
        body.crawl_anchor = None
        body.crawl_pose = max(0.0, body.crawl_pose - 0.08)

    flag = (move_x == 0 and body.standing and c1.on_floor)
    if body.feet_stuck is not None and not flag:
        body.feet_stuck = None
    elif body.feet_stuck is None and flag:
        body.feet_stuck = [c1.x, body._floor_h - c1.rad]
    if body.feet_stuck is not None:
        body.feet_stuck[0] += (c1.x - body.feet_stuck[0]) * cr.FEET_EASE
        body.feet_stuck[1] = body._floor_h - c1.rad
        if not c1.pinned:
            c1.x = body.feet_stuck[0]
            c1.y = body.feet_stuck[1]

    mp.update_counters(body)                # 接地帧计数
    on_ground = body.on_floor()

    # bodyMode 按位置判（非 standing），过渡期平滑跟随
    if not on_ground:
        body.bodyMode = "Default"
    elif (c0.y < c1.y - 3.0) and body.animation != "CrawlTurn" and not c0.on_floor:
        body.bodyMode = "Stand"
    else:
        body.bodyMode = "Crawl"

    mp.anim_forces(body, move_x)               # 姿态过渡每帧力（可覆写 bodyMode/清 animation）
    ms.anim_forces(body, move_x, inp0, inp1)   # 滑/滚/翻/火箭每帧力（覆写 bodyMode=Default）
    mp.crawl_turn_delay(body)
    mp.posture_entry(body, move_x)             # 各态过渡入口（下一 tick 起施力）
    ms.movement_increments(body)            # 滚动计时++/安全网

    if body._ctrl_roll_direction != 0:      # 滚/滑期间横向意图=滚向
        move_x = body._ctrl_roll_direction

    if on_ground:
        body._ctrl_can_jump = 5             # 接地授权 5-tick 郊狼窗口

    dyn0 = cr.RUN_UPPER * body.stats.runspeed_fac
    dyn1 = cr.RUN_LOWER * body.stats.runspeed_fac
    if body.bodyMode == "Stand":
        c0.vy += cr.STAND_HEAD
        c1.vy += cr.STAND_FEET
        ms.skid_update(body, move_x)  # 急刹掉头
    elif body.bodyMode == "Default" and body.standing:
        c0.vy += cr.DEF_STAND_HEAD    # 抗重力，腾空立直身体
        c1.vy += cr.DEF_STAND_FEET
    elif body.bodyMode == "Crawl":
        dyn0 = dyn1 = cr.CRAWL_SPEED
        if inp0.y != 0:
            dyn0 = dyn1 = cr.CRAWL_SLOW     # 抬/低头减速
        if (move_x > 0) == (c0.x < c1.x):   # 掉头减速
            dyn0 *= 0.75
            dyn1 *= 0.75
        if (move_x == 0 and c1.on_floor and not c0.pinned and not c1.pinned
                and body._jump_pending is None):
            body._crawl_pose()      # 勿投影头到 conn 距圆，会破坏蓄力接地判定

    if body._ctrl_roll_direction != 0:      # 滚/滑期跑速取默认上限
        dyn0 = dyn1 = ms.DEFAULT_DYN
    ms.super_launch_charge(body, move_x, inp0, inp1)  # 趴蹲蓄力

    if body.walk_speed_target is not None:
        dyn0 = min(dyn0, body.walk_speed_target)
        dyn1 = min(dyn1, body.walk_speed_target)
    grounded = c0.on_floor or c1.on_floor
    for c, dyn in ((c0, dyn0), (c1, dyn1)):
        if c.pinned:
            continue
        if move_x < 0:
            step = cr.H_ACCEL
            if c.vx - step < -dyn:
                step = dyn + c.vx
            if step > 0:
                c.vx -= step
        elif move_x > 0:
            step = cr.H_ACCEL
            if c.vx + step > dyn:
                step = dyn - c.vx
            if step > 0:
                c.vx += step
        if grounded:
            target = max(-dyn, min(dyn, c.vx)) if move_x != 0 else 0.0
            c.vx += (target - c.vx) * cr.SKID_DAMP

    # 跳跃转移链分派：Roll/BellySlide/DownOnFours/标准/蹲跳
    want_pre = body._ctrl_want_jump   # 快照，供工匠钩子读消费前值
    can_pre = body._ctrl_can_jump
    mj.dispatch(body, inp0)

    # 蓄力衰减在 dispatch 之后应用，防扑跳见不到满蓄
    if getattr(body, "_ctrl_sl_decay", 0) > 0 and body._ctrl_super_launch > 0:
        body._ctrl_super_launch -= 1

    # 持跳可变跳高：离地且按住才施，松键即停
    if on_ground:
        pass
    elif body.jump_boost > 0 and (inp0.jmp or body._ctrl_sim_hold > 0
                                  or (getattr(body, "_ctrl_pyro", None) is not None
                                      and inp0.pckp and body._ctrl_pyro_jumped)):
        body.jump_boost -= cr.JUMPBOOST_DECAY
        kick = (body.jump_boost + 1) * cr.JUMPBOOST_GAIN
        c0.vy -= kick
        c1.vy -= kick
        if body.jump_boost < 0:
            body.jump_boost = 0.0
    else:
        body.jump_boost = 0.0

    if body.walk_min is not None and move_x != 0:
        for c in (c0, c1):
            if c.x < body.walk_min:
                c.x = body.walk_min
            elif c.x > body.walk_max:
                c.x = body.walk_max

    # 工匠专属钩子，非工匠恒 None
    pyro = getattr(body, "_ctrl_pyro", None)
    if pyro is not None:
        pyro.update(body, inp0, inp1, want_pre, can_pre)
