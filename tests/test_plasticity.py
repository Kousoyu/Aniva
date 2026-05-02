"""Plasticity 测试 — Hebbian 共活性 + 能量门控 + 遗忘."""

import math
import numpy as np
import pytest
from aniva.config import AnivaConfig
from aniva.core.connection import Connection
from aniva.core.plasticity import apply_plasticity, _output_strength
from aniva.life_core import LifeCore


class TestOutputStrength:
    """连续输出强度测试."""

    def test_below_threshold_produces_small_positive(self):
        s = _output_strength(activation=0.1, threshold=0.3, softness=0.02)
        assert s > 0.0
        assert s < 0.01  # far below threshold → nearly zero

    def test_at_threshold_is_mid_range(self):
        s = _output_strength(activation=0.3, threshold=0.3, softness=0.02)
        # sigmoid(0) = 0.5, so output ≈ 0.3 * 0.5 = 0.15
        assert s == pytest.approx(0.15, abs=0.01)

    def test_above_threshold_approaches_activation(self):
        s = _output_strength(activation=0.8, threshold=0.3, softness=0.02)
        assert s > 0.7  # close to activation

    def test_output_never_exceeds_activation(self):
        for act in [0.0, 0.2, 0.5, 0.8, 1.0]:
            s = _output_strength(act, threshold=0.3, softness=0.02)
            assert s <= act + 1e-12

    def test_continuous_no_hard_cutoff(self):
        """连续过渡：activation 微小变化 → output 微小变化（无硬跳变）。"""
        s1 = _output_strength(0.29, 0.3, 0.02)
        s2 = _output_strength(0.30, 0.3, 0.02)
        s3 = _output_strength(0.31, 0.3, 0.02)
        assert s1 < s2 < s3
        assert s2 - s1 < 0.1  # small continuous change, not a jump


class TestApplyPlasticity:
    """apply_plasticity 单元测试."""

    def test_coactive_excitatory_strengthens(self):
        conn = Connection(cid=0, source_id=0, target_id=1, weight=0.3)
        acts = np.array([0.8, 0.7], dtype=np.float64)
        thrs = np.array([0.3, 0.25], dtype=np.float64)
        engs = np.array([0.8, 0.8], dtype=np.float64)

        apply_plasticity([conn], acts, thrs, engs,
                         plasticity_rate=0.01,
                         threshold_softness=0.02,
                         dt=1.0)

        assert conn.weight > 0.3

    def test_coactive_inhibitory_becomes_more_inhibitory(self):
        conn = Connection(cid=0, source_id=0, target_id=1, weight=-0.3,
                          is_inhibitory=True)
        acts = np.array([0.8, 0.7], dtype=np.float64)
        thrs = np.array([0.3, 0.25], dtype=np.float64)
        engs = np.array([0.8, 0.8], dtype=np.float64)

        apply_plasticity([conn], acts, thrs, engs,
                         plasticity_rate=0.01,
                         threshold_softness=0.02,
                         dt=1.0)

        assert conn.weight < -0.3

    def test_inactive_connection_decays(self):
        conn = Connection(cid=0, source_id=0, target_id=1, weight=0.5)
        acts = np.array([0.01, 0.01], dtype=np.float64)
        thrs = np.array([0.3, 0.25], dtype=np.float64)
        engs = np.array([0.8, 0.8], dtype=np.float64)

        apply_plasticity([conn], acts, thrs, engs,
                         plasticity_rate=0.01,
                         threshold_softness=0.02,
                         dt=1.0)

        # Decay should reduce weight
        assert conn.weight < 0.5

    def test_low_energy_reduces_plasticity(self):
        acts = np.array([0.8, 0.7, 0.8, 0.7], dtype=np.float64)
        thrs = np.array([0.3, 0.25, 0.3, 0.25], dtype=np.float64)
        engs = np.array([0.8, 0.8, 0.1, 0.1], dtype=np.float64)

        conn_high = Connection(cid=0, source_id=0, target_id=1, weight=0.3)
        conn_low = Connection(cid=1, source_id=2, target_id=3, weight=0.3)

        apply_plasticity([conn_high], acts, thrs, engs,
                         plasticity_rate=0.01,
                         threshold_softness=0.02, dt=1.0)
        apply_plasticity([conn_low], acts, thrs, engs,
                         plasticity_rate=0.01,
                         threshold_softness=0.02, dt=1.0)

        delta_high = conn_high.weight - 0.3
        delta_low = conn_low.weight - 0.3
        assert delta_high > delta_low, (
            f"high-energy delta={delta_high} should exceed "
            f"low-energy delta={delta_low}"
        )

    def test_weight_stays_in_bounds(self):
        conn_exc = Connection(cid=0, source_id=0, target_id=1, weight=0.999)
        conn_inh = Connection(cid=1, source_id=0, target_id=1, weight=-0.999,
                              is_inhibitory=True)
        acts = np.array([1.0, 1.0], dtype=np.float64)
        thrs = np.array([0.1, 0.1], dtype=np.float64)
        engs = np.array([1.0, 1.0], dtype=np.float64)

        for _ in range(100):
            apply_plasticity([conn_exc, conn_inh], acts, thrs, engs,
                             plasticity_rate=0.1,
                             threshold_softness=0.02, dt=1.0)

        assert -1.0 <= conn_exc.weight <= 1.0
        assert -1.0 <= conn_inh.weight <= 1.0

    def test_plasticity_determinism(self):
        def run():
            conn = Connection(cid=0, source_id=0, target_id=1, weight=0.3)
            acts = np.array([0.6, 0.5], dtype=np.float64)
            thrs = np.array([0.3, 0.25], dtype=np.float64)
            engs = np.array([0.7, 0.7], dtype=np.float64)
            apply_plasticity([conn], acts, thrs, engs,
                             plasticity_rate=0.01,
                             threshold_softness=0.02, dt=1.0)
            return conn.weight

        assert run() == pytest.approx(run())

    def test_decay_never_reverses_weight_sign(self):
        """衰减应向零趋近，不会翻转符号。"""
        conn_exc = Connection(cid=0, source_id=0, target_id=1, weight=0.001)
        conn_inh = Connection(cid=1, source_id=0, target_id=1, weight=-0.001,
                              is_inhibitory=True)
        acts = np.array([0.01, 0.01], dtype=np.float64)
        thrs = np.array([0.3, 0.25], dtype=np.float64)
        engs = np.array([0.8, 0.8], dtype=np.float64)
        connections = [conn_exc, conn_inh]

        for _ in range(100):
            apply_plasticity(connections, acts, thrs, engs,
                             plasticity_rate=0.1,
                             threshold_softness=0.02, dt=1.0)

        # Should decay toward zero but not cross it
        assert conn_exc.weight >= 0.0
        assert conn_inh.weight <= 0.0


class TestPlasticityIntegration:
    """Plasticity 与 LifeCore 集成测试."""

    def test_step_applies_plasticity(self):
        """确认 LifeCore.step() 会执行 plasticity（权重会变）。"""
        cfg = AnivaConfig(
            unit_count=100, seed=42,
            plasticity_rate=0.01,  # faster for test
            synaptic_strength=0.30,
        )
        core = LifeCore(cfg)
        weights_before = [c.weight for c in core.connections]

        # Run enough steps for plasticity to take effect
        for _ in range(50):
            core.step()

        weights_after = [c.weight for c in core.connections]

        # Some weights should have changed
        diffs = [abs(a - b) for a, b in zip(weights_before, weights_after)]
        assert max(diffs) > 0.0, "plasticity should change connection weights"

    def test_plasticity_keeps_weights_in_bounds(self):
        cfg = AnivaConfig(
            unit_count=50, seed=42,
            plasticity_rate=0.01,
            synaptic_strength=0.30,
        )
        core = LifeCore(cfg)

        for _ in range(200):
            core.step()

        for conn in core.connections:
            assert -1.0 <= conn.weight <= 1.0, (
                f"weight {conn.weight} out of bounds after plasticity"
            )

    def test_plasticity_determinism_with_lifecore(self):
        cfg = AnivaConfig(
            unit_count=30, seed=99,
            plasticity_rate=0.01,
            synaptic_strength=0.30,
        )
        core_a = LifeCore(cfg)
        core_b = LifeCore(cfg)

        for _ in range(50):
            core_a.step()
            core_b.step()

        weights_a = [c.weight for c in core_a.connections]
        weights_b = [c.weight for c in core_b.connections]
        assert weights_a == pytest.approx(weights_b)

    def test_no_plasticity_with_zero_rate(self):
        """plasticity_rate=0 时权重应不变。"""
        cfg = AnivaConfig(
            unit_count=50, seed=42,
            plasticity_rate=0.0,
            synaptic_strength=0.30,
        )
        core = LifeCore(cfg)
        weights_before = [c.weight for c in core.connections]

        for _ in range(50):
            core.step()

        weights_after = [c.weight for c in core.connections]
        assert weights_before == pytest.approx(weights_after)


class TestExp5HistoryBifurcation:
    """实验 5 集成测试."""

    def test_run_two_groups_completes(self):
        from aniva.experiments.exp5_history_bifurcation import run_experiment
        from aniva.config import AnivaConfig
        cfg = AnivaConfig(unit_count=30, seed=42)
        result = run_experiment(
            config=cfg, total_steps=100,
            snapshot_interval=50,
            groups=["A_L", "B"],
        )
        assert "A_L" in result["groups"]
        assert "B" in result["groups"]
        assert len(result["groups"]["A_L"]["snapshots"]) >= 2

    def test_snapshots_have_required_fields(self):
        from aniva.experiments.exp5_history_bifurcation import run_experiment
        from aniva.config import AnivaConfig
        cfg = AnivaConfig(unit_count=30, seed=42)
        result = run_experiment(
            config=cfg, total_steps=100,
            snapshot_interval=50,
            groups=["A_L"],
        )
        snap = result["groups"]["A_L"]["snapshots"][-1]
        required = [
            "step", "mean_activation", "mean_energy",
            "hard_active_ratio", "strong_output_ratio",
            "activation_entropy", "weight_mean", "weight_std",
            "weight_abs_mean",
        ]
        for key in required:
            assert key in snap, f"missing field: {key}"

    def test_divergence_computed_for_available_pairs(self):
        from aniva.experiments.exp5_history_bifurcation import run_experiment
        from aniva.config import AnivaConfig
        cfg = AnivaConfig(unit_count=30, seed=42)
        result = run_experiment(
            config=cfg, total_steps=200,
            snapshot_interval=100,
            groups=["A_L", "A_R", "B"],
        )
        assert "A_L_vs_A_R" in result["divergence"]
        assert "A_L_vs_B" in result["divergence"]
        assert "final_weight_l1" in result["divergence"]["A_L_vs_A_R"]

    def test_verdict_has_expected_keys(self):
        from aniva.experiments.exp5_history_bifurcation import run_experiment
        from aniva.config import AnivaConfig
        cfg = AnivaConfig(unit_count=30, seed=42)
        result = run_experiment(
            config=cfg, total_steps=200,
            snapshot_interval=100,
            groups=["A_L", "A_R", "B", "C", "D_L", "F"],
        )
        v = result["verdict"]
        assert "repeatability" in v
        assert "plasticity_causal" in v
        assert "long_term_deposition" in v
        assert "structural_bifurcation" in v

    def test_determinism(self):
        from aniva.experiments.exp5_history_bifurcation import run_experiment
        from aniva.config import AnivaConfig

        def run_once():
            cfg = AnivaConfig(unit_count=30, seed=77)
            return run_experiment(
                config=cfg, total_steps=100,
                snapshot_interval=50,
                groups=["A_L", "B"],
            )

        r1 = run_once()
        r2 = run_once()

        w1 = r1["groups"]["A_L"]["weights_final"]
        w2 = r2["groups"]["A_L"]["weights_final"]
        assert w1 == pytest.approx(w2)

    def test_cli_runs(self):
        import sys
        from io import StringIO
        from aniva.experiments.exp5_history_bifurcation import main

        old_stdout = sys.stdout
        try:
            sys.stdout = StringIO()
            exit_code = main([
                "--steps", "100",
                "--seed", "42",
                "--unit-count", "30",
                "--snapshot-interval", "50",
                "--groups", "A_L", "B",
            ])
            assert exit_code == 0
        finally:
            sys.stdout = old_stdout

    def test_weight_bounds_after_experiment(self):
        from aniva.experiments.exp5_history_bifurcation import run_experiment
        from aniva.config import AnivaConfig
        cfg = AnivaConfig(unit_count=30, seed=42,
                          plasticity_rate=0.01)
        result = run_experiment(
            config=cfg, total_steps=100,
            snapshot_interval=50,
            groups=["A_L"],
        )
        w = result["groups"]["A_L"]["weights_final"]
        assert all((-1.0 <= wi <= 1.0) for wi in w)

    def test_csv_output_creates_file(self, tmp_path):
        import sys
        from io import StringIO
        from aniva.experiments.exp5_history_bifurcation import main

        csv_path = tmp_path / "exp5.csv"
        old_stdout = sys.stdout
        try:
            sys.stdout = StringIO()
            exit_code = main([
                "--steps", "100",
                "--seed", "42",
                "--unit-count", "30",
                "--snapshot-interval", "50",
                "--groups", "A_L", "B",
                "--output-csv", str(csv_path),
            ])
            assert exit_code == 0
        finally:
            sys.stdout = old_stdout
        assert csv_path.exists()

    def test_activation_entropy_in_range(self):
        from aniva.experiments.exp5_history_bifurcation import run_experiment
        from aniva.config import AnivaConfig
        cfg = AnivaConfig(unit_count=30, seed=42)
        result = run_experiment(
            config=cfg, total_steps=100,
            snapshot_interval=50,
            groups=["A_L"],
        )
        for snap in result["groups"]["A_L"]["snapshots"]:
            ent = snap["activation_entropy"]
            assert ent >= 0.0, f"entropy should be >= 0, got {ent}"
            # max entropy for 20 bins ≈ log(20) ≈ 2.996
            assert ent <= 3.0, f"entropy should be <= log(20) ≈ 3.0, got {ent}"

    def test_same_stimulus_group_determinism(self):
        """A_L 和 C 是相同刺激组，应接近但不强制 bit-perfect。"""
        from aniva.experiments.exp5_history_bifurcation import run_experiment
        from aniva.config import AnivaConfig
        cfg = AnivaConfig(unit_count=30, seed=42)
        result = run_experiment(
            config=cfg, total_steps=100,
            snapshot_interval=50,
            groups=["A_L", "C"],
        )
        # Same stimuli, same seed → should be identical
        al_w = result["groups"]["A_L"]["weights_final"]
        c_w = result["groups"]["C"]["weights_final"]
        assert al_w == pytest.approx(c_w)


    def test_propagates_homeostasis_config_to_run_group(self):
        """regression: _run_group 必须透传 homeostasis 配置，不能丢失。"""
        from aniva.experiments.exp5_history_bifurcation import run_experiment
        from aniva.config import AnivaConfig
        cfg = AnivaConfig(
            unit_count=30, seed=42,
            plasticity_rate=0.0001,
            homeostasis_enabled=True,
            homeostatic_target_abs_weight=0.30,
            homeostatic_rate=1.0,
        )
        result = run_experiment(
            config=cfg, total_steps=50,
            snapshot_interval=50,
            groups=["A_L"],
        )
        g = result["groups"]["A_L"]
        assert g["homeostasis_enabled"] is True, (
            "homeostasis_enabled should propagate to _run_group"
        )
        assert g["homeostatic_target_abs_weight"] == 0.30
        assert g["homeostatic_rate"] == 1.0


class TestHomeostasis:
    """Homeostatic maintenance 测试."""

    def test_homeostasis_off_preserves_old_behavior(self):
        """homeostasis_enabled=False 时行为与之前一致。"""
        cfg = AnivaConfig(
            unit_count=50, seed=42,
            plasticity_rate=0.01,
            homeostasis_enabled=False,
        )
        core = LifeCore(cfg)
        for _ in range(50):
            core.step()
        abs_weights = [abs(c.weight) for c in core.connections]
        assert sum(abs_weights) / len(abs_weights) < 0.5  # decay has reduced

    def test_homeostasis_on_pulls_toward_target(self):
        """homeostasis_enabled=True 时 weight_abs_mean 向 target 靠拢。"""
        cfg = AnivaConfig(
            unit_count=50, seed=42,
            plasticity_rate=0.01,
            homeostasis_enabled=True,
            homeostatic_target_abs_weight=0.30,
            homeostatic_rate=1.0,
        )
        core = LifeCore(cfg)
        for _ in range(100):
            core.step()
        abs_weights = [abs(c.weight) for c in core.connections]
        current_mean = sum(abs_weights) / len(abs_weights)
        # With rate=1.0, should stay at or near target
        assert current_mean >= 0.25, (
            f"weight_abs_mean={current_mean} below expected range"
        )

    def test_homeostasis_does_not_flip_weight_sign(self):
        """稳态缩放不应翻转权重符号。"""
        cfg = AnivaConfig(
            unit_count=50, seed=42,
            plasticity_rate=0.05,
            homeostasis_enabled=True,
            homeostatic_target_abs_weight=0.30,
            homeostatic_rate=1.0,
        )
        core = LifeCore(cfg)
        signs_before = [1 if c.weight >= 0 else -1 for c in core.connections]
        for _ in range(50):
            core.step()
        signs_after = [1 if c.weight >= 0 else -1 for c in core.connections]
        assert signs_before == signs_after

    def test_homeostasis_keeps_weights_in_bounds(self):
        """稳态缩放不破坏权重边界 [-1, 1]。"""
        cfg = AnivaConfig(
            unit_count=50, seed=42,
            plasticity_rate=0.01,
            homeostasis_enabled=True,
            homeostatic_target_abs_weight=0.30,
            homeostatic_rate=1.0,
        )
        core = LifeCore(cfg)
        for _ in range(200):
            core.step()
        for conn in core.connections:
            assert -1.0 <= conn.weight <= 1.0

    def test_homeostasis_determinism(self):
        """稳态缩放应完全确定性。"""
        def run():
            cfg = AnivaConfig(
                unit_count=30, seed=99,
                plasticity_rate=0.01,
                homeostasis_enabled=True,
                homeostatic_target_abs_weight=0.30,
                homeostatic_rate=1.0,
            )
            core = LifeCore(cfg)
            for _ in range(50):
                core.step()
            return [c.weight for c in core.connections]

        assert run() == pytest.approx(run())

    def test_homeostasis_noop_when_above_target(self):
        """weight_abs_mean 高于 target 时不强制压低。"""
        cfg = AnivaConfig(
            unit_count=30, seed=42,
            plasticity_rate=0.0,  # no decay
            homeostasis_enabled=True,
            homeostatic_target_abs_weight=0.05,  # very low target
            homeostatic_rate=1.0,
        )
        core = LifeCore(cfg)
        initial_mean = sum(abs(c.weight) for c in core.connections) / len(core.connections)
        assert initial_mean > 0.05  # weights start high
        for _ in range(20):
            core.step()
        final_mean = sum(abs(c.weight) for c in core.connections) / len(core.connections)
        # With plasticity_rate=0 and low target, should not be forcibly lowered
        assert final_mean == pytest.approx(initial_mean)
