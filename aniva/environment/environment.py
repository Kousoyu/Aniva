"""极简环境 — 刺激源与环境接口.

第一版环境只定义 Stimulus 数据结构和基本环境容器。
不做复杂空间交互，只验证"外界能影响内部"。
"""

from dataclasses import dataclass
from typing import Tuple, Optional


@dataclass
class Stimulus:
    """一个环境刺激源。

    Attributes:
        position: 刺激源在空间中的位置。
        intensity: 刺激强度，正=兴奋性刺激，负=抑制性刺激。
        radius: 影响半径，刺激只影响此范围内的单元。
    """

    position: Tuple[float, float, float]
    intensity: float = 1.0
    radius: float = 0.3

    def __post_init__(self):
        if self.radius <= 0:
            raise ValueError(f"radius must be positive, got {self.radius}")


class Environment:
    """极简环境容器。

    TODO（后续实现）:
    - 管理刺激源的添加/移除/更新。
    - 计算刺激对单元的影响（空间距离加权）。
    """

    def __init__(self):
        self.stimuli: list[Stimulus] = []

    def add_stimulus(self, stimulus: Stimulus) -> None:
        self.stimuli.append(stimulus)

    def remove_stimulus(self, idx: int) -> None:
        if 0 <= idx < len(self.stimuli):
            self.stimuli.pop(idx)
