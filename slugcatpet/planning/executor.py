"""计划执行器：驱动候选控制器；续跑优先（同方案仍最优则不打断），进展判失败，2+2 放弃进冷却。"""
from __future__ import annotations

from ..behavior import tuning
from .ability import DONE, GIVEUP, HOLD, HOLDING, MODE_STAY, MODE_TOUCH, RUNNING


class PlanExecutor:
    """update() -> "running"|"holding"|"giveup"；mode 决定问 touch 还是 stay 候选。接触/抓取由消费方每 tick 自查并终止。"""

    def __init__(self, pet, planner, goal, mode=MODE_TOUCH):
        self.pet = pet
        self.planner = planner
        self.goal = goal
        self.mode = mode
        self._fails = {}           # ability_key -> 失败次数
        self._exhausted = set()    # 已 2 败踢出的方案
        self._schemes_burned = 0
        self._active = None
        self._controller = None
        self._step_ticks = 0
        self._step_budget = 0.0
        self._start_best = 0.0     # step 开始时的最优剩余耗时
        self._replans = 0          # 世界性重规划累计
        self._snap_wv = None
        self._snap_zerog = None
        self._given_up = False
        self._holding = False      # 上一 tick 报 HOLD，本 tick 免破裂检查

    def update(self):
        if self._given_up:
            return GIVEUP
        if not self.goal.valid():
            # 目标消亡：终止但不入冷却
            self._abort_controller()
            self._given_up = True
            return GIVEUP
        # 路径几何变化才重规划，驻留中免检
        if (self._controller is not None and not self._holding
                and self._structural_changed()):
            self._replans += 1
            if self._replans > tuning.PLAN_REPLAN_BUDGET:
                return self._give_up()
            self._abort_controller()
        if self._controller is None and not self._plan():
            return self._give_up()

        status = self._controller.update()
        self._step_ticks += 1
        # stay 语境：DONE 与 HOLD 同等对待为已到位
        if status == DONE and self.mode == MODE_STAY:
            status = HOLD
        self._holding = (status == HOLD)
        if status == HOLD:
            # 驻留中快照保鲜，防世界变更误判破裂
            self._step_ticks = 0
            self._resnapshot()
            return HOLDING
        if status == RUNNING:
            if self._step_ticks < self._step_budget:
                return RUNNING
            # 单步预算到：仍最优则续跑，否则换方案
            if self._best_key() == self._active.ability_key:
                self._step_ticks = 0
                return RUNNING
            self._abort_controller()
            if not self._count_fail():
                return GIVEUP
            if not self._plan():
                return self._give_up()
            return RUNNING

        # 结束后按剩余耗时降幅判进展
        self._abort_controller()
        remaining = self._filtered()
        new_best = remaining[0].time_est if remaining else None
        progressed = (new_best is not None
                      and self._start_best - new_best >= tuning.PLAN_PROGRESS_MIN)
        if not progressed and not self._count_fail():
            return GIVEUP
        if not self._plan():
            return self._give_up()
        return RUNNING

    def cancel(self):
        """消费方终止：清理在跑控制器，不入冷却。"""
        self._abort_controller()
        self._given_up = True

    # 内部
    def _structural_changed(self):
        if self._geometry_version() != self._snap_wv:
            return True
        return getattr(self.pet.body, "zerog", False) != self._snap_zerog

    def _resnapshot(self):
        self._snap_wv = self._geometry_version()
        self._snap_zerog = getattr(self.pet.body, "zerog", False)

    def _best_key(self):
        cands = self._filtered()
        return cands[0].ability_key if cands else None

    def _geometry_version(self):
        return getattr(self.pet, "geometry_version", 0)

    def _candidates(self):
        if self.mode == MODE_STAY:
            return self.planner.stay_candidates(self.goal)
        return self.planner.touch_candidates(self.goal)

    def _filtered(self):
        return [c for c in self._candidates()
                if c.ability_key not in self._exhausted]

    def _plan(self):
        cands = self._filtered()
        if not cands:
            return False
        self._active = cands[0]
        self._controller = self._active.make_controller()
        self._step_ticks = 0
        self._step_budget = max(tuning.PLAN_STEP_TIMEOUT_MIN,
                                self._active.time_est * tuning.PLAN_STEP_TIMEOUT_K)
        self._start_best = self._active.time_est
        self._resnapshot()
        return True

    def _count_fail(self):
        """记 1 败；2 败踢方案换次优，2+2 触顶放弃（回 False）。"""
        key = self._active.ability_key
        n = self._fails.get(key, 0) + 1
        self._fails[key] = n
        if n >= tuning.PLAN_FAILS_PER_SCHEME:
            self._exhausted.add(key)
            self._schemes_burned += 1
            if self._schemes_burned >= tuning.PLAN_SCHEMES_MAX:
                self._give_up()
                return False
        return True

    def _abort_controller(self):
        c = self._controller
        self._controller = None
        self._holding = False
        if c is not None and hasattr(c, "cancel"):
            c.cancel()

    def _give_up(self):
        self._abort_controller()
        self._given_up = True
        self.planner.on_giveup(self.goal)
        return GIVEUP
