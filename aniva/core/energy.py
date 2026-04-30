"""能量系统 — 能量消耗与恢复.

TODO（第二步实现）:
- consume_energy: 根据 activation 消耗能量。
- recover_energy: 能量缓慢自然恢复。
- 当前仅定义接口签名，不实现任何逻辑。
"""

from aniva.core.unit import Unit


def consume_energy(unit: Unit, dt: float) -> Unit:
    """活动消耗能量：activation 越高，消耗越快。

    Args:
        unit: 当前单元。
        dt: 时间步长。

    Returns:
        更新后的 Unit。
    """
    raise NotImplementedError("Energy not yet implemented")


def recover_energy(unit: Unit, recovery_rate: float, dt: float) -> Unit:
    """能量自然恢复（像呼吸/代谢）。

    Args:
        unit: 当前单元。
        recovery_rate: 每步恢复速率。
        dt: 时间步长。

    Returns:
        更新后的 Unit。
    """
    raise NotImplementedError("Energy not yet implemented")
