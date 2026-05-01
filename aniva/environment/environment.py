"""环境模块 — 刺激源管理.

Phase 4.0: 点刺激 (PointStimulus)，按空间距离影响单元。
未来预留: 全局刺激 (GlobalStimulus)、刺激序列、动态环境。
"""

import math
from dataclasses import dataclass
from typing import Tuple
from aniva.core.unit import Unit


def _euclidean_distance(
    p1: Tuple[float, float, float], p2: Tuple[float, float, float]
) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(p1, p2)))


@dataclass
class Stimulus:
    """空间点刺激源。

    在 3D 空间中某位置产生局部影响，按线性距离衰减。
    正 intensity = 兴奋性刺激，负 intensity = 抑制性刺激。

    Attributes:
        position: 刺激源在空间中的 3D 坐标。
        intensity: 刺激强度。
        radius: 影响半径，超过此距离影响为 0。
        start_step: 刺激开始步数。
        duration_steps: 持续步数。
    """

    position: Tuple[float, float, float]
    intensity: float = 1.0
    radius: float = 0.3
    start_step: int = 0
    duration_steps: int = 100

    def __post_init__(self):
        if self.radius <= 0:
            raise ValueError(f"radius must be positive, got {self.radius}")
        if self.duration_steps <= 0:
            raise ValueError(
                f"duration_steps must be positive, got {self.duration_steps}"
            )
        if self.start_step < 0:
            raise ValueError(
                f"start_step must be >= 0, got {self.start_step}"
            )

    @property
    def end_step(self) -> int:
        return self.start_step + self.duration_steps

    def is_active(self, step: int) -> bool:
        return self.start_step <= step < self.end_step

    def influence_at(self, pos: Tuple[float, float, float]) -> float:
        """计算刺激在给定位置的影响强度（线性距离衰减）。"""
        dist = _euclidean_distance(self.position, pos)
        if dist >= self.radius:
            return 0.0
        return self.intensity * (1.0 - dist / self.radius)


class Environment:
    """环境容器 — 管理多个刺激源。

    未来预留:
        - 全局调制信号 (global_modulation)
        - 刺激序列 / 时间表
        - 动态环境变化
    """

    def __init__(self):
        self.stimuli: list[Stimulus] = []

    def add_stimulus(self, stimulus: Stimulus) -> None:
        self.stimuli.append(stimulus)

    def remove_stimulus(self, idx: int) -> None:
        if 0 <= idx < len(self.stimuli):
            self.stimuli.pop(idx)

    def compute_influences(
        self, units: dict[int, Unit], step: int
    ) -> dict[int, float]:
        """计算当前步所有活跃刺激对各单元的总影响。

        Args:
            units: uid -> Unit 映射。
            step: 当前步数，用于判断刺激是否在活跃窗口内。

        Returns:
            dict[uid, total_influence] — 只包含被影响的单元。
        """
        influences: dict[int, float] = {}
        for stim in self.stimuli:
            if not stim.is_active(step):
                continue
            for uid, unit in units.items():
                inf = stim.influence_at(unit.position)
                if inf != 0.0:
                    influences[uid] = influences.get(uid, 0.0) + inf
        return influences
