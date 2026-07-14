"""按 CatDef.layout_file 加载部件基准摆位，物理/动画在此之上偏移。"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from .._paths import resource_dir
from ..cats import default_def

LAYOUTS_DIR = resource_dir() / "layouts"
DEFAULT_PATH = LAYOUTS_DIR / default_def().layout_file


@dataclass
class Part:
    frame: str
    atlas: str
    x: float = 0.0       # 逻辑画布坐标（左上原点，y 向下）
    y: float = 0.0
    z: int = 0
    mirror: bool = False
    visible: bool = True
    scale: float = 1.0
    tint: list | None = None
    anchor: list | None = None
    angle: float = 0.0


@dataclass
class Layout:
    tint: list = field(default_factory=lambda: list(default_def().body_color))  # 无 json 时的回退体色
    canvas_scale: int = 2                                        # 整数倍放大，保像素清晰
    canvas_w: int = 56
    canvas_h: int = 70
    parts: list = field(default_factory=list)

    @staticmethod
    def load(path: Path | str = DEFAULT_PATH) -> "Layout":
        path = Path(path)
        if not path.exists():
            return Layout()
        d = json.loads(path.read_text(encoding="utf-8"))
        parts = [Part(**p) for p in d.get("parts", [])]
        d["parts"] = parts
        return Layout(**d)

    @staticmethod
    def for_cat(cat) -> "Layout":
        """按 CatDef.layout_file 加载该猫的部件摆位。"""
        return Layout.load(LAYOUTS_DIR / cat.layout_file)
