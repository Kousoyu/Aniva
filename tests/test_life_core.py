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
        core = LifeCore(AnivaConfig(unit_count=200, seed=42))
        for uid, unit in core.units.items():
            assert unit.uid == uid
            assert 0.0 <= unit.activation <= 1.0
            assert 0.0 <= unit.energy <= 1.0
            assert 0.2 <= unit.threshold <= 0.4
            assert 0.8 <= unit.time_constant <= 1.2
            # 位置在空间半径内
            for coord in unit.position:
                assert -1.0 <= coord <= 1.0

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
    """Phase 2.5: 能量反馈——energy 反过来约束 activation."""

    def test_low_energy_suppresses_activation(self):
        """低 energy 时，activation 被压低."""
        config = AnivaConfig(
            unit_count=1,
            seed=0,
            dt=1.0,
            noise_strength=0.0,
            energy_consumption_rate=0.0,
            energy_recovery_rate=0.0,
            min_energy_activation_factor=0.25,
            baseline_activity=0.0,
            leak_rate=0.0,
        )
        core = LifeCore(config)
        unit = core.units[0]
        unit.activation = 0.8
        unit.energy = 0.1  # 低能量

        core.step()
        # energy_factor = 0.25 + 0.75 * 0.1 = 0.325
        # activation 应该从 0.8 被压到 0.8 * 0.325 = 0.26
        expected_factor = 0.25 + 0.75 * 0.1
        assert unit.activation == pytest.approx(0.8 * expected_factor), (
            f"Expected activation ~{0.8 * expected_factor}, got {unit.activation}"
        )

    def test_high_energy_preserves_activation(self):
        """高 energy 时，activation 几乎不被压制."""
        config = AnivaConfig(
            unit_count=1,
            seed=0,
            dt=1.0,
            noise_strength=0.0,
            energy_consumption_rate=0.0,
            energy_recovery_rate=0.0,
            min_energy_activation_factor=0.25,
            baseline_activity=0.0,
            leak_rate=0.0,
        )
        core = LifeCore(config)
        unit = core.units[0]
        unit.activation = 0.8
        unit.energy = 1.0

        core.step()
        # energy_factor = 0.25 + 0.75 * 1.0 = 1.0
        assert unit.activation == pytest.approx(0.8), (
            f"High energy should preserve activation, got {unit.activation}"
        )

    def test_energy_gate_does_not_push_out_of_bounds(self):
        """energy gate 不会让 activation 越界."""
        config = AnivaConfig(
            unit_count=10,
            seed=0,
            dt=1.0,
            noise_strength=0.1,
            min_energy_activation_factor=0.25,
        )
        core = LifeCore(config)
        # 强制混合极端状态
        for uid, unit in core.units.items():
            unit.activation = 1.0 if uid % 2 == 0 else 0.0
            unit.energy = 0.0 if uid % 3 == 0 else 1.0

        for _ in range(50):
            core.step()
            for unit in core.units.values():
                assert 0.0 <= unit.activation <= 1.0, (
                    f"Unit {unit.uid} activation={unit.activation} out of [0, 1]"
                )

    def test_energy_gate_seed_determinism(self):
        """加入 energy gate 后，相同 seed 仍然可复现."""
        config = AnivaConfig(
            unit_count=10,
            seed=42,
            dt=1.0,
            noise_strength=0.05,
            min_energy_activation_factor=0.25,
        )
        core1 = LifeCore(config)
        core2 = LifeCore(config)

        for _ in range(30):
            core1.step()
            core2.step()

        for uid in core1.units:
            u1 = core1.units[uid]
            u2 = core2.units[uid]
            assert u1.activation == u2.activation
            assert u1.energy == u2.energy
            assert u1.trace == u2.trace


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

    def test_source_below_threshold_no_synaptic_effect(self):
        """source 低于 threshold 时，不影响 target."""
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
        core.connections.append(Connection(cid=0, source_id=0, target_id=1, weight=0.8))
        core.units[0].activation = 0.1   # 低于 threshold
        core.units[0].threshold = 0.3
        core.units[0].energy = 1.0
        core.units[1].activation = 0.0
        core.units[1].energy = 1.0

        core.step()
        # effective_output = max(0, 0.1-0.3) = 0 → no synaptic contribution
        assert core.units[1].activation == 0.0, (
            f"Below-threshold source should not affect target, got {core.units[1].activation}"
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
        # effective_output = max(0, 0.8-0.3) = 0.5, contribution = 0.5*0.5 = 0.25
        # delta = 0.25 * 0.1 * 1.0 = 0.025
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
