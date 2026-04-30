"""活性单元 — 生命核里最小的活性实体."""

from dataclasses import dataclass, field
from typing import Tuple


@dataclass
class Unit:
    """Aniva 的最小活性单元。

    每个 Unit 不是被写死的状态机，而是由动力学规则驱动其状态变化。
    这些规则在 dynamics/energy/noise 模块中定义，Unit 只负责保存状态。

    Attributes:
        uid: 单元唯一标识。
        activation: 当前活性强度 [0, 1]。
        energy: 当前能量水平 [0, 1]。
        threshold: 活性阈值，超过此值才会向外传播影响。
        trace: 历史活动累积痕迹，随活动加深，缓慢衰减。
        position: 空间位置，用于计算局部场效应。
        time_constant: 时间常数，决定状态变化速度。不同单元可不同。
    """

    uid: int
    activation: float = 0.0
    energy: float = 0.5
    threshold: float = 0.3
    trace: float = 0.0
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    time_constant: float = 1.0

    def __post_init__(self):
        if not 0.0 <= self.activation <= 1.0:
            raise ValueError(f"activation must be in [0, 1], got {self.activation}")
        if not 0.0 <= self.energy <= 1.0:
            raise ValueError(f"energy must be in [0, 1], got {self.energy}")
