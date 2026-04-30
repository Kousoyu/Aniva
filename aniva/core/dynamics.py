"""动力学 — 活性流动与单元状态更新规则.

Phase 3: 最小突触传递。
Phase 3.14: soft threshold — sigmoid 平滑输出代替硬阈值。
局部场效应和弥散调节留待后续版本。
"""

import math
from collections import defaultdict
from aniva.core.unit import Unit
from aniva.core.connection import Connection


def compute_synaptic_input(
    connections: list[Connection],
    units: dict[int, Unit],
    threshold_softness: float = 0.02,
) -> dict[int, float]:
    """计算每个单元的突触输入总和。

    两遍法避免顺序依赖：
    - 第一遍：用所有 connection 的 source 当前 activation 计算 contribution，
      累加到 per-target input_sum。
    - 返回 dict，由调用方统一应用到每个 target。

    软阈值：effective_output = activation * sigmoid((activation - threshold) / softness)
    低于 threshold 时有极弱输出，高于 threshold 时输出接近 activation。

    Args:
        connections: 所有连接（只读）。
        units: uid -> Unit 映射（只读，使用当前 activation）。
        threshold_softness: 软阈值宽度，越小越接近硬阈值。

    Returns:
        dict[target_uid, total_synaptic_input]
    """
    input_sum: dict[int, float] = defaultdict(float)
    for conn in connections:
        source = units.get(conn.source_id)
        if source is None:
            continue
        # Soft threshold: sigmoid 平滑过渡，避免硬开关导致网络静默
        x = (source.activation - source.threshold) / threshold_softness
        x = max(-60.0, min(60.0, x))  # 防溢出
        gate = 1.0 / (1.0 + math.exp(-x))
        effective_output = source.activation * gate
        contribution = effective_output * conn.weight
        input_sum[conn.target_id] += contribution
    return dict(input_sum)
