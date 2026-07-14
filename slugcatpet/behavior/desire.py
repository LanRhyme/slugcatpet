"""欲望加权选择：freshness 滞回控冷却，合格候选中加权随机抽取。"""
from __future__ import annotations

from ..behavior import tuning


def _lerp(x, lo, hi, flo, fhi):
    if hi == lo:
        return flo
    t = max(0.0, min(1.0, (x - lo) / (hi - lo)))
    return flo + (fhi - flo) * t


class MoodContext:
    __slots__ = ("energy", "temper", "has_climbable_pole", "cold", "has_warm_lamp",
                 "has_hpole", "can_ceiling_play", "submerged")

    def __init__(self, energy, temper, has_climbable_pole, cold=0.0, has_warm_lamp=False,
                 has_hpole=False, can_ceiling_play=True, submerged=False):
        self.energy = energy
        self.temper = temper
        self.has_climbable_pole = has_climbable_pole
        self.cold = cold
        self.has_warm_lamp = has_warm_lamp
        self.has_hpole = has_hpole
        self.can_ceiling_play = can_ceiling_play
        self.submerged = submerged


def _one(_):
    return 1.0


class Candidate:
    __slots__ = ("name", "base", "start", "quit", "decay", "recover",
                 "gate", "energy_factor", "temper_factor", "cold_factor",
                 "one_shot", "freshness")

    def __init__(self, name, base, start, quit, decay, recover,
                 gate, energy_factor, temper_factor, one_shot, init=1.0,
                 cold_factor=None):
        self.name = name
        self.base = base
        self.start = start
        self.quit = quit
        self.decay = decay
        self.recover = recover
        self.gate = gate
        self.energy_factor = energy_factor
        self.temper_factor = temper_factor
        self.cold_factor = cold_factor if cold_factor is not None else _one
        self.one_shot = one_shot          # True=自身结束，False=freshness 降至 quit 退出
        self.freshness = init

    def weight(self, ctx, noise):
        return max(0.0, self.base * self.energy_factor(ctx.energy)
                   * self.temper_factor(ctx.temper)
                   * self.cold_factor(ctx.cold) + noise)


class MoodArbiter:
    def __init__(self, rng, noise_amp):
        self.rng = rng
        self.noise_amp = noise_amp
        self.candidates = {}
        self.order = []

    def add(self, cand):
        self.candidates[cand.name] = cand
        self.order.append(cand)

    def tick_freshness(self, active_name):
        """做时降 active、不做时回升其余（每 tick 一次）。"""
        for c in self.order:
            if c.name == active_name:
                c.freshness = max(0.0, c.freshness - c.decay)
            else:
                c.freshness = min(1.0, c.freshness + c.recover)

    def should_quit(self, active_name):
        """one_shot 候选恒 False；否则检查 freshness ≤ quit。"""
        c = self.candidates.get(active_name)
        if c is None or c.one_shot:
            return False
        return c.freshness <= c.quit

    def eligible(self, ctx):
        return [c for c in self.order if c.gate(ctx) and c.freshness >= c.start]

    def select(self, ctx):
        """在合格候选中加权随机抽一个；无合格候选返回 None。"""
        elig = self.eligible(ctx)
        if not elig:
            return None
        weights = [c.weight(ctx, self.rng.uniform(0.0, self.noise_amp)) for c in elig]
        total = sum(weights)
        if total <= 0.0:
            return None
        r = self.rng.random() * total
        acc = 0.0
        for c, w in zip(elig, weights):
            acc += w
            if r <= acc:
                return c.name
        return elig[-1].name

    def is_fresh(self, name):
        """该候选 freshness 是否已回升过 start 线。"""
        c = self.candidates.get(name)
        return c is not None and c.freshness >= c.start


def play_mult(personality, name):
    """好动度×玩具偏好 → 玩耍候选权重乘子；personality=None 取中性。"""
    act = 0.5 if personality is None else personality.activity
    toy = {} if personality is None else personality.toy_pref
    return max(0.0, 1.0 + tuning.PERS_ACT_SPREAD * (act - 0.5)) * toy.get(name, 1.0)


def play_gate(personality):
    """好动度 → 玩耍体力门（好动下调、不破底）。"""
    act = 0.5 if personality is None else personality.activity
    return max(tuning.PERS_GATE_FLOOR,
               tuning.PLAY_ENERGY_GATE - tuning.PERS_GATE_SPREAD * (act - 0.5))


def build_arbiter(rng, personality=None):
    # 乘子/体力门走模块级公式，供 CatDef 挂载复用
    def _pm(name):
        return play_mult(personality, name)

    _gate = play_gate(personality)

    arb = MoodArbiter(rng, tuning.MOOD_NOISE_AMP)
    arb.add(Candidate(
        "pole_climb", base=tuning.POLE_BASE * _pm("pole_climb"),
        start=tuning.POLE_START, quit=tuning.POLE_QUIT,
        decay=tuning.POLE_DECAY, recover=tuning.POLE_RECOVER,
        gate=lambda ctx: ctx.has_climbable_pole and ctx.energy >= _gate and not ctx.submerged,
        energy_factor=lambda e: _lerp(e, 0.0, 1.0, tuning.POLE_SF_TIRED, tuning.POLE_SF_FRESH),
        temper_factor=lambda t: 1.0,
        one_shot=True, init=tuning.POLE_INIT))
    arb.add(Candidate(
        "hpole", base=tuning.HPOLE_BASE * _pm("hpole"),
        start=tuning.HPOLE_START, quit=tuning.HPOLE_QUIT,
        decay=tuning.HPOLE_DECAY, recover=tuning.HPOLE_RECOVER,
        gate=lambda ctx: ctx.has_hpole and ctx.energy >= _gate and not ctx.submerged,
        energy_factor=lambda e: _lerp(e, 0.0, 1.0, tuning.HPOLE_SF_TIRED, tuning.HPOLE_SF_FRESH),
        temper_factor=lambda t: 1.0,
        one_shot=True, init=tuning.HPOLE_INIT))
    arb.add(Candidate(
        "ceiling_play", base=tuning.CEIL_BASE * _pm("ceiling_play"),
        start=tuning.CEIL_START, quit=tuning.CEIL_QUIT,
        decay=tuning.CEIL_DECAY, recover=tuning.CEIL_RECOVER,
        gate=lambda ctx: ctx.can_ceiling_play and ctx.energy >= _gate and not ctx.submerged,
        energy_factor=lambda e: _lerp(e, 0.0, 1.0, tuning.CEIL_SF_TIRED, tuning.CEIL_SF_FRESH),
        temper_factor=lambda t: 1.0,
        one_shot=False, init=tuning.CEIL_INIT))
    # idle 兜底候选
    arb.add(Candidate(
        "idle", base=tuning.IDLE_BASE, start=0.0, quit=0.0,
        decay=0.0, recover=1.0,
        gate=lambda ctx: True,
        energy_factor=lambda e: _lerp(e, tuning.IDLE_SF_KNEE, 1.0,
                                      tuning.IDLE_SF_TIRED, tuning.IDLE_SF_FRESH),
        temper_factor=lambda t: 1.0,
        one_shot=True, init=1.0))
    # 趋暖候选：权重随 cold 升
    arb.add(Candidate(
        "seek_warmth", base=tuning.COLD_SEEK_BASE, start=0.1, quit=0.0,
        decay=0.0, recover=1.0,
        gate=lambda ctx: ctx.has_warm_lamp and ctx.cold > 0.05,
        energy_factor=lambda e: 1.0,
        temper_factor=lambda t: 1.0,
        cold_factor=lambda c: c,
        one_shot=True))
    return arb
