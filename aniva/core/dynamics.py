"""动力学 — 活性流动与单元状态更新规则.

Phase 3: 最小突触传递。
当前实现：compute_synaptic_input 聚合所有连接的加权输入。
局部场效应和弥散调节留待后续版本。
"""

from collections import defaultdict
from aniva.core.unit import Unit
from aniva.core.connection import Connection


def compute_synaptic_input(
    connections: list[Connection],
    units: dict[int, Unit],
) -> dict[int, float]:
    """计算每个单元的突触输入总和。

    两遍法避免顺序依赖：
    - 第一遍：用所有 connection 的 source 当前 activation 计算 contribution，
      累加到 per-target input_sum。
    - 返回 dict，由调用方统一应用到每个 target。

    输入 = Σ(source.activation * connection.weight)，对所有指向 target 的连接。

    Args:
        connections: 所有连接（只读）。
        units: uid -> Unit 映射（只读，使用当前 activation）。

    Returns:
        dict[target_uid, total_synaptic_input]
    """
    input_sum: dict[int, float] = defaultdict(float)
    for conn in connections:
        source = units.get(conn.source_id)
        if source is None:
            continue
        # Thresholded output: 只有超过阈值的活性才向外传播
        effective_output = max(0.0, source.activation - source.threshold)
        contribution = effective_output * conn.weight
        input_sum[conn.target_id] += contribution
    return dict(input_sum)
