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
    temporal_eligibility_mode: str = "activity",
    activity_traces: np.ndarray | None = None,
    onset_traces: np.ndarray | None = None,
    current_onsets: np.ndarray | None = None,
    temporal_crossing_window: int = 200,
    temporal_crossing_strength: float = 0.5,
    is_crossing: np.ndarray | None = None,
    last_crossing_time: np.ndarray | None = None,
    current_step: int = 0,
) -> None:
    """对所有权重执行一步 Hebbian plasticity（可选 temporal eligibility）。

    规则（每条连接独立，仅使用局部信息）：
    1. 计算 source 和 target 的连续 output_strength
    2. coactivity = source_strength * target_strength
    3. energy_gate = min(source.energy, target.energy)
    4. Hebbian: delta = plasticity_rate * coactivity * dt * energy_gate
       - 兴奋连接 → weight 增加，抑制连接 → weight 减小（更负）
    5. Temporal (Phase 9):
       - "activity" mode: eligibility = pre_trace * post_act - pre_act * post_trace
       - "onset" mode: eligibility = pre_onset_trace * post_onset - post_onset_trace * pre_onset
       - "threshold_crossing" mode: Δt = t_target_cross - t_source_cross
         applied only at target crossing, linear decay kernel over temporal_crossing_window
       - causal (pre before post) → strengthen; anti → weaken
       - threshold_crossing: temporal_delta = plasticity_rate * temporal_crossing_strength * weight_factor * dt
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
        temporal_eligibility_mode: "activity" | "onset" | "threshold_crossing".
        activity_traces: shape (n_units,) EMA activation traces (activity mode).
        onset_traces: shape (n_units,) EMA onset traces (onset mode).
        current_onsets: shape (n_units,) current step onsets (onset mode).
        temporal_crossing_window: max Δt for causal/anti-causal window.
        temporal_crossing_strength: weight of crossing temporal term.
        is_crossing: shape (n_units,) bool — which units crossed this step.
        last_crossing_time: shape (n_units,) int — step of last crossing (-1 if never).
        current_step: current simulation step count.
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
        if temporal_enabled:
            temporal_delta = 0.0
            if temporal_eligibility_mode == "threshold_crossing" and is_crossing is not None and last_crossing_time is not None:
                # Phase 9B: threshold-crossing — applied only when target crosses
                if is_crossing[tid]:
                    t_source = int(last_crossing_time[sid])
                    if t_source >= 0:  # source has crossed at least once
                        dt_val = current_step - t_source
                        if 0 < dt_val <= temporal_crossing_window:
                            weight_factor = max(0.0, 1.0 - dt_val / temporal_crossing_window)
                            temporal_delta = plasticity_rate * temporal_crossing_strength * weight_factor * dt
                        elif -temporal_crossing_window <= dt_val < 0:
                            weight_factor = max(0.0, 1.0 - abs(dt_val) / temporal_crossing_window)
                            temporal_delta = -plasticity_rate * temporal_crossing_strength * weight_factor * dt
            elif temporal_eligibility_mode == "onset" and onset_traces is not None and current_onsets is not None:
                # Phase 9A.4: onset-based — detects "who started firing recently"
                pre_onset_trace = float(onset_traces[sid])
                post_onset_trace = float(onset_traces[tid])
                pre_onset = float(current_onsets[sid])
                post_onset = float(current_onsets[tid])
                # causal: source onset trace was active, target onset is active now
                # anti: target onset trace was active, source onset is active now
                eligibility = pre_onset_trace * post_onset - post_onset_trace * pre_onset
                if eligibility > temporal_eligibility_clip:
                    eligibility = temporal_eligibility_clip
                elif eligibility < -temporal_eligibility_clip:
                    eligibility = -temporal_eligibility_clip
                temporal_delta = plasticity_rate * temporal_plasticity_rate * eligibility * dt
            elif activity_traces is not None:
                # Phase 9A: activity-based — detects "who was active recently"
                pre_trace = float(activity_traces[sid])
                post_trace = float(activity_traces[tid])
                pre_act = float(activations[sid])
                post_act = float(activations[tid])
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
