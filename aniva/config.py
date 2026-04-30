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
    exc_inh_ratio: float = 0.8
    seed: int = 42
    dt: float = 0.5
    noise_strength: float = 0.01
    energy_consumption_rate: float = 0.05
    energy_recovery_rate: float = 0.008
    trace_decay_rate: float = 0.001
    min_energy_activation_factor: float = 0.25
    synaptic_strength: float = 0.05
    baseline_activity: float = 0.05
    leak_rate: float = 0.02
    threshold_min: float = 0.2
    threshold_max: float = 0.4
    threshold_softness: float = 0.02
    plasticity_rate: float = 0.0001
    spatial_radius: float = 1.0

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
