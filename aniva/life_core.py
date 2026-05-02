"""生命核 — 组装所有模块的核心引擎.

LifeCore 是 Unit 和 Connection 的容器，负责初始化和步进调度。
"""

import numpy as np
from typing import Optional

from aniva.config import AnivaConfig
from aniva.core.connection import Connection
from aniva.core.noise import apply_noise
from aniva.core.energy import consume_energy, recover_energy
from aniva.core.dynamics import compute_synaptic_input, compute_synaptic_input_vectorized
from aniva.core.plasticity import apply_plasticity

try:
    from aniva.core.plasticity_numba import apply_plasticity_numba, NUMBA_AVAILABLE
except ImportError:
    NUMBA_AVAILABLE = False
    apply_plasticity_numba = None


class _UnitProxy:
    """数组支持的 Unit 兼容代理，用于向后兼容外部代码。

    所有属性读写直接映射到 LifeCore 内部数组，不复制数据。
    """
    __slots__ = ('_core', '_uid')

    def __init__(self, core: 'LifeCore', uid: int):
        self._core = core
        self._uid = uid

    @property
    def uid(self) -> int:
        return self._uid

    @property
    def activation(self) -> float:
        return float(self._core._activations[self._uid])

    @activation.setter
    def activation(self, v: float):
        self._core._activations[self._uid] = v

    @property
    def energy(self) -> float:
        return float(self._core._energies[self._uid])

    @energy.setter
    def energy(self, v: float):
        self._core._energies[self._uid] = v

    @property
    def threshold(self) -> float:
        return float(self._core._thresholds[self._uid])

    @threshold.setter
    def threshold(self, v: float):
        self._core._thresholds[self._uid] = v

    @property
    def trace(self) -> float:
        return float(self._core._traces[self._uid])

    @trace.setter
    def trace(self, v: float):
        self._core._traces[self._uid] = v

    @property
    def position(self) -> tuple:
        return tuple(self._core._positions[self._uid])

    @position.setter
    def position(self, v):
        self._core._positions[self._uid] = v

    @property
    def time_constant(self) -> float:
        return float(self._core._time_constants[self._uid])

    @time_constant.setter
    def time_constant(self, v: float):
        self._core._time_constants[self._uid] = v


class LifeCore:
    """Aniva 生命核。

    管理所有活性单元和它们之间的连接。
    每个 step() 调用推进一个时间步。

    Attributes:
        config: 全局配置。
        units: uid -> _UnitProxy 映射（向后兼容，数组支持）。
        connections: 连接列表。
        rng: NumPy 随机数生成器。
        step_count: 已执行的总步数。
    """

    def __init__(self, config: Optional[AnivaConfig] = None):
        self.config = config or AnivaConfig()
        self.rng = np.random.default_rng(self.config.seed)
        n = self.config.unit_count

        # 数组支持的单元状态（正准存储，按 uid 索引）
        self._activations = np.empty(n, dtype=np.float64)
        self._energies = np.empty(n, dtype=np.float64)
        self._thresholds = np.empty(n, dtype=np.float64)
        self._traces = np.zeros(n, dtype=np.float64)
        self._positions = np.empty((n, 3), dtype=np.float64)
        self._time_constants = np.empty(n, dtype=np.float64)

        # 向后兼容：构建 Unit 兼容代理字典
        self.units: dict[int, _UnitProxy] = {}
        for uid in range(n):
            self.units[uid] = _UnitProxy(self, uid)

        self.connections: list[Connection] = []
        self.step_count: int = 0
        self._next_cid: int = 0
        self._init_units()
        self._init_connections()
        self._build_cache_arrays()

    def _init_units(self) -> None:
        """初始化所有活性单元状态到数组。"""
        sr = self.config.spatial_radius
        for uid in range(self.config.unit_count):
            self._positions[uid] = (
                self.rng.uniform(-sr, sr),
                self.rng.uniform(-sr, sr),
                self.rng.uniform(-sr, sr),
            )
            self._thresholds[uid] = self.rng.uniform(
                self.config.threshold_min, self.config.threshold_max
            )
            self._time_constants[uid] = self.rng.uniform(0.8, 1.2)
            self._energies[uid] = self.rng.uniform(0.4, 0.6)
            self._activations[uid] = 0.0

    def _init_connections(self) -> None:
        """随机初始化稀疏连接，兴奋/抑制比例由 config 控制。"""
        n_possible = self.config.unit_count * (self.config.unit_count - 1)
        n_connections = int(n_possible * self.config.connection_density)

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

    def _build_cache_arrays(self) -> None:
        """构建向量化计算所需的 NumPy 缓存数组。"""
        n_conn = len(self.connections)
        self._source_indices = np.empty(n_conn, dtype=np.int64)
        self._target_indices = np.empty(n_conn, dtype=np.int64)
        self._weight_cache = np.empty(n_conn, dtype=np.float64)
        for i, conn in enumerate(self.connections):
            self._source_indices[i] = conn.source_id
            self._target_indices[i] = conn.target_id
            self._weight_cache[i] = conn.weight

    def _sync_weight_cache(self) -> None:
        """同步权重缓存：在 plasticity/homeostasis 修改 Connection.weight 后调用。"""
        for i, conn in enumerate(self.connections):
            self._weight_cache[i] = conn.weight

    def _sync_connections_from_cache(self) -> None:
        """反向同步：从权重缓存回写到 Connection.weight（Numba 路径使用）。"""
        for i, conn in enumerate(self.connections):
            conn.weight = self._weight_cache[i]

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
        acts = self._activations
        engs = self._energies
        thrs = self._thresholds
        trcs = self._traces
        tcs = self._time_constants
        n_units = cfg.unit_count

        # 0. 环境输入：外界先推动（在突触传递之前，让信号由网络自行传播）
        if env_influences:
            for uid, influence in env_influences.items():
                acts[uid] += influence * dt
                if acts[uid] < 0.0:
                    acts[uid] = 0.0
                elif acts[uid] > 1.0:
                    acts[uid] = 1.0

        # 1. 突触传递：向量化计算所有输入，再统一应用（避免顺序依赖）
        if len(self.connections) != len(self._weight_cache):
            self._build_cache_arrays()
        synaptic_inputs = compute_synaptic_input_vectorized(
            acts, thrs,
            self._source_indices, self._target_indices, self._weight_cache,
            cfg.threshold_softness, n_units,
        )
        for uid, inp in synaptic_inputs.items():
            energy = engs[uid]
            energy_factor = (
                cfg.min_energy_activation_factor
                + (1.0 - cfg.min_energy_activation_factor) * energy
            )
            raw_delta = inp * cfg.synaptic_strength * dt * energy_factor
            act = acts[uid]
            if raw_delta >= 0.0:
                delta = raw_delta * (1.0 - act)
            else:
                delta = raw_delta * act
            acts[uid] = max(0.0, min(1.0, act + delta))

        # 2-6. 逐单元更新：噪声、回落、能量、痕迹
        # 保持逐个 rng.normal() 调用以维持 RNG 序列一致性
        sqrt_dt = dt ** 0.5
        for uid in range(n_units):
            # 噪声
            delta = self.rng.normal(0.0, cfg.noise_strength) * sqrt_dt
            v = acts[uid] + delta
            acts[uid] = 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)

            # 自然回落
            leak_delta = (cfg.baseline_activity - acts[uid]) * cfg.leak_rate * dt / tcs[uid]
            v = acts[uid] + leak_delta
            acts[uid] = 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)

            # 能量消耗
            v = engs[uid] - acts[uid] * cfg.energy_consumption_rate * dt
            engs[uid] = 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)

            # 能量恢复
            v = engs[uid] + cfg.energy_recovery_rate * (1.0 - engs[uid]) * dt
            engs[uid] = 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)

            # 痕迹更新
            trcs[uid] += acts[uid] * dt
            trcs[uid] *= 1.0 - cfg.trace_decay_rate * dt

        # 7. 可塑性：连接权重根据共活性变化
        if cfg.use_numba_plasticity and NUMBA_AVAILABLE:
            # Numba 路径：原地更新 _weight_cache，再同步回 Connection
            apply_plasticity_numba(
                self._source_indices, self._target_indices, self._weight_cache,
                self._activations, self._thresholds, self._energies,
                cfg.plasticity_rate, cfg.threshold_softness, dt,
            )
            self._sync_connections_from_cache()
        else:
            apply_plasticity(
                self.connections,
                self._activations, self._thresholds, self._energies,
                cfg.plasticity_rate, cfg.threshold_softness, dt,
            )

        # 8. 稳态维持（读取 Connection.weight，两种路径均已同步）
        if cfg.homeostasis_enabled and self.connections:
            current = sum(abs(c.weight) for c in self.connections) / len(self.connections)
            if current > 1e-12 and current < cfg.homeostatic_target_abs_weight:
                target = cfg.homeostatic_target_abs_weight
                scale = 1.0 + cfg.homeostatic_rate * ((target / current) - 1.0)
                for conn in self.connections:
                    conn.weight *= scale
                    conn.weight = max(-1.0, min(1.0, conn.weight))

        self._sync_weight_cache()
        self.step_count += 1

    @property
    def unit_count(self) -> int:
        return self.config.unit_count

    @property
    def connection_count(self) -> int:
        return len(self.connections)
