"""能量系统 — 能量消耗与恢复.

每个单元有独立的能量值。活动消耗能量，能量缓慢恢复。
机制简单且确定：消耗 ∝ activation，恢复 ∝ (1 - energy)。
没有写死的节律——波动由 activation 动态和参数自然产生。
"""

from aniva.core.unit import Unit


def consume_energy(unit: Unit, consumption_rate: float, dt: float) -> Unit:
    """活动消耗能量：activation 越高，消耗越快。

    delta_energy = -activation * consumption_rate * dt

    Args:
        unit: 当前单元。
        consumption_rate: 每单位 activation 的消耗速率。
        dt: 时间步长。

    Returns:
        更新后的 Unit（原位修改并返回）。
    """
    delta = unit.activation * consumption_rate * dt
    unit.energy = max(0.0, min(1.0, unit.energy - delta))
    return unit


def recover_energy(unit: Unit, recovery_rate: float, dt: float) -> Unit:
    """能量自然恢复——越空虚恢复越快，越满越慢。

    delta_energy = recovery_rate * (1 - energy) * dt

    这模仿真实代谢：能量接近 0 时恢复最快，接近满时趋缓。
    不是写死的周期，而是自然的趋近平衡。

    Args:
        unit: 当前单元。
        recovery_rate: 恢复速率。
        dt: 时间步长。

    Returns:
        更新后的 Unit（原位修改并返回）。
    """
    delta = recovery_rate * (1.0 - unit.energy) * dt
    unit.energy = max(0.0, min(1.0, unit.energy + delta))
    return unit
