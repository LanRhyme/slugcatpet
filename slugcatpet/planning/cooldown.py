"""放弃目标冷却注册表：时长到期或世界结构版本变更即清除。"""
from __future__ import annotations
import time

from ..behavior import tuning

TICK_HZ = 40.0


class CooldownRegistry:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._entries = {}     # key -> (到期时刻, world_version)

    def add(self, key, world_version):
        expire = self._clock() + tuning.PLAN_COOLDOWN_TICKS / TICK_HZ
        self._entries[key] = (expire, world_version)

    def active(self, key, world_version):
        e = self._entries.get(key)
        if e is None:
            return False
        expire, wv = e
        if world_version != wv or self._clock() >= expire:
            del self._entries[key]
            return False
        return True
