"""CatPersonality：每种族的原创性格行为层，与 SlugStats 生理层并列。"""
from __future__ import annotations

from dataclasses import dataclass, field

# 食性枚举
DIET_OMNIVORE = "omnivore"
DIET_CARNIVORE = "carnivore"
DIET_VEGETARIAN = "vegetarian"
DIET_SPECIAL = "special"


@dataclass(frozen=True)
class CatPersonality:
    """一种族性格：连续轴 + diet 枚举 + toy_pref 乘子，中性=0.5/1.0。"""
    activity: float = 0.5
    stamina: float = 1.0           # EN_DRAIN÷stamina，低反而更快累
    cold_gain_fac: float = 1.0
    sociability: float = 0.5
    swim_zeal: float = 0.5         # ≤0.5 视为中性
    diet: str = DIET_OMNIVORE
    toy_pref: dict = field(default_factory=dict)   # 空=全 1


DEFAULT_PERSONALITY = CatPersonality()
