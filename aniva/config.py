"""全局配置 — 所有可调参数的集中定义."""

from dataclasses import dataclass


@dataclass
class AnivaConfig:
    """Aniva 生命核的全局配置。

    Attributes:
        unit_count: 活性单元总数。
        connection_density: 连接密度 (0, 1]，每个单元平均连接 = unit_count * density。
        exc_inh_ratio: 兴奋性连接占比，其余为抑制性。
        seed: 随机种子，用于可复现初始化。
        dt: 模拟时间步长（毫秒级逻辑步）。
        noise_strength: 噪声/扰动强度。
        energy_consumption_rate: 能量消耗速率（乘 activation 后每单位时间消耗）。
        energy_recovery_rate: 每步能量恢复速率。
        trace_decay_rate: 历史痕迹衰减速率。
        min_energy_activation_factor: 能量对突触输入响应的最低调制因子。
            energy=1 时 factor=1（完全响应），energy=0 时 factor=此值（最低响应但非零）。
        synaptic_strength: 突触传递强度，控制连接输入对 activation 的影响幅度。
        baseline_activity: activation 的自然回落目标值。
        leak_rate: activation 向 baseline 回落的速率。
        threshold_min: Unit 初始 threshold 下限。
        threshold_max: Unit 初始 threshold 上限。
        threshold_softness: 突触输出软阈值宽度。越小越接近硬阈值。
            sigmoid((activation - threshold) / softness) 控制输出平滑度。
        plasticity_rate: 连接权重变化速率（后续使用）。
        spatial_radius: 单元分布的立方体空间半径（position 的取值范围）。
    """

    unit_count: int = 300
    connection_density: float = 0.05
    exc_inh_ratio: float = 0.5
    seed: int = 42
    dt: float = 0.5
    noise_strength: float = 0.01
    energy_consumption_rate: float = 0.05
    energy_recovery_rate: float = 0.008
    trace_decay_rate: float = 0.001
    min_energy_activation_factor: float = 0.25
    synaptic_strength: float = 0.30
    baseline_activity: float = 0.05
    leak_rate: float = 0.02
    threshold_min: float = 0.2
    threshold_max: float = 0.4
    threshold_softness: float = 0.02
    plasticity_rate: float = 0.0001
    spatial_radius: float = 1.0
    homeostasis_enabled: bool = False
    homeostatic_target_abs_weight: float = 0.30
    homeostatic_rate: float = 1.0
    use_numba_plasticity: bool = False
    # Phase 9: temporal eligibility trace
    temporal_plasticity_enabled: bool = False
    temporal_eligibility_mode: str = "activity"  # "activity" | "onset" | "threshold_crossing"
    temporal_trace_decay: float = 0.05  # EMA decay per dt unit (τ ≈ 20 steps)
    temporal_plasticity_rate: float = 0.5  # weight of eligibility term vs Hebbian term
    temporal_eligibility_clip: float = 1.0  # clamp |eligibility| before weight update
    # Phase 9B: threshold-crossing temporal plasticity
    temporal_crossing_window: int = 200  # max Δt for causal/anti-causal window
    temporal_crossing_strength: float = 0.5  # weight of crossing term
    temporal_crossing_level_mode: str = "unit_threshold"  # "unit_threshold" | "fixed" | "percentile"
    temporal_crossing_fixed_level: float = 0.3  # used if mode = "fixed"
    temporal_crossing_refractory: int = 50  # min steps between crossings per unit
    # Phase 9C: event-pair trace plasticity (all default off)
    event_pair_plasticity_enabled: bool = False
    event_pair_trace_tau: float = 1000.0  # τ_trace, O(N) trace decay time constant
    event_pair_target_update_l1: float = 1e-4  # target L1 norm of event-pair dW
    event_pair_gate_mode: str = "soft_trace_gate"  # "soft_trace_gate" | "bare_l1_norm" | "hard_threshold"
    event_pair_trace_gate_ref: float = 3e-2  # trace_gate_ref
    event_pair_gate_power: float = 1.0  # gate_power
    event_pair_gate_threshold: float = 1e-3  # hard_threshold cutoff
    event_pair_ledger_enabled: bool = False  # dW ledger diagnostics
    # Phase 9D: structural consolidation (all default off)
    consolidation_enabled: bool = False
    consolidation_tag_tau: float = 5000.0  # tag decay time constant (steps)
    consolidation_capture_threshold: float = 0.5  # capture signal must exceed this
    consolidation_slow_weight_max: float = 0.1  # per-connection slow_weight clamp
    consolidation_slow_weight_rate: float = 0.1  # tag → slow_weight transfer ratio
    consolidation_capture_refractory_steps: int = 500  # steps between captures
    consolidation_ledger_enabled: bool = False  # capture event log

    def __post_init__(self):
        if self.unit_count < 1:
            raise ValueError(f"unit_count must be >= 1, got {self.unit_count}")
        if not 0.0 <= self.connection_density <= 1.0:
            raise ValueError(
                f"connection_density must be in [0, 1], got {self.connection_density}"
            )
        if not 0.0 <= self.exc_inh_ratio <= 1.0:
            raise ValueError(
                f"exc_inh_ratio must be in [0, 1], got {self.exc_inh_ratio}"
            )
        if self.dt <= 0.0:
            raise ValueError(f"dt must be positive, got {self.dt}")
        if not 0.0 <= self.threshold_min <= self.threshold_max <= 1.0:
            raise ValueError(
                f"threshold range invalid: [{self.threshold_min}, {self.threshold_max}]"
            )
