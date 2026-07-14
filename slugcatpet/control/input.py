"""操控输入层：InputPackage（一帧操控输入）+ InputBuffer（10 帧历史环）。"""
from __future__ import annotations
from dataclasses import dataclass

BUFFER_LEN = 10


@dataclass
class InputPackage:
    """一帧操控输入。"""
    x: int = 0                    # ∈{-1,0,1}
    y: int = 0                    # ∈{-1,0,1}
    jmp: bool = False
    thrw: bool = False
    pckp: bool = False
    mp: bool = False              # 占位
    spec: bool = False            # 占位
    crouchToggle: bool = False    # 占位
    downDiagonal: int = 0         # 下斜横向符号，派生自 x,y

    def __post_init__(self):
        # 建包即算，(x,y) 纯函数
        self.downDiagonal = self.x if (self.y < 0 and self.x != 0) else 0


class InputBuffer:
    """输入历史环，push 后 [0]=当前。"""

    def __init__(self, length: int = BUFFER_LEN):
        self._len = int(length)
        self._frames = [InputPackage() for _ in range(self._len)]

    def push(self, pkg: InputPackage) -> None:
        self._frames.insert(0, pkg)
        self._frames.pop()

    def __getitem__(self, i: int) -> InputPackage:
        if 0 <= i < len(self._frames):
            return self._frames[i]
        return InputPackage()          # 越界返回全零，不抛

    def __len__(self) -> int:
        return self._len

    def __repr__(self) -> str:
        return f"InputBuffer({self._frames!r})"
