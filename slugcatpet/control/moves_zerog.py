"""零重力手操移动（控制路径专用，y↓），只做输入→意图，积分仍由 _step_zerog 负责。"""
from __future__ import annotations

import math


def ctrl_zerog_update(body) -> None:
    """每零重力 ctrl tick：want 缓冲 → 意图划水/贴墙蹬 → 工匠钩子。"""
    inp = body._ctrl_input
    inp0, inp1 = inp[0], inp[1]
    # 跳跃预输入缓冲同主干；蹬墙窗口用 body.canJump（勿混 _ctrl_can_jump）
    if body._ctrl_want_jump > 0:
        body._ctrl_want_jump -= 1
    elif inp0.jmp and not inp1.jmp:
        body._ctrl_want_jump = 5
    if inp0.x > 0:
        body.facing = 1
    elif inp0.x < 0:
        body.facing = -1
    on_wall = body.canJump > 0
    ix, iy = float(inp0.x), float(-inp0.y)          # y 翻号
    if ix != 0.0 or iy != 0.0:
        d = math.hypot(ix, iy)
        ux, uy = ix / d, iy / d
        body.zerog_swim(ux, uy, on_wall)
        if on_wall and body._ctrl_want_jump > 0:    # 贴墙跳，消费 want
            body.request_zerog_kick(ux, uy)
            body._ctrl_want_jump = 0
    elif on_wall and body._ctrl_want_jump > 0:      # 无方向蹬墙，退化为纯背离法向
        body.request_zerog_kick()
        body._ctrl_want_jump = 0
    # 工匠爆跳钩子
    pyro = getattr(body, "_ctrl_pyro", None)
    if pyro is not None:
        pyro.update(body, inp0, inp1, body._ctrl_want_jump, body.canJump)
