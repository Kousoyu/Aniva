"""动力学 — 活性流动与单元状态更新规则.

TODO（第二步实现）:
- update_unit_state: 计算单个单元下一步状态，整合突触输入、局部场、弥散调节。
- 当前仅定义接口签名，不实现任何逻辑。
"""

import numpy as np
from aniva.core.unit import Unit
from aniva.core.connection import Connection


def update_unit_state(
    unit: Unit,
    connected_units: list[Unit],
    connections: list[Connection],
    dt: float,
) -> Unit:
    """根据所有输入更新一个单元的状态，返回更新后的 Unit。

    Args:
        unit: 当前单元。
        connected_units: 所有与该单元有连接关系的其他单元。
        connections: 与该单元相关的连接。
        dt: 时间步长。

    Returns:
        更新后的 Unit（新对象）。
    """
    raise NotImplementedError("Dynamics not yet implemented")
