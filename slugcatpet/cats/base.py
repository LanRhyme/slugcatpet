"""CatDef：每猫种族的静态定义数据类（外观 / 资源 / 能力开关 / 调参槽位）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .personality import CatPersonality, DEFAULT_PERSONALITY
from .stats import SlugStats, DEFAULT_STATS


@dataclass(frozen=True)
class CatCaps:
    """能力开关：关 = 不建对应器官、不注册对应状态。"""
    tongue: bool = True
    ascension: bool = True
    gills: bool = False           # 仅 Rivulet
    pyro: bool = False            # 需配 tuning.pyro_heat_cap
    acrobat: bool = False         # 仅 Rivulet
    # 跳跃/竖杆够取全员通用，不设 cap


# 能力开启时 tuning 必须携带的配套键
CAP_REQUIRED_TUNING = {
    "ascension": ("temper_ascend_gate", "temper_kill_cancel_saint"),
    "pyro": ("pyro_heat_cap",),
}


@dataclass(frozen=True)
class CatDef:
    """一只猫种族的定义：注册键、体/眼色、帧族、layout 文件、图集需求、能力、调参。"""
    key: str                                   # i18n variant_* 键
    body_color: tuple[int, int, int]
    eye_color: tuple[int, int, int]            # 兼脸暗色
    frames: dict[str, tuple[str, str]]         # 语义名→(图集 key, 帧名)
    layout_file: str                           # resources/layouts/ 下文件名
    atlas_keys: tuple[str, ...]                # AtlasSet key
    caps: CatCaps = field(default_factory=CatCaps)
    stats: SlugStats = DEFAULT_STATS
    personality: CatPersonality = DEFAULT_PERSONALITY
    tuning: dict = field(default_factory=dict)
    fsm_mount: Callable | None = None              # FSM 构造时调用，注册独占状态
    wip: bool = True                               # 未完成占位，做完显式设 False

    def __post_init__(self):
        # caps 开启却缺配套 tuning 键 → 建 def 即报错
        for cap, keys in CAP_REQUIRED_TUNING.items():
            if getattr(self.caps, cap):
                missing = [k for k in keys if k not in self.tuning]
                if missing:
                    raise ValueError(
                        f"CatDef {self.key!r}: caps.{cap} 开启但 tuning 缺少配套键: "
                        + ", ".join(missing))
