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
            threshold = self.rng.uniform(0.2, 0.4)
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

    def step(self) -> None:
        """推进一个时间步。

        对每个 Unit 依次执行：
        0. 突触输入 → 所有 connection 的加权信号聚合到 target
        1. 噪声扰动 → activation 接受微小随机波动
        2. 能量门控 → energy 越低 activation 越被压低（代谢闭环）
        3. 能量消耗 → 活跃消耗能量
        4. 能量恢复 → 能量缓慢自然恢复
        5. 痕迹更新 → activation 加深痕迹，痕迹缓慢衰减
        """
        dt = self.config.dt
        cfg = self.config

        # 0. 突触传递：先计算所有输入，再统一应用（避免顺序依赖）
        synaptic_inputs = compute_synaptic_input(self.connections, self.units)
        for uid, inp in synaptic_inputs.items():
            unit = self.units.get(uid)
            if unit is not None:
                unit.activation += inp * cfg.synaptic_strength * dt
                unit.activation = max(0.0, min(1.0, unit.activation))

        for unit in self.units.values():
            apply_noise(unit, cfg.noise_strength, dt, self.rng)
            # 能量反馈：energy 越低 → activation 越被压低
            energy_factor = (
                cfg.min_energy_activation_factor
                + (1.0 - cfg.min_energy_activation_factor) * unit.energy
            )
            unit.activation *= energy_factor
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
        self.step_count += 1

    @property
    def unit_count(self) -> int:
        return len(self.units)

    @property
    def connection_count(self) -> int:
        return len(self.connections)
