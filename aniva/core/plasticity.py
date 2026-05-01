"""Plasticity — 连接权重随活动历史变化.

Phase 5.0: 最小 Hebbian plasticity + 连续共活性 + 能量门控 + 遗忘.

核心原则：
- 局部规则：每条连接只知道 source 和 target 的当前状态
- 连续共活性：用 sigmoid 软阈值计算 output_strength，不退回二值
- 能量代价：两端单元能量低时 plasticity 暂停
- 遗忘是机制不是 bug：不活跃连接持续衰减
- 无全局 reward / loss / fitness

未来预留：稳态可塑性 (homeostatic plasticity)、连接生长/消亡。
"""

import math
from aniva.core.unit import Unit
from aniva.core.connection import Connection


def _output_strength(
    activation: float, threshold: float, softness: float
) -> float:
    """连续输出强度 — 复用 sigmoid 软阈值。

    activation * sigmoid((activation - threshold) / softness)
    低于 threshold 时有极弱输出，高于 threshold 时输出接近 activation。
    """
    x = (activation - threshold) / softness
    x = max(-60.0, min(60.0, x))
    gate = 1.0 / (1.0 + math.exp(-x))
    return activation * gate


def apply_plasticity(
    connections: list[Connection],
    units: dict[int, Unit],
    plasticity_rate: float,
    threshold_softness: float,
    dt: float,
) -> None:
    """对所有权重执行一步 Hebbian plasticity。

    规则（每条连接独立，仅使用局部信息）：
    1. 计算 source 和 target 的连续 output_strength
    2. coactivity = source_strength * target_strength
    3. energy_gate = min(source.energy, target.energy)
    4. 增强：delta = plasticity_rate * coactivity * dt * energy_gate
       - 兴奋连接 → weight 增加（更正）
       - 抑制连接 → weight 减小（更负）
    5. 衰减：weight *= (1 - decay_rate * dt)
       - decay_rate = plasticity_rate * 0.5
       - 所有连接持续微弱衰减，只有长期反复共激活的能存活
    6. 钳位到 [-1, 1]

    Args:
        connections: 所有连接（原地修改 weight）。
        units: uid -> Unit 映射。
        plasticity_rate: 变化速率（极慢，默认 0.0001）。
        threshold_softness: 软阈值宽度。
        dt: 时间步长。
    """
    decay_rate = plasticity_rate * 0.5
    for conn in connections:
        source = units.get(conn.source_id)
        target = units.get(conn.target_id)
        if source is None or target is None:
            continue

        src_str = _output_strength(
            source.activation, source.threshold, threshold_softness
        )
        tgt_str = _output_strength(
            target.activation, target.threshold, threshold_softness
        )
        coactivity = src_str * tgt_str

        # 能量门控：两端任一能量低 → plasticity 减速
        energy_gate = min(source.energy, target.energy)

        # Hebbian：共激活 → 增强（保持符号方向）
        delta = plasticity_rate * coactivity * dt * energy_gate
        if conn.weight >= 0:
            conn.weight += delta
        else:
            conn.weight -= delta

        # 遗忘：所有连接持续微弱衰减
        conn.weight *= 1.0 - decay_rate * dt

        # 钳位
        conn.weight = max(-1.0, min(1.0, conn.weight))
