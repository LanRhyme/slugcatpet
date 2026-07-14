"""Saint 独占状态挂载：按 caps 把超度与舌头系状态注册进 BehaviorFSM，关闭的能力不注册。"""
from __future__ import annotations

from ...behavior import tuning
from .ascension import Ascension
from .climb import TongueClimber, CeilingHanger
from .cursorlick import CursorLicker, RELICK_COOLDOWN
from .dodgekill import KillDodger

T_GRAB_TO_ASCEND = 200      # 被拎住这么久且满足超度门 → 直接超度


def mount(fsm):
    """CatDef.fsm_mount 入口：按 caps 挂载对应状态与弹窗应对。"""
    caps = fsm.win.cat.caps
    if caps.tongue:
        _mount_climb(fsm)
        _mount_cursorlick(fsm)
        _mount_dodgekill(fsm)
    if caps.ascension:
        _mount_ascension(fsm)
    if caps.tongue or caps.ascension:

        def threat_response():
            # 满足超度门→超度并消弹窗；否则舌躲杀（游泳中不进）
            if caps.ascension and _ascend_ready(fsm):
                fsm._dismiss_kill_dialog()
                fsm._transition("Ascension")
            elif caps.tongue and not fsm.body.swimming:
                fsm._transition("DodgeKill")

        fsm.threat_response = threat_response


def _mount_climb(fsm):
    """爬墙链：RelocateToWall → TongueClimb → CeilingHang。"""

    def relocate_enter():
        fsm.body.set_posture(True)
        fsm._relocate_x = None

    def st_relocatetowall(cursor, disturbed):
        b = fsm.body
        side = getattr(fsm, "_wall_side", -1)
        target = b.walk_max if side > 0 else b.walk_min
        if fsm._relocate_x is None:
            fsm._relocate_x = target
            b.walk_to(target)
        if not b.is_moving() or abs(b.chunk1.x - target) < 6.0:
            b.stop_walk()
            fsm._transition("TongueClimb")

    def climb_enter():
        fsm.climb = TongueClimber(fsm.win, getattr(fsm, "_wall_side", -1))

    def st_tongueclimb(cursor, disturbed):
        if fsm.grab.active:
            fsm._break_tongue()
            fsm.climb = None
            fsm._transition("Dragged")
            return
        if fsm.climb is None:
            fsm._transition("CeilingHang")
            return
        b = fsm.body
        if b.swimming:            # 落水自救：划水朝正上方，合力出水
            b.swim_target = (b.chunk0.x, b.chunk0.y - 120.0)
        elif b.swim_target is not None:
            b.swim_target = None
        done = fsm.climb.update()
        if fsm.climb.giveup:
            fsm._break_tongue()
            fsm._transition("IdleStand")
        elif done:
            fsm._transition("CeilingHang")

    def hang_enter():
        fsm.climb = CeilingHanger(fsm.win, getattr(fsm, "_wall_side", -1), fsm.rng)

    def st_ceilinghang(cursor, disturbed):
        if fsm.grab.active:
            fsm._break_tongue()
            fsm.climb = None
            fsm._transition("Dragged")
            return
        done = fsm.climb.update() if fsm.climb else True
        # 涨水期间赖着不下来（下面是水）
        bored = fsm.mood.should_quit("ceiling_play") and fsm.water_threat() <= 0.5
        if bored or done:
            fsm._break_tongue()
            fsm.climb = None
            fsm._transition("Airborne")

    def brk():
        fsm._break_tongue()
        fsm.body.stop_walk()
        fsm.climb = None

    def kill_brk():
        fsm._break_tongue()
        fsm.climb = None

    fsm.register_state("RelocateToWall", enter=relocate_enter, tick=st_relocatetowall)
    fsm.register_state("TongueClimb", enter=climb_enter, tick=st_tongueclimb,
                       brk=brk, kill_break=kill_brk)
    fsm.register_state("CeilingHang", enter=hang_enter, tick=st_ceilinghang,
                       brk=brk, kill_break=kill_brk)


def _mount_cursorlick(fsm):
    """舔光标 CursorLick：CursorLicker 三阶段；hang 期靠上横杆则转 HPole。"""

    def enter():
        fsm.gfx.hand_aim["l"] = None
        fsm.gfx.hand_aim["r"] = None
        fsm._dwell = 0
        fsm.cursorlick = CursorLicker(fsm.win, fsm.rng)

    def st_cursorlick(cursor, disturbed):
        if fsm.grab.active:
            brk()
            fsm._transition("Dragged")
            return
        if fsm.cursorlick is None:
            fsm._transition("IdleStand")
            return
        fsm.gfx.look_at = cursor
        status = fsm.cursorlick.update(cursor, fsm._cursor_speed)
        if status == "to_idle":
            if fsm.cursorlick.outcome == "licked_once":
                fsm.body.temper_shift(tuning.TEMPER_LICK)
            brk()
            fsm._transition("IdleStand")
        elif status == "to_airborne":
            brk()
            fsm._transition("Airborne")
        elif (fsm.cursorlick.phase == "hang" and fsm.win.tongue.attached):
            pole = fsm._horizontal_pole_near(cursor)
            if pole is not None:
                fsm.cursorlick = None
                fsm._dwell = 0
                fsm._relick_cooldown = RELICK_COOLDOWN
                fsm._hpole_pole = pole
                fsm._transition("HPole")

    def brk():
        fsm._break_tongue()
        fsm.body.stop_walk()
        fsm.cursorlick = None
        fsm._dwell = 0
        fsm._relick_cooldown = RELICK_COOLDOWN

    fsm.register_state("CursorLick", enter=enter, tick=st_cursorlick,
                       brk=brk, kill_break=brk)


def _mount_dodgekill(fsm):
    """舌躲杀 DodgeKill：杀死弹窗存在期间 KillDodger 舌点「取消」。"""

    def enter():
        fsm.gfx.hand_aim["l"] = None
        fsm.gfx.hand_aim["r"] = None
        fsm.body.set_posture(True)
        fsm.body.stop_walk()
        fsm.dodge = KillDodger(fsm.win, fsm.rng)

    def st_dodgekill(cursor, disturbed):
        if getattr(fsm.win, "_kill_dialog", None) is None:
            brk()
            fsm._transition("IdleStand" if fsm.body.on_floor() else "Airborne")
            return
        if fsm.grab.active:
            brk()
            fsm._transition("Dragged")
            return
        if fsm.dodge is None:
            brk()
            fsm._transition("IdleStand")
            return
        done = fsm.dodge.update()
        if done:
            brk()
            fsm._transition("IdleStand" if fsm.body.on_floor() else "Airborne")

    def brk():
        if fsm.dodge is not None:
            fsm.dodge.release()
            fsm.dodge = None
        fsm._break_tongue()
        fsm.body.stop_walk()
        fsm.gfx.hand_aim["l"] = None
        fsm.gfx.hand_aim["r"] = None

    fsm.register_state("DodgeKill", enter=enter, tick=st_dodgekill,
                       brk=brk, kill_break=brk)


def _ascend_ready(fsm):
    """超度双门：业力满 + 好感疏远。"""
    return (fsm.body.karma >= fsm.body.karma_max
            and fsm.body.temper <= fsm.win.cat.tuning["temper_ascend_gate"])


def _mount_ascension(fsm):
    """超度 Ascension 状态与接管钩子。"""

    def enter():
        fsm.grab.force_release()
        fsm.body.suspended = False
        fsm.karma = Ascension(fsm.win)
        fsm.gfx.ascension = fsm.karma

    def st_ascension(cursor, disturbed):
        done = fsm.karma.update(cursor) if fsm.karma else True
        if done:
            fsm.karma = None
            fsm.gfx.ascension = None
            fsm._transition("Airborne")

    def kill_brk():
        if fsm.karma is not None:
            fsm.karma.abort()
            fsm.karma = None
        fsm.gfx.ascension = None
        fsm.body.suspended = False

    def drag_takeover(frames):
        if frames >= T_GRAB_TO_ASCEND and _ascend_ready(fsm):
            fsm._transition("Ascension")
            return True
        return False

    def stun_takeover():
        if _ascend_ready(fsm):
            fsm._transition("Ascension")
            return True
        return False

    fsm.register_state("Ascension", enter=enter, tick=st_ascension,
                       kill_break=kill_brk, fx=lambda: fsm.karma)
    fsm.drag_takeover = drag_takeover
    fsm.stun_takeover = stun_takeover
    fsm._interaction_blockers.add("Ascension")
