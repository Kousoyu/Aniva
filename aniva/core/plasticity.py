"""Plasticity — 连接权重随活动历史变化.

Phase 5.0: 最小 Hebbian plasticity + 连续共活性 + 能量门控 + 遗忘.
Phase 6.5: 接受数组而非 Unit 字典，消除 proxy 开销。

核心原则：
- 局部规则：每条连接只知道 source 和 target 的当前状态
- 连续共活性：用 sigmoid 软阈值计算 output_strength，不退回二值
- 能量代价：两端单元能量低时 plasticity 暂停
- 遗忘是机制不是 bug：不活跃连接持续衰减
- 无全局 reward / loss / fitness

未来预留：稳态可塑性 (homeostatic plasticity)、连接生长/消亡。
"""

import math
import numpy as np
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
    activations: np.ndarray,
    thresholds: np.ndarray,
    energies: np.ndarray,
    plasticity_rate: float,
    threshold_softness: float,
    dt: float,
    temporal_enabled: bool = False,
    temporal_trace_decay: float = 0.05,
    temporal_plasticity_rate: float = 0.5,
    temporal_eligibility_clip: float = 1.0,
    activity_traces: np.ndarray | None = None,
) -> None:
    """对所有权重执行一步 Hebbian plasticity（可选 temporal eligibility）。

    规则（每条连接独立，仅使用局部信息）：
    1. 计算 source 和 target 的连续 output_strength
    2. coactivity = source_strength * target_strength
    3. energy_gate = min(source.energy, target.energy)
    4. Hebbian: delta = plasticity_rate * coactivity * dt * energy_gate
       - 兴奋连接 → weight 增加，抑制连接 → weight 减小（更负）
    5. Temporal (Phase 9): eligibility = pre_trace * post_act - pre_act * post_trace
       - causal (pre before post) → strengthen; anti → weaken
       - temporal_delta = plasticity_rate * temporal_plasticity_rate * eligibility * dt
    6. 衰减：weight *= (1 - decay_rate * dt)
    7. 钳位到 [-1, 1]

    Args:
        connections: 所有连接（原地修改 weight）。
        activations: shape (n_units,) 按 uid 索引。
        thresholds: shape (n_units,) 按 uid 索引。
        energies: shape (n_units,) 按 uid 索引。
        plasticity_rate: 变化速率（极慢，默认 0.0001）。
        threshold_softness: 软阈值宽度。
        dt: 时间步长。
        temporal_enabled: 是否启用 eligibility trace (Phase 9)。
        temporal_trace_decay: EMA 衰减率（per dt unit）。
        temporal_plasticity_rate: eligibility 项的相对权重。
        temporal_eligibility_clip: eligibility 绝对值上限。
        activity_traces: shape (n_units,) 快速 EMA 痕迹。
    """
    decay_rate = plasticity_rate * 0.5
    for conn in connections:
        sid = conn.source_id
        tid = conn.target_id

        src_str = _output_strength(
            float(activations[sid]), float(thresholds[sid]), threshold_softness
        )
        tgt_str = _output_strength(
            float(activations[tid]), float(thresholds[tid]), threshold_softness
        )
        coactivity = src_str * tgt_str

        # 能量门控：两端任一能量低 → plasticity 减速
        energy_gate = min(float(energies[sid]), float(energies[tid]))

        # Hebbian：共激活 → 增强（保持符号方向）
        delta = plasticity_rate * coactivity * dt * energy_gate

        # Phase 9: temporal eligibility trace
        if temporal_enabled and activity_traces is not None:
            pre_trace = float(activity_traces[sid])
            post_trace = float(activity_traces[tid])
            pre_act = float(activations[sid])
            post_act = float(activations[tid])
            # causal: pre was active recently, post is active now
            # anti: post was active recently, pre is active now
            eligibility = pre_trace * post_act - pre_act * post_trace
            if eligibility > temporal_eligibility_clip:
                eligibility = temporal_eligibility_clip
            elif eligibility < -temporal_eligibility_clip:
                eligibility = -temporal_eligibility_clip
            temporal_delta = plasticity_rate * temporal_plasticity_rate * eligibility * dt
            delta += temporal_delta

        if conn.weight >= 0:
            conn.weight += delta
        else:
            conn.weight -= delta

        # 遗忘：所有连接持续微弱衰减
        conn.weight *= 1.0 - decay_rate * dt

        # 钳位
        conn.weight = max(-1.0, min(1.0, conn.weight))
