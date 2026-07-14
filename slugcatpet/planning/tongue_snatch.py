"""机会主义舌头补救层：空中掠果时抢射舌粘住收绳，消费方每 tick 驱动。"""
from __future__ import annotations
import math

from ..behavior import tuning
from .tongue_reach import FETCH_IDEAL, FETCH_REEL, mouth_pos


class TongueSnatch:
    """一个补救实例：最多抢射 PLAN_SNATCH_MAX_TRIES 次；粘住即收绳，退出则收舌还权。"""

    def __init__(self, pet):
        self.pet = pet
        self._prev_dist = None      # 判是否已掠过最近点
        self._rescues = 0
        self._active = False
        self._timer = 0

    def update(self, goal):
        """推进一 tick：未持有则判触发门抢射；持有中则维持收绳 / 判退出。"""
        tg = self.pet.tongue
        if tg is None:
            return
        if self._active:
            self._maintain(tg, goal)
            return
        body = self.pet.body
        gx, gy = goal.pos()
        mox, moy = mouth_pos(self.pet)
        dist = math.hypot(gx - mox, gy - moy)
        prev = self._prev_dist
        self._prev_dist = dist
        if not self._should_fire(goal, body, tg, dist, prev):
            return
        # 先判空闲再占用，射失败即还权
        if not tg.is_idle():
            return
        if not tg.try_acquire(self):
            return
        if not tg.shoot(mox, moy, gx, gy, hit=True, obj=goal.obj, owner=self):
            tg.release(self)
            return
        tg.set_targets(ideal=FETCH_IDEAL, reel_rate=FETCH_REEL)
        self._active = True
        self._timer = 0
        self._rescues += 1

    def holding(self):
        """是否正持有补救舌头，需实查 owner 非仅看布尔。"""
        tg = self.pet.tongue
        return self._active and tg is not None and tg.owner is self

    def reset(self):
        """换新目标：配额刷新 + 清本地态。"""
        self._rescues = 0
        self._clear()

    def _should_fire(self, goal, body, tg, dist, prev):
        """触发门：grasp 目标 + 实体 + 有效 + 腾空 + 已掠过最近点 + 在射程内 + 未触顶抢射数。"""
        if goal.contact != "grasp" or goal.obj is None or not goal.valid():
            return False
        if body.on_floor():
            return False
        if self._rescues >= tuning.PLAN_SNATCH_MAX_TRIES:
            return False
        if prev is None or dist <= prev:        # 尚未掠过最近点（仍在靠近）
            return False
        if dist > tg.total:
            return False
        return True

    def _maintain(self, tg, goal):
        """持有中：确认仍持有→判退出→粘住则压收绳。"""
        self._timer += 1
        if tg.owner is not self:                # owner 变化即视为已丢失
            self._clear()
            return
        if not goal.valid() or self._timer > tuning.PLAN_SNATCH_TIMEOUT:
            self._handback(tg)
            return
        if tg.attached:
            tg.set_targets(ideal=FETCH_IDEAL, reel_rate=FETCH_REEL)

    def abort(self):
        """外部结束补救（抓到 / 换目标 / 中断）：收回仍持有的舌头并清本地态。"""
        tg = self.pet.tongue
        if tg is not None and tg.owner is self:
            self._handback(tg)
        else:
            self._clear()

    def _handback(self, tg):
        """收舌 + 释权 + 解悬，还权原控制器。"""
        if tg.owner is self:
            tg.retract()
            tg.release(self)
        self.pet.body.suspended = False
        self._clear()

    def _clear(self):
        self._active = False
        self._timer = 0
        self._prev_dist = None
