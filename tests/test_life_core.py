"""LifeCore 测试."""

import os
import tempfile
import pytest
import numpy as np
from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.core.connection import Connection
from aniva.observer import Observer
from aniva.experiments import exp1_free_run
from aniva.experiments import exp1_parameter_sweep


class TestLifeCoreInit:
    def test_default_init(self):
        """用默认 config 初始化 LifeCore."""
        core = LifeCore()
        assert core.unit_count == 300
        assert core.step_count == 0

    def test_custom_unit_count(self):
        """可以指定单元数量."""
        config = AnivaConfig(unit_count=100, seed=1)
        core = LifeCore(config)
        assert core.unit_count == 100

    def test_seed_determinism(self):
        """相同 seed 产生相同的初始结构."""
        config = AnivaConfig(unit_count=50, seed=123)
        core1 = LifeCore(config)
        core2 = LifeCore(config)

        # 单元属性完全相同
        for uid in range(50):
            u1 = core1.units[uid]
            u2 = core2.units[uid]
            assert u1.uid == u2.uid
            assert u1.position == u2.position
            assert u1.threshold == u2.threshold
            assert u1.time_constant == u2.time_constant
            assert u1.energy == u2.energy

        # 连接完全相同
        assert len(core1.connections) == len(core2.connections)
        for c1, c2 in zip(core1.connections, core2.connections):
            assert c1.source_id == c2.source_id
            assert c1.target_id == c2.target_id
            assert c1.weight == c2.weight

    def test_different_seed_different_structure(self):
        """不同 seed 产生不同的初始结构."""
        core1 = LifeCore(AnivaConfig(unit_count=30, seed=1))
        core2 = LifeCore(AnivaConfig(unit_count=30, seed=2))

        # 位置至少有一个不同
        positions1 = [u.position for u in core1.units.values()]
        positions2 = [u.position for u in core2.units.values()]
        assert positions1 != positions2

    def test_connection_count(self):
        """连接数量符合 config 设置."""
        config = AnivaConfig(unit_count=100, connection_density=0.05, seed=0)
        core = LifeCore(config)
        expected = int(100 * 99 * 0.05)
        assert core.connection_count == expected

    def test_no_self_connections(self):
        """不存在自连接（同一个 unit 不会连到自己）."""
        core = LifeCore(AnivaConfig(unit_count=50, seed=7))
        for conn in core.connections:
            assert conn.source_id != conn.target_id

    def test_all_units_initialized(self):
        """所有单元都有合法的初始值."""
        config = AnivaConfig(unit_count=200, seed=42)
        core = LifeCore(config)
        for uid, unit in core.units.items():
            assert unit.uid == uid
            assert 0.0 <= unit.activation <= 1.0
            assert 0.0 <= unit.energy <= 1.0
            assert config.threshold_min <= unit.threshold <= config.threshold_max
            assert 0.8 <= unit.time_constant <= 1.2
            for coord in unit.position:
                assert -config.spatial_radius <= coord <= config.spatial_radius

    def test_exc_inh_ratio(self):
        """兴奋/抑制比例接近 config 设定."""
        config = AnivaConfig(unit_count=200, connection_density=0.05, exc_inh_ratio=0.8, seed=0)
        core = LifeCore(config)
        exc_count = sum(1 for c in core.connections if not c.is_inhibitory)
        inh_count = sum(1 for c in core.connections if c.is_inhibitory)
        actual_ratio = exc_count / (exc_count + inh_count)
        # 允许统计偏差
        assert abs(actual_ratio - 0.8) < 0.05


class TestLifeCoreStep:
    def test_step_increments_counter(self):
        """step() 会增加步数计数器."""
        core = LifeCore(AnivaConfig(unit_count=10, seed=0))
        assert core.step_count == 0
        core.step()
        assert core.step_count == 1
        core.step()
        assert core.step_count == 2

    def test_step_does_not_crash(self):
        """多次 step() 不会崩溃."""
        core = LifeCore(AnivaConfig(unit_count=10, seed=0))
        for _ in range(100):
            core.step()


class TestLifeCoreStepDynamics:
    """Phase 2: 验证 step() 中的噪声、能量、痕迹机制."""

    def test_activation_changes_after_steps(self):
        """步进足够多步后，activation 不全是初始值."""
        core = LifeCore(AnivaConfig(unit_count=20, seed=42, noise_strength=0.02))
        initial_acts = [u.activation for u in core.units.values()]
        for _ in range(100):
            core.step()
        current_acts = [u.activation for u in core.units.values()]
        # 噪声已作用，至少有些单元的 activation 发生了变化
        diffs = [abs(a - b) for a, b in zip(initial_acts, current_acts)]
        assert any(d > 0 for d in diffs), "No units changed activation after steps"

    def test_activation_stays_in_bounds(self):
        """activation 始终在 [0, 1] 范围内."""
        core = LifeCore(AnivaConfig(unit_count=20, seed=0, noise_strength=0.05))
        for _ in range(200):
            core.step()
        for unit in core.units.values():
            assert 0.0 <= unit.activation <= 1.0, (
                f"Unit {unit.uid} activation={unit.activation} out of [0, 1]"
            )

    def test_energy_stays_in_bounds(self):
        """energy 始终在 [0, 1] 范围内."""
        core = LifeCore(AnivaConfig(unit_count=20, seed=0))
        for _ in range(200):
            core.step()
        for unit in core.units.values():
            assert 0.0 <= unit.energy <= 1.0, (
                f"Unit {unit.uid} energy={unit.energy} out of [0, 1]"
            )

    def test_energy_decreases_when_activation_forced_high(self):
        """当 activation 被人为提高时，energy 会被消耗."""
        # 使用小规模 + 高消耗率来加速观察
        config = AnivaConfig(
            unit_count=1,
            seed=0,
            dt=1.0,
            energy_consumption_rate=0.1,
            energy_recovery_rate=0.0,  # 关闭恢复，只看消耗
            noise_strength=0.0,         # 关闭噪声，排除干扰
        )
        core = LifeCore(config)
        unit = core.units[0]
        unit.activation = 0.8
        unit.energy = 0.5
        initial_energy = unit.energy

        core.step()
        assert unit.energy < initial_energy, (
            f"Energy should decrease when active, was {initial_energy} → {unit.energy}"
        )

    def test_energy_recovers_when_activation_is_zero(self):
        """activation 为 0 且无噪声时，energy 应恢复."""
        config = AnivaConfig(
            unit_count=1,
            seed=0,
            dt=1.0,
            energy_recovery_rate=0.1,
            energy_consumption_rate=0.0,
            noise_strength=0.0,
        )
        core = LifeCore(config)
        unit = core.units[0]
        unit.activation = 0.0
        unit.energy = 0.3
        initial_energy = unit.energy

        core.step()
        assert unit.energy > initial_energy, (
            f"Energy should recover when idle, was {initial_energy} → {unit.energy}"
        )

    def test_trace_accumulates_with_activation(self):
        """trace 随 activation 累积."""
        config = AnivaConfig(
            unit_count=1,
            seed=0,
            dt=1.0,
            noise_strength=0.0,
            trace_decay_rate=0.0,  # 关闭衰减，只看累积
        )
        core = LifeCore(config)
        unit = core.units[0]
        unit.activation = 0.5
        initial_trace = unit.trace

        for _ in range(10):
            core.step()

        assert unit.trace > initial_trace, (
            f"Trace should accumulate: {initial_trace} → {unit.trace}"
        )

    def test_trace_decays_without_activation(self):
        """不活跃时 trace 会衰减."""
        config = AnivaConfig(
            unit_count=1,
            seed=0,
            dt=1.0,
            noise_strength=0.0,
            trace_decay_rate=0.1,
        )
        core = LifeCore(config)
        unit = core.units[0]
        unit.trace = 1.0
        unit.activation = 0.0

        core.step()
        assert unit.trace < 1.0, f"Trace should decay: got {unit.trace}"

    def test_noise_only_changes_activation_not_energy(self):
        """噪声只扰动 activation，不直接改 energy."""
        config = AnivaConfig(
            unit_count=20,
            seed=0,
            noise_strength=0.05,
            energy_consumption_rate=0.0,
            energy_recovery_rate=0.0,
        )
        core = LifeCore(config)
        initial_energies = [u.energy for u in core.units.values()]

        for _ in range(10):
            core.step()

        current_energies = [u.energy for u in core.units.values()]
        assert initial_energies == current_energies, (
            "Energy should not change when consumption and recovery are disabled"
        )

    def test_seed_determinism_after_steps(self):
        """相同 seed 运行相同步数后，状态完全一致."""
        config = AnivaConfig(unit_count=10, seed=99, dt=1.0, noise_strength=0.1)
        core1 = LifeCore(config)
        core2 = LifeCore(config)

        for _ in range(50):
            core1.step()
            core2.step()

        for uid in core1.units:
            u1 = core1.units[uid]
            u2 = core2.units[uid]
            assert u1.activation == u2.activation, (
                f"Activation mismatch at unit {uid}: {u1.activation} vs {u2.activation}"
            )
            assert u1.energy == u2.energy
            assert u1.trace == u2.trace

    def test_different_seed_diverges(self):
        """不同 seed 运行足够步数后，轨迹出现差异."""
        config1 = AnivaConfig(unit_count=5, seed=1, dt=1.0, noise_strength=0.1)
        config2 = AnivaConfig(unit_count=5, seed=999, dt=1.0, noise_strength=0.1)
        core1 = LifeCore(config1)
        core2 = LifeCore(config2)

        for _ in range(50):
            core1.step()
            core2.step()

        acts1 = [u.activation for u in core1.units.values()]
        acts2 = [u.activation for u in core2.units.values()]
        assert acts1 != acts2, "Different seeds should produce different trajectories"

    def test_activation_not_all_zero_after_long_run(self):
        """长时间运行后不仅不会全零，还有非零 activation（噪声保持活性）."""
        core = LifeCore(AnivaConfig(unit_count=30, seed=123, noise_strength=0.02, dt=1.0))
        for _ in range(500):
            core.step()
        acts = [u.activation for u in core.units.values()]
        # 有些单元因噪声偏离 0
        non_zero = sum(1 for a in acts if a > 0.0)
        assert non_zero > 0, f"Expected some non-zero activations, got all zeros"


class TestEnergyFeedback:
    """Phase 3.11: energy gate 调制突触输入响应，而非直接压 activation."""

    def test_low_energy_target_responds_weaker_to_synaptic(self):
        """低 energy 的 target 对同样的突触输入响应更弱."""
        config = AnivaConfig(
            unit_count=2,
            seed=0,
            dt=1.0,
            noise_strength=0.0,
            energy_consumption_rate=0.0,
            energy_recovery_rate=0.0,
            connection_density=0.0,
            synaptic_strength=0.1,
            min_energy_activation_factor=0.25,
            baseline_activity=0.0,
            leak_rate=0.0,
            threshold_min=0.0,
            threshold_max=0.0,
        )
        core = LifeCore(config)
        core.connections.clear()
        core.connections.append(Connection(cid=0, source_id=0, target_id=1, weight=0.5))
        core.units[0].activation = 0.8
        core.units[0].energy = 1.0
        core.units[1].activation = 0.0
        core.units[1].energy = 0.1  # 低能量

        core.step()
        # effective_output = 0.8, contribution = 0.8*0.5 = 0.4
        # energy_factor = 0.25 + 0.75*0.1 = 0.325
        # delta = 0.4 * 0.1 * 1.0 * 0.325 = 0.013
        assert core.units[1].activation == pytest.approx(0.013), (
            f"Low energy target should respond weakly, got {core.units[1].activation}"
        )

    def test_high_energy_target_responds_stronger_to_synaptic(self):
        """高 energy 的 target 对同样的突触输入响应更强."""
        config = AnivaConfig(
            unit_count=2,
            seed=0,
            dt=1.0,
            noise_strength=0.0,
            energy_consumption_rate=0.0,
            energy_recovery_rate=0.0,
            connection_density=0.0,
            synaptic_strength=0.1,
            min_energy_activation_factor=0.25,
            baseline_activity=0.0,
            leak_rate=0.0,
            threshold_min=0.0,
            threshold_max=0.0,
        )
        core = LifeCore(config)
        core.connections.clear()
        core.connections.append(Connection(cid=0, source_id=0, target_id=1, weight=0.5))
        core.units[0].activation = 0.8
        core.units[0].energy = 1.0
        core.units[1].activation = 0.0
        core.units[1].energy = 1.0  # 高能量

        core.step()
        # energy_factor = 0.25 + 0.75*1.0 = 1.0
        # delta = 0.4 * 0.1 * 1.0 * 1.0 = 0.04
        assert core.units[1].activation == pytest.approx(0.04), (
            f"High energy target should respond fully, got {core.units[1].activation}"
        )

    def test_energy_gate_no_direct_effect_without_input(self):
        """无输入、无噪声、无 leak、无消耗时，energy gate 不单独改变 activation."""
        config = AnivaConfig(
            unit_count=5,
            seed=0,
            dt=1.0,
            noise_strength=0.0,
            energy_consumption_rate=0.0,
            energy_recovery_rate=0.0,
            connection_density=0.0,
            min_energy_activation_factor=0.25,
            baseline_activity=0.0,
            leak_rate=0.0,
        )
        core = LifeCore(config)
        for unit in core.units.values():
            unit.activation = 0.5
            unit.energy = 0.3  # 低能量，旧 gate 会压制，新 gate 不应该

        initial_acts = [u.activation for u in core.units.values()]
        core.step()
        current_acts = [u.activation for u in core.units.values()]
        assert initial_acts == current_acts, (
            "Without input, energy gate should not change activation"
        )

    def test_energy_gate_bounds_and_determinism(self):
        """新 energy gate 下 activation 不越界且可复现."""
        config = AnivaConfig(
            unit_count=10,
            seed=42,
            dt=1.0,
            noise_strength=0.05,
            synaptic_strength=0.1,
            min_energy_activation_factor=0.25,
        )
        core1 = LifeCore(config)
        core2 = LifeCore(config)

        for _ in range(50):
            core1.step()
            core2.step()
            for unit in core1.units.values():
                assert 0.0 <= unit.activation <= 1.0, (
                    f"Unit {unit.uid} activation={unit.activation} out of [0, 1]"
                )

        for uid in core1.units:
            u1 = core1.units[uid]
            u2 = core2.units[uid]
            assert u1.activation == u2.activation
            assert u1.energy == u2.energy
            assert u1.trace == u2.trace


class TestEnergyBalance:
    """Phase 3.12: energy balance — 默认参数下存在合理的 energy 稳态."""

    def test_default_recovery_exceeds_baseline_consumption(self):
        """recovery_rate 大于 baseline 消耗，否则 energy 必崩."""
        cfg = AnivaConfig()
        consumption_at_baseline = cfg.baseline_activity * cfg.energy_consumption_rate
        assert cfg.energy_recovery_rate > consumption_at_baseline, (
            f"recovery_rate={cfg.energy_recovery_rate} must exceed "
            f"baseline consumption={consumption_at_baseline}"
        )

    def test_energy_converges_at_baseline_activity(self):
        """baseline 活性下，energy 收敛到非零稳态."""
        config = AnivaConfig(
            unit_count=1,
            seed=0,
            dt=1.0,
            noise_strength=0.0,
            connection_density=0.0,
            baseline_activity=0.05,
            leak_rate=0.0,
            energy_consumption_rate=0.05,
            energy_recovery_rate=0.008,
        )
        core = LifeCore(config)
        unit = core.units[0]
        unit.activation = 0.05  # = baseline
        unit.energy = 0.4

        for _ in range(200):
            core.step()

        # 稳态: 0.05*0.05 = 0.008*(1-e) → e ≈ 0.6875
        assert unit.energy > 0.5, (
            f"Energy should converge above 0.5, got {unit.energy}"
        )
        assert unit.energy < 0.9, (
            f"Energy should not overshoot, got {unit.energy}"
        )

    def test_high_activation_still_drains_energy(self):
        """高 activation 仍然消耗 energy（疲劳机制保留）."""
        config = AnivaConfig(
            unit_count=1,
            seed=0,
            dt=1.0,
            noise_strength=0.0,
            connection_density=0.0,
            baseline_activity=0.05,
            leak_rate=0.0,
            energy_consumption_rate=0.05,
            energy_recovery_rate=0.008,
        )
        core = LifeCore(config)
        unit = core.units[0]
        unit.activation = 0.5
        unit.energy = 0.7

        initial_energy = unit.energy
        for _ in range(50):
            core.step()

        assert unit.energy < initial_energy, (
            f"High activation should drain energy: {initial_energy} → {unit.energy}"
        )

    def test_low_activation_allows_recovery(self):
        """低于稳态时 energy 可以恢复."""
        config = AnivaConfig(
            unit_count=1,
            seed=0,
            dt=1.0,
            noise_strength=0.0,
            connection_density=0.0,
            baseline_activity=0.05,
            leak_rate=0.0,
            energy_consumption_rate=0.05,
            energy_recovery_rate=0.008,
        )
        core = LifeCore(config)
        unit = core.units[0]
        unit.activation = 0.0
        unit.energy = 0.3

        initial_energy = unit.energy
        for _ in range(50):
            core.step()

        assert unit.energy > initial_energy, (
            f"Low activation should allow recovery: {initial_energy} → {unit.energy}"
        )

    def test_energy_balance_determinism(self):
        """能量修正不影响确定性."""
        config = AnivaConfig(
            unit_count=10,
            seed=42,
            dt=1.0,
            noise_strength=0.05,
        )
        core1 = LifeCore(config)
        core2 = LifeCore(config)

        for _ in range(50):
            core1.step()
            core2.step()

        for uid in core1.units:
            assert core1.units[uid].energy == core2.units[uid].energy
            assert core1.units[uid].activation == core2.units[uid].activation


class TestSynapticDiagnostics:
    """Phase 3.13: 突触影响诊断——判断活性来自 noise 还是网络传导."""

    def test_metrics_includes_synaptic_fields(self):
        """get_metrics 包含 6 个突触诊断字段."""
        core = LifeCore(AnivaConfig(unit_count=10, seed=0))
        obs = Observer(core)
        metrics = obs.get_metrics()
        for field in [
            "source_active_ratio", "mean_effective_output", "max_effective_output",
            "mean_abs_synaptic_input", "max_abs_synaptic_input", "synaptic_target_ratio",
        ]:
            assert field in metrics, f"Missing synaptic field: {field}"

    def test_synaptic_field_types(self):
        """突触诊断字段类型正确."""
        core = LifeCore(AnivaConfig(unit_count=10, seed=0))
        obs = Observer(core)
        metrics = obs.get_metrics()
        assert isinstance(metrics["source_active_ratio"], float)
        assert isinstance(metrics["mean_effective_output"], float)
        assert isinstance(metrics["max_effective_output"], float)
        assert isinstance(metrics["mean_abs_synaptic_input"], float)
        assert isinstance(metrics["max_abs_synaptic_input"], float)
        assert isinstance(metrics["synaptic_target_ratio"], float)

    def test_source_active_ratio_in_range(self):
        """source_active_ratio 在 [0, 1]."""
        core = LifeCore(AnivaConfig(unit_count=20, seed=0))
        obs = Observer(core)
        for _ in range(20):
            core.step()
        metrics = obs.get_metrics()
        assert 0.0 <= metrics["source_active_ratio"] <= 1.0

    def test_synaptic_target_ratio_in_range(self):
        """synaptic_target_ratio 在 [0, 1]."""
        core = LifeCore(AnivaConfig(unit_count=20, seed=0))
        obs = Observer(core)
        for _ in range(20):
            core.step()
        metrics = obs.get_metrics()
        assert 0.0 <= metrics["synaptic_target_ratio"] <= 1.0

    def test_no_connections_zero_synaptic_input(self):
        """无连接时 mean_abs_synaptic_input = 0."""
        config = AnivaConfig(
            unit_count=10, seed=0,
            connection_density=0.0,  # 零连接
        )
        core = LifeCore(config)
        obs = Observer(core)
        metrics = obs.get_metrics()
        assert metrics["mean_abs_synaptic_input"] == 0.0
        assert metrics["max_abs_synaptic_input"] == 0.0
        assert metrics["synaptic_target_ratio"] == 0.0

    def test_above_threshold_source_produces_output(self):
        """source 超过 threshold 时 effective_output > 0."""
        config = AnivaConfig(
            unit_count=5, seed=0,
            connection_density=0.0,
            noise_strength=0.0,
            baseline_activity=0.0,
            leak_rate=0.0,
        )
        core = LifeCore(config)
        obs = Observer(core)
        # 手动设一个单元 activation 超过 threshold
        core.units[0].activation = 0.5
        core.units[0].threshold = 0.2
        metrics = obs.get_metrics()
        assert metrics["source_active_ratio"] > 0.0, (
            f"Expected source_active_ratio > 0, got {metrics['source_active_ratio']}"
        )
        assert metrics["max_effective_output"] > 0.0

    def test_strong_connection_produces_synaptic_input(self):
        """有强连接且 source 超 threshold 时，突触输入 > 0."""
        config = AnivaConfig(
            unit_count=2, seed=0,
            dt=1.0,
            connection_density=0.0,
            noise_strength=0.0,
            baseline_activity=0.0,
            leak_rate=0.0,
        )
        core = LifeCore(config)
        core.connections.clear()
        core.connections.append(
            Connection(cid=0, source_id=0, target_id=1, weight=0.8)
        )
        core.units[0].activation = 0.6
        core.units[0].threshold = 0.2
        core.units[1].activation = 0.0

        obs = Observer(core)
        metrics = obs.get_metrics()
        # sigmoid((0.6-0.2)/0.05)=sigmoid(8)≈1.0, output≈0.6, contribution≈0.48
        assert metrics["mean_abs_synaptic_input"] > 0.0, (
            f"Expected synaptic input > 0, got {metrics['mean_abs_synaptic_input']}"
        )
        assert metrics["max_abs_synaptic_input"] == pytest.approx(0.48, rel=0.05)
        assert metrics["synaptic_target_ratio"] > 0.0

    def test_sweep_output_includes_synaptic_fields(self):
        """参数扫描输出包含突触诊断字段."""
        results = exp1_parameter_sweep.sweep(
            noise_strengths=[0.01],
            baseline_activities=[0.05],
            synaptic_strengths=[0.05],
            seeds=[1],
            unit_count=5,
            total_steps=10,
        )
        row = results[0]
        for field in [
            "source_active_ratio", "mean_effective_output", "max_effective_output",
            "mean_abs_synaptic_input", "max_abs_synaptic_input", "synaptic_target_ratio",
        ]:
            assert field in row, f"Missing synaptic field in sweep: {field}"

    def test_soft_threshold_below_produces_tiny_output(self):
        """低于 threshold 仍有极弱但非零的 effective_output."""
        config = AnivaConfig(
            unit_count=5, seed=0,
            connection_density=0.0,
            noise_strength=0.0,
            baseline_activity=0.0,
            leak_rate=0.0,
            threshold_softness=0.05,
        )
        core = LifeCore(config)
        obs = Observer(core)
        core.units[0].activation = 0.05
        core.units[0].threshold = 0.2
        metrics = obs.get_metrics()
        # sigmoid((0.05-0.2)/0.05)=sigmoid(-3)≈0.047, output=0.05*0.047≈0.0024
        assert metrics["mean_effective_output"] > 0.0, (
            "Soft threshold should allow sub-threshold output"
        )
        assert metrics["mean_effective_output"] < 0.01, (
            f"Sub-threshold output should be tiny, got {metrics['mean_effective_output']}"
        )

    def test_softness_smaller_is_harder(self):
        """threshold_softness 越小越接近硬阈值."""
        config = AnivaConfig(
            unit_count=5, seed=0,
            connection_density=0.0,
            noise_strength=0.0,
            baseline_activity=0.0,
            leak_rate=0.0,
            threshold_softness=0.001,  # 极硬
        )
        core = LifeCore(config)
        obs = Observer(core)
        core.units[0].activation = 0.15
        core.units[0].threshold = 0.2
        metrics = obs.get_metrics()
        # (0.15-0.2)/0.001=-50, sigmoid(-50)≈1.9e-22, output≈0
        assert metrics["mean_effective_output"] < 1e-6, (
            f"Hard-like softness should suppress deep sub-threshold output, "
            f"got {metrics['mean_effective_output']}"
        )

    def test_effective_output_never_exceeds_activation(self):
        """effective_output 不超过 source activation."""
        config = AnivaConfig(
            unit_count=5, seed=0,
            connection_density=0.0,
            noise_strength=0.0,
            baseline_activity=0.0,
            leak_rate=0.0,
        )
        core = LifeCore(config)
        obs = Observer(core)
        # 混合各种 activation 水平
        for uid, unit in core.units.items():
            unit.activation = uid / 5.0  # 0.0, 0.2, 0.4, 0.6, 0.8
        metrics = obs.get_metrics()
        assert metrics["max_effective_output"] <= metrics["max_activation"], (
            f"effective_output must not exceed activation: "
            f"{metrics['max_effective_output']} > {metrics['max_activation']}"
        )

    def test_default_softness_config_value(self):
        """threshold_softness 默认值正确."""
        cfg = AnivaConfig()
        assert cfg.threshold_softness == 0.02

    def test_default_softness_stable_no_explosion(self):
        """默认 softness=0.02 下 1000 步不爆燃."""
        config = AnivaConfig(unit_count=300, seed=42)
        core = LifeCore(config)
        obs = Observer(core)
        for _ in range(1000):
            core.step()
        metrics = obs.get_metrics()
        assert metrics["mean_activation"] < 0.8, (
            f"Default softness should not explode: mean_act={metrics['mean_activation']}"
        )
        assert metrics["mean_energy"] > 0.05, (
            f"Default softness should not drain energy: mean_energy={metrics['mean_energy']}"
        )
        assert metrics["mean_abs_synaptic_input"] > 0.0, (
            "Default softness should allow some synaptic conduction"
        )


class TestSynapticTransmission:
    """Phase 3: 最小突触传递——Unit 通过 Connection 互相影响."""

    def test_excitatory_connection_increases_target(self):
        """兴奋性连接增加 target 的 activation."""
        config = AnivaConfig(
            unit_count=2,
            seed=0,
            dt=1.0,
            noise_strength=0.0,
            energy_consumption_rate=0.0,
            energy_recovery_rate=0.0,
            synaptic_strength=0.1,
            connection_density=0.0,  # 低密度让自动连接很少
        )
        core = LifeCore(config)
        # 清空自动生成的连接，手动创建测试连接
        core.connections.clear()
        core.connections.append(Connection(cid=0, source_id=0, target_id=1, weight=0.8))
        # 设置初始状态
        core.units[0].activation = 0.5
        core.units[0].energy = 1.0
        core.units[1].activation = 0.0
        core.units[1].energy = 1.0

        core.step()
        # input = 0.5 * 0.8 = 0.4, delta = 0.4 * 0.1 * 1.0 = 0.04
        assert core.units[1].activation > 0.0, (
            f"Excitatory connection should increase target activation, got {core.units[1].activation}"
        )

    def test_inhibitory_connection_decreases_target(self):
        """抑制性连接降低 target 的 activation."""
        config = AnivaConfig(
            unit_count=2,
            seed=0,
            dt=1.0,
            noise_strength=0.0,
            energy_consumption_rate=0.0,
            energy_recovery_rate=0.0,
            synaptic_strength=0.1,
            connection_density=0.0,
        )
        core = LifeCore(config)
        core.connections.clear()
        core.connections.append(
            Connection(cid=0, source_id=0, target_id=1, weight=-0.5, is_inhibitory=True)
        )
        core.units[0].activation = 0.8
        core.units[0].energy = 1.0
        core.units[1].activation = 0.5
        core.units[1].energy = 1.0

        initial_act = core.units[1].activation
        core.step()
        # input = 0.8 * -0.5 = -0.4, delta = -0.4 * 0.1 = -0.04
        assert core.units[1].activation < initial_act, (
            f"Inhibitory connection should decrease target, {initial_act} → {core.units[1].activation}"
        )

    def test_multiple_inputs_stack(self):
        """多个连接输入可以叠加."""
        config = AnivaConfig(
            unit_count=3,
            seed=0,
            dt=1.0,
            noise_strength=0.0,
            energy_consumption_rate=0.0,
            energy_recovery_rate=0.0,
            synaptic_strength=0.1,
            connection_density=0.0,
        )
        core = LifeCore(config)
        core.connections.clear()
        core.connections.append(Connection(cid=0, source_id=0, target_id=2, weight=0.5))
        core.connections.append(Connection(cid=1, source_id=1, target_id=2, weight=0.3))
        # 再加一条连接到 unit 2 的抑制连接
        core.connections.append(
            Connection(cid=2, source_id=0, target_id=1, weight=-0.2, is_inhibitory=True)
        )

        core.units[0].activation = 0.5
        core.units[1].activation = 0.5
        core.units[2].activation = 0.0
        for uid in range(3):
            core.units[uid].energy = 1.0

        core.step()
        # unit 2: input = 0.5*0.5 + 0.5*0.3 = 0.25+0.15 = 0.4, delta = 0.04
        # unit 1: input = 0.5*-0.2 = -0.1, delta = -0.01
        assert core.units[2].activation > 0.0, (
            f"Stacked inputs should increase activation, got {core.units[2].activation}"
        )
        assert core.units[1].activation < 0.5, (
            f"Inhibitory input should decrease activation, got {core.units[1].activation}"
        )

    def test_no_connections_no_synaptic_change(self):
        """无连接且无噪声且关闭代谢时，activation 不应变化."""
        config = AnivaConfig(
            unit_count=5,
            seed=0,
            dt=1.0,
            noise_strength=0.0,
            energy_consumption_rate=0.0,
            energy_recovery_rate=0.0,
            connection_density=0.0,
            min_energy_activation_factor=1.0,
            baseline_activity=0.0,
            leak_rate=0.0,
        )
        core = LifeCore(config)
        for unit in core.units.values():
            unit.activation = 0.3
            unit.energy = 1.0

        initial_acts = [u.activation for u in core.units.values()]
        core.step()
        current_acts = [u.activation for u in core.units.values()]
        assert initial_acts == current_acts, (
            "Without connections and noise, activations should not change"
        )

    def test_activation_stays_in_bounds_with_synaptic(self):
        """加入突触传递后，activation 仍不越界."""
        config = AnivaConfig(
            unit_count=20,
            seed=0,
            dt=1.0,
            noise_strength=0.1,
            synaptic_strength=0.1,
        )
        core = LifeCore(config)
        # 混合极端值
        for unit in core.units.values():
            unit.activation = 1.0 if unit.uid % 2 == 0 else 0.0
            unit.energy = 1.0

        for _ in range(100):
            core.step()
            for unit in core.units.values():
                assert 0.0 <= unit.activation <= 1.0, (
                    f"Unit {unit.uid} activation={unit.activation}"
                )

    def test_synaptic_seed_determinism(self):
        """加入突触传递后，相同 seed 仍然可复现."""
        config = AnivaConfig(
            unit_count=10,
            seed=77,
            dt=1.0,
            noise_strength=0.05,
            synaptic_strength=0.1,
        )
        core1 = LifeCore(config)
        core2 = LifeCore(config)

        for _ in range(50):
            core1.step()
            core2.step()

        for uid in core1.units:
            u1 = core1.units[uid]
            u2 = core2.units[uid]
            assert u1.activation == u2.activation
            assert u1.energy == u2.energy
            assert u1.trace == u2.trace


class TestLeakAndThreshold:
    """Phase 3.5: activation leak + threshold gating."""

    def test_activation_leaks_down_to_baseline(self):
        """高于 baseline 时，activation 回落."""
        config = AnivaConfig(
            unit_count=1,
            seed=0,
            dt=1.0,
            noise_strength=0.0,
            energy_consumption_rate=0.0,
            energy_recovery_rate=0.0,
            connection_density=0.0,
            min_energy_activation_factor=1.0,
            baseline_activity=0.05,
            leak_rate=0.1,
        )
        core = LifeCore(config)
        unit = core.units[0]
        unit.activation = 0.8
        unit.energy = 1.0
        unit.time_constant = 1.0

        core.step()
        # leak = (0.05 - 0.8) * 0.1 * 1.0 / 1.0 = -0.075 → 0.725
        assert unit.activation < 0.8, (
            f"Activation should leak down from 0.8, got {unit.activation}"
        )

    def test_activation_leaks_up_to_baseline(self):
        """低于 baseline 时，activation 缓慢上升."""
        config = AnivaConfig(
            unit_count=1,
            seed=0,
            dt=1.0,
            noise_strength=0.0,
            energy_consumption_rate=0.0,
            energy_recovery_rate=0.0,
            connection_density=0.0,
            min_energy_activation_factor=1.0,
            baseline_activity=0.05,
            leak_rate=0.1,
        )
        core = LifeCore(config)
        unit = core.units[0]
        unit.activation = 0.0
        unit.energy = 1.0
        unit.time_constant = 1.0

        core.step()
        # leak = (0.05 - 0.0) * 0.1 * 1.0 / 1.0 = +0.005
        assert unit.activation > 0.0, (
            f"Activation should leak up from 0, got {unit.activation}"
        )

    def test_time_constant_slows_leak(self):
        """time_constant 越大，leak 变化越慢."""
        config = AnivaConfig(
            unit_count=2,
            seed=0,
            dt=1.0,
            noise_strength=0.0,
            energy_consumption_rate=0.0,
            energy_recovery_rate=0.0,
            connection_density=0.0,
            min_energy_activation_factor=1.0,
            baseline_activity=0.05,
            leak_rate=0.1,
        )
        core = LifeCore(config)
        u_fast = core.units[0]
        u_slow = core.units[1]
        u_fast.activation = 0.8
        u_fast.energy = 1.0
        u_fast.time_constant = 0.5  # 快
        u_slow.activation = 0.8
        u_slow.energy = 1.0
        u_slow.time_constant = 2.0  # 慢

        core.step()
        # fast: (0.05-0.8)*0.1/0.5 = -0.15 → 0.65
        # slow: (0.05-0.8)*0.1/2.0 = -0.0375 → 0.7625
        assert u_fast.activation < u_slow.activation, (
            f"Fast unit TC={u_fast.time_constant} should leak more: "
            f"fast={u_fast.activation}, slow={u_slow.activation}"
        )

    def test_source_below_threshold_produces_weak_output(self):
        """source 低于 threshold 时，soft threshold 仍有极弱输出."""
        config = AnivaConfig(
            unit_count=2,
            seed=0,
            dt=1.0,
            noise_strength=0.0,
            energy_consumption_rate=0.0,
            energy_recovery_rate=0.0,
            connection_density=0.0,
            min_energy_activation_factor=1.0,
            synaptic_strength=0.1,
            baseline_activity=0.0,
            leak_rate=0.0,
            threshold_softness=0.05,
        )
        core = LifeCore(config)
        core.connections.clear()
        core.connections.append(Connection(cid=0, source_id=0, target_id=1, weight=0.8))
        core.units[0].activation = 0.1   # 低于 threshold=0.3
        core.units[0].threshold = 0.3
        core.units[0].energy = 1.0
        core.units[1].activation = 0.0
        core.units[1].energy = 1.0

        core.step()
        # sigmoid((0.1-0.3)/0.05)=sigmoid(-4)≈0.018, effective_output=0.1*0.018≈0.0018
        # contribution=0.0018*0.8=0.00144, delta≈0.000144
        assert core.units[1].activation > 0.0, (
            f"Soft threshold: even below threshold should have weak output"
        )
        assert core.units[1].activation < 0.001, (
            f"Below-threshold output should be very small, got {core.units[1].activation}"
        )

    def test_source_above_threshold_affects_target(self):
        """source 高于 threshold 时，影响 target."""
        config = AnivaConfig(
            unit_count=2,
            seed=0,
            dt=1.0,
            noise_strength=0.0,
            energy_consumption_rate=0.0,
            energy_recovery_rate=0.0,
            connection_density=0.0,
            min_energy_activation_factor=1.0,
            synaptic_strength=0.1,
            baseline_activity=0.0,
            leak_rate=0.0,
        )
        core = LifeCore(config)
        core.connections.clear()
        core.connections.append(Connection(cid=0, source_id=0, target_id=1, weight=0.5))
        core.units[0].activation = 0.8
        core.units[0].threshold = 0.3
        core.units[0].energy = 1.0
        core.units[1].activation = 0.0
        core.units[1].energy = 1.0

        core.step()
        # sigmoid((0.8-0.3)/0.05)=sigmoid(10)≈1.0 → output≈0.8 → delta≈0.04
        assert core.units[1].activation > 0.0, (
            f"Above-threshold source should affect target, got {core.units[1].activation}"
        )

    def test_leak_and_threshold_determinism(self):
        """加入 leak 和 threshold 后，相同 seed 仍然可复现."""
        config = AnivaConfig(
            unit_count=10,
            seed=88,
            dt=1.0,
            noise_strength=0.05,
            synaptic_strength=0.1,
            baseline_activity=0.05,
            leak_rate=0.02,
        )
        core1 = LifeCore(config)
        core2 = LifeCore(config)

        for _ in range(50):
            core1.step()
            core2.step()

        for uid in core1.units:
            u1 = core1.units[uid]
            u2 = core2.units[uid]
            assert u1.activation == u2.activation
            assert u1.energy == u2.energy
            assert u1.trace == u2.trace


class TestObserverMetrics:
    """Phase 3.6: Observer get_metrics() 验证."""

    def test_metrics_has_required_fields(self):
        """get_metrics() 返回所有期望字段."""
        core = LifeCore(AnivaConfig(unit_count=20, seed=0))
        obs = Observer(core)
        metrics = obs.get_metrics()
        expected_fields = {
            "step", "mean_activation", "max_activation", "min_activation",
            "mean_energy", "min_energy", "mean_trace", "active_unit_ratio",
            "mean_threshold", "min_threshold", "max_threshold",
            "mean_activation_to_threshold_ratio",
        }
        assert expected_fields.issubset(metrics.keys()), (
            f"Missing fields: {expected_fields - metrics.keys()}"
        )

    def test_metrics_types_correct(self):
        """字段类型正确."""
        core = LifeCore(AnivaConfig(unit_count=20, seed=0))
        obs = Observer(core)
        metrics = obs.get_metrics()
        assert isinstance(metrics["step"], int)
        assert isinstance(metrics["mean_activation"], float)
        assert isinstance(metrics["max_activation"], float)
        assert isinstance(metrics["min_activation"], float)
        assert isinstance(metrics["mean_energy"], float)
        assert isinstance(metrics["min_energy"], float)
        assert isinstance(metrics["mean_trace"], float)
        assert isinstance(metrics["active_unit_ratio"], float)
        assert isinstance(metrics["mean_threshold"], float)
        assert isinstance(metrics["min_threshold"], float)
        assert isinstance(metrics["max_threshold"], float)
        assert isinstance(metrics["mean_activation_to_threshold_ratio"], float)

    def test_active_unit_ratio_in_range(self):
        """active_unit_ratio 在 [0, 1] 范围内."""
        core = LifeCore(AnivaConfig(unit_count=30, seed=0))
        obs = Observer(core)
        for _ in range(10):
            core.step()
        metrics = obs.get_metrics()
        assert 0.0 <= metrics["active_unit_ratio"] <= 1.0, (
            f"active_unit_ratio={metrics['active_unit_ratio']}"
        )


class TestExp1FreeRun:
    """Phase 3.6: 实验 1 自由运行."""

    def test_free_run_completes_without_error(self):
        """自由运行有限步不报错."""
        config = AnivaConfig(unit_count=10, seed=0, dt=1.0)
        result = exp1_free_run.run(config=config, total_steps=50, report_interval=100)
        assert result["total_steps"] == 50
        assert len(result["history"]) == 50
        assert "final_metrics" in result

    def test_free_run_seed_determinism(self):
        """相同 seed 的自由运行结果一致."""
        config = AnivaConfig(unit_count=10, seed=77, dt=1.0)
        r1 = exp1_free_run.run(config=config, total_steps=30, report_interval=100)
        r2 = exp1_free_run.run(config=config, total_steps=30, report_interval=100)
        for i, (m1, m2) in enumerate(zip(r1["history"], r2["history"])):
            assert m1 == m2, (
                f"Metrics diverge at step {i}: {m1} vs {m2}"
            )

    def test_free_run_default_config(self):
        """默认配置下的自由运行不报错."""
        result = exp1_free_run.run(total_steps=100, report_interval=100)
        assert result["total_steps"] == 100
        assert len(result["history"]) == 100


class TestExp1CLI:
    """Phase 3.7: 命令行接口和 CSV 导出."""

    def test_main_default_args(self):
        """默认参数下 main() 不报错."""
        exit_code = exp1_free_run.main(
            argv=["--steps", "20", "--report-interval", "100", "--unit-count", "5"]
        )
        assert exit_code == 0

    def test_main_steps_controls_total(self):
        """--steps 控制总步数（通过 run() 间接验证）."""
        result = exp1_free_run.run(
            config=AnivaConfig(unit_count=5, seed=0),
            total_steps=30,
            report_interval=100,
        )
        assert result["total_steps"] == 30
        assert len(result["history"]) == 30

    def test_csv_output_created(self):
        """--output-csv 生成 CSV 文件且行数正确."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "out.csv")
            exit_code = exp1_free_run.main(
                argv=[
                    "--steps", "50",
                    "--unit-count", "5",
                    "--report-interval", "100",
                    "--seed", "1",
                    "--output-csv", csv_path,
                ]
            )
            assert exit_code == 0
            assert os.path.exists(csv_path)
            with open(csv_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            # header + 50 data rows
            assert len(lines) == 51


class TestParameterSweep:
    """Phase 3.8: 参数扫描观测."""

    def test_sweep_runs_without_error(self):
        """参数扫描不报错."""
        results = exp1_parameter_sweep.sweep(
            noise_strengths=[0.01],
            baseline_activities=[0.05],
            synaptic_strengths=[0.05],
            seeds=[1],
            unit_count=5,
            total_steps=20,
        )
        assert len(results) == 1
        # 每个结果包含参数和指标
        row = results[0]
        for key in [
            "noise_strength", "baseline_activity", "synaptic_strength", "seed",
            "min_energy_activation_factor", "leak_rate",
            "mean_activation", "max_activation", "mean_energy", "min_energy",
            "mean_trace", "active_unit_ratio",
        ]:
            assert key in row, f"Missing key: {key}"

    def test_sweep_grid_size(self):
        """扫描网格大小 = N_noise * N_baseline * N_synaptic * N_seeds."""
        ns = [0.01, 0.02]
        ba = [0.05]
        ss = [0.05]
        seeds = [1, 2, 3]
        results = exp1_parameter_sweep.sweep(
            noise_strengths=ns,
            baseline_activities=ba,
            synaptic_strengths=ss,
            seeds=seeds,
            unit_count=5,
            total_steps=10,
        )
        assert len(results) == 2 * 1 * 1 * 3

    def test_sweep_determinism(self):
        """相同输入产生相同结果."""
        results1 = exp1_parameter_sweep.sweep(
            noise_strengths=[0.01],
            baseline_activities=[0.05],
            synaptic_strengths=[0.05],
            seeds=[1],
            unit_count=5,
            total_steps=20,
        )
        results2 = exp1_parameter_sweep.sweep(
            noise_strengths=[0.01],
            baseline_activities=[0.05],
            synaptic_strengths=[0.05],
            seeds=[1],
            unit_count=5,
            total_steps=20,
        )
        assert results1 == results2

    def test_sweep_includes_threshold_fields(self):
        """sweep 结果包含 threshold 相关字段."""
        results = exp1_parameter_sweep.sweep(
            noise_strengths=[0.01],
            baseline_activities=[0.05],
            synaptic_strengths=[0.05],
            seeds=[1],
            threshold_mins=[0.15],
            threshold_maxs=[0.35],
            unit_count=5,
            total_steps=20,
        )
        row = results[0]
        assert row["threshold_min"] == 0.15
        assert row["threshold_max"] == 0.35
        assert "mean_threshold" in row
        assert "mean_activation_to_threshold_ratio" in row


class TestEnergyGateDiagnostics:
    """Phase 3.10: energy gate 诊断扫描."""

    def test_sweep_energy_factor_values_recorded(self):
        """sweep 结果记录 min_energy_activation_factor 和 leak_rate."""
        results = exp1_parameter_sweep.sweep(
            noise_strengths=[0.01],
            baseline_activities=[0.05],
            synaptic_strengths=[0.05],
            seeds=[1],
            min_energy_activation_factors=[0.1, 0.5],
            leak_rates=[0.01],
            unit_count=5,
            total_steps=20,
        )
        assert len(results) == 2
        eaf_values = {r["min_energy_activation_factor"] for r in results}
        assert eaf_values == {0.1, 0.5}
        for r in results:
            assert r["leak_rate"] == 0.01

    def test_sweep_leak_rate_values_recorded(self):
        """sweep 结果记录不同 leak_rate."""
        results = exp1_parameter_sweep.sweep(
            noise_strengths=[0.01],
            baseline_activities=[0.05],
            synaptic_strengths=[0.05],
            seeds=[1],
            min_energy_activation_factors=[0.25],
            leak_rates=[0.0, 0.05, 0.1],
            unit_count=5,
            total_steps=20,
        )
        assert len(results) == 3
        lr_values = {r["leak_rate"] for r in results}
        assert lr_values == {0.0, 0.05, 0.1}

    def test_sweep_default_energy_factor_is_config_default(self):
        """不指定 energy_factor 时使用 AnivaConfig 默认值."""
        results = exp1_parameter_sweep.sweep(
            noise_strengths=[0.01],
            baseline_activities=[0.05],
            synaptic_strengths=[0.05],
            seeds=[1],
            unit_count=5,
            total_steps=10,
        )
        assert results[0]["min_energy_activation_factor"] == AnivaConfig.min_energy_activation_factor
        assert results[0]["leak_rate"] == AnivaConfig.leak_rate

    def test_sweep_determinism_with_new_params(self):
        """energy_factor + leak_rate 扫描也保证确定性."""
        results1 = exp1_parameter_sweep.sweep(
            noise_strengths=[0.01],
            baseline_activities=[0.05],
            synaptic_strengths=[0.05],
            seeds=[1, 2],
            min_energy_activation_factors=[0.25, 0.5],
            leak_rates=[0.01, 0.05],
            unit_count=5,
            total_steps=20,
        )
        results2 = exp1_parameter_sweep.sweep(
            noise_strengths=[0.01],
            baseline_activities=[0.05],
            synaptic_strengths=[0.05],
            seeds=[1, 2],
            min_energy_activation_factors=[0.25, 0.5],
            leak_rates=[0.01, 0.05],
            unit_count=5,
            total_steps=20,
        )
        assert results1 == results2

    def test_cli_energy_factor_arg(self):
        """CLI --energy-factor 参数传递正确."""
        import sys as _sys
        _argv_backup = _sys.argv
        try:
            _sys.argv = ["exp1_parameter_sweep.py",
                         "--energy-factor", "0.1", "0.5", "0.9",
                         "--leak-rate", "0.0",
                         "--noise", "0.01", "--baseline", "0.05",
                         "--synaptic", "0.05", "--seeds", "1",
                         "--unit-count", "5", "--steps", "10"]
            exit_code = exp1_parameter_sweep.main()
            assert exit_code == 0
        finally:
            _sys.argv = _argv_backup

    def test_cli_leak_rate_arg(self):
        """CLI --leak-rate 参数传递正确."""
        import sys as _sys
        _argv_backup = _sys.argv
        try:
            _sys.argv = ["exp1_parameter_sweep.py",
                         "--leak-rate", "0.0", "0.05", "0.1",
                         "--energy-factor", "0.25",
                         "--noise", "0.01", "--baseline", "0.05",
                         "--synaptic", "0.05", "--seeds", "1",
                         "--unit-count", "5", "--steps", "10"]
            exit_code = exp1_parameter_sweep.main()
            assert exit_code == 0
        finally:
            _sys.argv = _argv_backup

    def test_sweep_threshold_softness_values_recorded(self):
        """sweep 结果记录 threshold_softness."""
        results = exp1_parameter_sweep.sweep(
            noise_strengths=[0.01],
            baseline_activities=[0.05],
            synaptic_strengths=[0.05],
            seeds=[1],
            threshold_softnesses=[0.01, 0.05],
            unit_count=5,
            total_steps=10,
        )
        assert len(results) == 2
        ts_values = {r["threshold_softness"] for r in results}
        assert ts_values == {0.01, 0.05}

    def test_sweep_default_softness_is_config_default(self):
        """不指定 threshold_softness 时使用 AnivaConfig 默认值."""
        results = exp1_parameter_sweep.sweep(
            noise_strengths=[0.01],
            baseline_activities=[0.05],
            synaptic_strengths=[0.05],
            seeds=[1],
            unit_count=5,
            total_steps=10,
        )
        assert results[0]["threshold_softness"] == AnivaConfig.threshold_softness

    def test_cli_threshold_softness_arg(self):
        """CLI --threshold-softness 参数传递正确."""
        import sys as _sys
        _argv_backup = _sys.argv
        try:
            _sys.argv = ["exp1_parameter_sweep.py",
                         "--threshold-softness", "0.005", "0.01", "0.05",
                         "--noise", "0.01", "--baseline", "0.05",
                         "--synaptic", "0.05", "--seeds", "1",
                         "--unit-count", "5", "--steps", "10"]
            exit_code = exp1_parameter_sweep.main()
            assert exit_code == 0
        finally:
            _sys.argv = _argv_backup


class TestThresholdConfig:
    """Phase 3.9: threshold 参数暴露."""

    def test_default_threshold_range_matches_original(self):
        """默认 threshold 范围和之前硬编码一致."""
        config = AnivaConfig()
        assert config.threshold_min == 0.2
        assert config.threshold_max == 0.4

    def test_custom_threshold_range_used_in_init(self):
        """自定义 threshold 范围影响 Unit 初始化."""
        config = AnivaConfig(
            unit_count=50, seed=0,
            threshold_min=0.1, threshold_max=0.2,
        )
        core = LifeCore(config)
        for unit in core.units.values():
            assert 0.1 <= unit.threshold <= 0.2, (
                f"Unit {unit.uid} threshold={unit.threshold}"
            )

    def test_threshold_validation(self):
        """threshold 范围验证."""
        with pytest.raises(ValueError):
            AnivaConfig(threshold_min=0.5, threshold_max=0.3)

    def test_metrics_threshold_values_in_range(self):
        """get_metrics 的 threshold 指标值合法."""
        config = AnivaConfig(unit_count=20, seed=0, threshold_min=0.15, threshold_max=0.35)
        core = LifeCore(config)
        obs = Observer(core)
        metrics = obs.get_metrics()
        assert 0.15 <= metrics["mean_threshold"] <= 0.35
        assert 0.15 <= metrics["min_threshold"] <= 0.35
        assert 0.15 <= metrics["max_threshold"] <= 0.35
        assert 0.0 <= metrics["mean_activation_to_threshold_ratio"] <= 1.0


class TestObserver:
    def test_snapshot_shape(self):
        """快照返回正确的数据形状."""
        config = AnivaConfig(unit_count=20, seed=0)
        core = LifeCore(config)
        obs = Observer(core)
        snap = obs.snapshot()
        assert snap["step"] == 0
        assert len(snap["activations"]) == 20
        assert len(snap["energies"]) == 20
        assert len(snap["traces"]) == 20

    def test_snapshot_after_steps(self):
        """步进后快照的 step 值正确更新."""
        core = LifeCore(AnivaConfig(unit_count=10, seed=0))
        obs = Observer(core)
        for i in range(5):
            core.step()
        snap = obs.snapshot()
        assert snap["step"] == 5
