"""环境模块 — 刺激源管理.

Phase 4.0: 点刺激 (PointStimulus)，按空间距离影响单元。
Phase 5.1: 分离 Stimulus（物理性质）与 StimulusEvent（时序调度）。
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
    """空间点刺激源 — 仅描述物理性质。

    在 3D 空间中某位置产生局部影响，按线性距离衰减。
    正 intensity = 兴奋性刺激，负 intensity = 抑制性刺激。

    不携带时间信息。时间调度由 StimulusEvent 管理。
    """

    position: Tuple[float, float, float]
    intensity: float = 1.0
    radius: float = 0.3

    def __post_init__(self):
        if self.radius <= 0:
            raise ValueError(f"radius must be positive, got {self.radius}")

    def influence_at(self, pos: Tuple[float, float, float]) -> float:
        """计算刺激在给定位置的影响强度（线性距离衰减）。"""
        dist = _euclidean_distance(self.position, pos)
        if dist >= self.radius:
            return 0.0
        return self.intensity * (1.0 - dist / self.radius)


@dataclass
class StimulusEvent:
    """一次刺激经历 — 将物理刺激绑定到时间窗口。

    经历的基本单位: (what, when, duration)。
    时间调度不属于 stimulus 本体，而属于"经历"层。
    """

    stimulus: Stimulus
    start_step: int
    duration_steps: int

    def __post_init__(self):
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


class Environment:
    """环境容器 — 管理刺激事件序列。

    未来预留:
        - 全局调制信号 (global_modulation)
        - 概率事件 / 事件序列
        - 动态环境变化
    """

    def __init__(self):
        self.events: list[StimulusEvent] = []

    def add_event(self, event: StimulusEvent) -> None:
        self.events.append(event)

    def remove_event(self, idx: int) -> None:
        if 0 <= idx < len(self.events):
            self.events.pop(idx)

    def compute_influences(
        self, units: dict[int, Unit], step: int
    ) -> dict[int, float]:
        """计算当前步所有活跃刺激事件对各单元的总影响。"""
        influences: dict[int, float] = {}
        for event in self.events:
            if not event.is_active(step):
                continue
            for uid, unit in units.items():
                inf = event.stimulus.influence_at(unit.position)
                if inf != 0.0:
                    influences[uid] = influences.get(uid, 0.0) + inf
        return influences
