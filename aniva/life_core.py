"""生命核 — 组装所有模块的核心引擎.

LifeCore 是 Unit 和 Connection 的容器，负责初始化和步进调度。
第一版只实现初始化和状态查询，不实现复杂动力学。
"""

import numpy as np
from typing import Optional

from aniva.config import AnivaConfig
from aniva.core.unit import Unit
from aniva.core.connection import Connection
from aniva.core.noise import apply_noise
from aniva.core.energy import consume_energy, recover_energy
from aniva.core.dynamics import compute_synaptic_input
from aniva.core.plasticity import apply_plasticity


class LifeCore:
    """Aniva 生命核。

    管理所有活性单元和它们之间的连接。
    每个 step() 调用推进一个时间步。

    Attributes:
        config: 全局配置。
        units: uid -> Unit 映射。
        connections: 连接列表。
        rng: NumPy 随机数生成器。
        step_count: 已执行的总步数。
    """

    def __init__(self, config: Optional[AnivaConfig] = None):
        self.config = config or AnivaConfig()
        self.rng = np.random.default_rng(self.config.seed)
        self.units: dict[int, Unit] = {}
        self.connections: list[Connection] = []
        self.step_count: int = 0
        self._next_cid: int = 0
        self._init_units()
        self._init_connections()

    def _init_units(self) -> None:
        """初始化所有活性单元，位置在立方体空间内随机分布。"""
        for uid in range(self.config.unit_count):
            position = tuple(
                self.rng.uniform(-self.config.spatial_radius, self.config.spatial_radius)
                for _ in range(3)
            )
            # 初始参数有微小差异（先天种子）
            threshold = self.rng.uniform(
                self.config.threshold_min, self.config.threshold_max
            )
            time_constant = self.rng.uniform(0.8, 1.2)
            energy = self.rng.uniform(0.4, 0.6)
            self.units[uid] = Unit(
                uid=uid,
                activation=0.0,
                energy=energy,
                threshold=threshold,
                position=position,
                time_constant=time_constant,
            )

    def _init_connections(self) -> None:
        """随机初始化稀疏连接，兴奋/抑制比例由 config 控制。"""
        n_possible = self.config.unit_count * (self.config.unit_count - 1)
        n_connections = int(n_possible * self.config.connection_density)

        # 生成所有可能的 (source, target) 对（排除自连接）
        all_pairs = [
            (s, t)
            for s in range(self.config.unit_count)
            for t in range(self.config.unit_count)
            if s != t
        ]
        chosen_indices = self.rng.choice(len(all_pairs), size=n_connections, replace=False)

        for idx in chosen_indices:
            source_id, target_id = all_pairs[idx]
            is_inhibitory = self.rng.random() > self.config.exc_inh_ratio
            if is_inhibitory:
                weight = -self.rng.uniform(0.0, 1.0)
            else:
                weight = self.rng.uniform(0.0, 1.0)
            conn = Connection(
                cid=self._next_cid,
                source_id=source_id,
                target_id=target_id,
                weight=weight,
                is_inhibitory=is_inhibitory,
            )
            self.connections.append(conn)
            self._next_cid += 1

    def step(
        self, env_influences: Optional[dict[int, float]] = None
    ) -> None:
        """推进一个时间步。

        对每个 Unit 依次执行：
        0. 环境输入 → 外界刺激先轻推受影响单元（在突触传递之前）
        1. 突触输入 → 加权信号聚合到 target，受 target energy 调制
        2. 噪声扰动 → activation 接受微小随机波动
        3. 自然回落 → activation 向 baseline 漂移
        4. 能量消耗 → 活跃消耗能量
        5. 能量恢复 → 能量缓慢自然恢复
        6. 痕迹更新 → activation 加深痕迹，痕迹缓慢衰减
        7. 可塑性 → 连接权重根据共活性 + 能量门控 + 遗忘更新

        Args:
            env_influences: 可选，{uid: influence} 映射，由 Environment 计算。
                外部先轻推，网络内部再自行传播。
        """
        dt = self.config.dt
        cfg = self.config

        # 0. 环境输入：外界先推动（在突触传递之前，让信号由网络自行传播）
        if env_influences:
            for uid, influence in env_influences.items():
                unit = self.units.get(uid)
                if unit is not None:
                    unit.activation += influence * dt
                    unit.activation = max(0.0, min(1.0, unit.activation))

        # 1. 突触传递：先计算所有输入，再统一应用（避免顺序依赖）
        #    target 的 energy 调制其对输入的响应强度
        synaptic_inputs = compute_synaptic_input(self.connections, self.units, cfg.threshold_softness)
        for uid, inp in synaptic_inputs.items():
            unit = self.units.get(uid)
            if unit is not None:
                energy_factor = (
                    cfg.min_energy_activation_factor
                    + (1.0 - cfg.min_energy_activation_factor) * unit.energy
                )
                raw_delta = inp * cfg.synaptic_strength * dt * energy_factor
                # 符号分离饱和：
                #   兴奋信号受 (1 - activation) 限制，activation 越高越难继续推高
                #   抑制信号受 activation 限制，activation 越低越难继续压低
                if raw_delta >= 0.0:
                    delta = raw_delta * (1.0 - unit.activation)
                else:
                    delta = raw_delta * unit.activation
                unit.activation += delta
                unit.activation = max(0.0, min(1.0, unit.activation))

        for unit in self.units.values():
            apply_noise(unit, cfg.noise_strength, dt, self.rng)
            # 自然回落：activation 向 baseline 漂移，time_constant 决定速度
            leak_delta = (
                (cfg.baseline_activity - unit.activation)
                * cfg.leak_rate
                * dt
                / unit.time_constant
            )
            unit.activation += leak_delta
            unit.activation = max(0.0, min(1.0, unit.activation))
            consume_energy(unit, cfg.energy_consumption_rate, dt)
            recover_energy(unit, cfg.energy_recovery_rate, dt)
            # Trace: 活跃加深痕迹，再整体缓慢衰减
            unit.trace += unit.activation * dt
            unit.trace *= 1.0 - cfg.trace_decay_rate * dt
        # 7. 可塑性：连接权重根据共活性变化（最后执行，用当前步最终状态）
        apply_plasticity(
            self.connections, self.units,
            cfg.plasticity_rate, cfg.threshold_softness, dt,
        )
        # 8. 稳态维持：防止 weight_abs_mean 持续衰减导致系统静默
        if cfg.homeostasis_enabled and self.connections:
            current = sum(abs(c.weight) for c in self.connections) / len(self.connections)
            if current > 1e-12 and current < cfg.homeostatic_target_abs_weight:
                target = cfg.homeostatic_target_abs_weight
                scale = 1.0 + cfg.homeostatic_rate * ((target / current) - 1.0)
                for conn in self.connections:
                    conn.weight *= scale
                    conn.weight = max(-1.0, min(1.0, conn.weight))
        self.step_count += 1

    @property
    def unit_count(self) -> int:
        return len(self.units)

    @property
    def connection_count(self) -> int:
        return len(self.connections)
