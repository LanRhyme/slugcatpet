"""运行时状态字符串常量。"""
from __future__ import annotations


class ItemState:
    FREE = "free"
    HANGING = "hanging"
    CARRIED = "carried"
    MOUSE = "mouse"
    EATEN = "eaten"
    GONE = "gone"


class TongueMode:
    IDLE = "idle"
    SHOOTING = "shooting"
    ATTACHED = "attached"
    RETRACTING = "retracting"

