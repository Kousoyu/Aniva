"""可塑性 — 连接权重变化与历史痕迹更新.

TODO（后续实现）:
- update_connection_weights: 根据 Hebbian-like 规则更新连接权重（用则强，不用则弱）。
- update_traces: 根据单元 activation 更新其历史痕迹（活跃加深痕迹，不活跃缓慢衰减）。
- 当前仅定义接口签名，不实现任何逻辑。
"""

import numpy as np
from aniva.core.connection import Connection
from aniva.core.unit import Unit


def update_connection_weights(
    connections: list[Connection],
    units: dict[int, Unit],
    plasticity_rate: float,
) -> list[Connection]:
    """根据两端单元的共同活动历史更新连接权重。

    Args:
        connections: 当前所有连接。
        units: uid -> Unit 映射。
        plasticity_rate: 变化速率。

    Returns:
        更新后的连接列表。
    """
    raise NotImplementedError("Plasticity not yet implemented")


def update_traces(units: dict[int, Unit], dt: float) -> dict[int, Unit]:
    """更新所有单元的历史痕迹。

    - 活跃 → 痕迹加深
    - 不活跃 → 痕迹缓慢衰减
    - 痕迹不会低于 0

    Args:
        units: uid -> Unit 映射。
        dt: 时间步长。

    Returns:
        更新后的 units。
    """
    raise NotImplementedError("Plasticity not yet implemented")
