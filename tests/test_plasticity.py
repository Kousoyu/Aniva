"""Plasticity 测试 — Hebbian 共活性 + 能量门控 + 遗忘."""

import math
import pytest
from aniva.config import AnivaConfig
from aniva.core.unit import Unit
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
        source = Unit(uid=0, activation=0.8, threshold=0.3, energy=0.8)
        target = Unit(uid=1, activation=0.7, threshold=0.25, energy=0.8)
        conn = Connection(cid=0, source_id=0, target_id=1, weight=0.3)
        units = {0: source, 1: target}
        connections = [conn]

        apply_plasticity(connections, units,
                         plasticity_rate=0.01,
                         threshold_softness=0.02,
                         dt=1.0)

        assert conn.weight > 0.3

    def test_coactive_inhibitory_becomes_more_inhibitory(self):
        source = Unit(uid=0, activation=0.8, threshold=0.3, energy=0.8)
        target = Unit(uid=1, activation=0.7, threshold=0.25, energy=0.8)
        conn = Connection(cid=0, source_id=0, target_id=1, weight=-0.3,
                          is_inhibitory=True)
        units = {0: source, 1: target}
        connections = [conn]

        apply_plasticity(connections, units,
                         plasticity_rate=0.01,
                         threshold_softness=0.02,
                         dt=1.0)

        assert conn.weight < -0.3

    def test_inactive_connection_decays(self):
        source = Unit(uid=0, activation=0.01, threshold=0.3, energy=0.8)
        target = Unit(uid=1, activation=0.01, threshold=0.25, energy=0.8)
        conn = Connection(cid=0, source_id=0, target_id=1, weight=0.5)
        units = {0: source, 1: target}
        connections = [conn]

        apply_plasticity(connections, units,
                         plasticity_rate=0.01,
                         threshold_softness=0.02,
                         dt=1.0)

        # Decay should reduce weight
        assert conn.weight < 0.5

    def test_low_energy_reduces_plasticity(self):
        source_high = Unit(uid=0, activation=0.8, threshold=0.3, energy=0.8)
        target_high = Unit(uid=1, activation=0.7, threshold=0.25, energy=0.8)

        source_low = Unit(uid=2, activation=0.8, threshold=0.3, energy=0.1)
        target_low = Unit(uid=3, activation=0.7, threshold=0.25, energy=0.1)

        conn_high = Connection(cid=0, source_id=0, target_id=1, weight=0.3)
        conn_low = Connection(cid=1, source_id=2, target_id=3, weight=0.3)

        apply_plasticity([conn_high], {0: source_high, 1: target_high},
                         plasticity_rate=0.01,
                         threshold_softness=0.02, dt=1.0)
        apply_plasticity([conn_low], {2: source_low, 3: target_low},
                         plasticity_rate=0.01,
                         threshold_softness=0.02, dt=1.0)

        delta_high = conn_high.weight - 0.3
        delta_low = conn_low.weight - 0.3
        assert delta_high > delta_low, (
            f"high-energy delta={delta_high} should exceed "
            f"low-energy delta={delta_low}"
        )

    def test_weight_stays_in_bounds(self):
        source = Unit(uid=0, activation=1.0, threshold=0.1, energy=1.0)
        target = Unit(uid=1, activation=1.0, threshold=0.1, energy=1.0)
        conn_exc = Connection(cid=0, source_id=0, target_id=1, weight=0.999)
        conn_inh = Connection(cid=1, source_id=0, target_id=1, weight=-0.999,
                              is_inhibitory=True)
        units = {0: source, 1: target}

        for _ in range(100):
            apply_plasticity([conn_exc, conn_inh], units,
                             plasticity_rate=0.1,
                             threshold_softness=0.02, dt=1.0)

        assert -1.0 <= conn_exc.weight <= 1.0
        assert -1.0 <= conn_inh.weight <= 1.0

    def test_plasticity_determinism(self):
        def run():
            source = Unit(uid=0, activation=0.6, threshold=0.3, energy=0.7)
            target = Unit(uid=1, activation=0.5, threshold=0.25, energy=0.7)
            conn = Connection(cid=0, source_id=0, target_id=1, weight=0.3)
            apply_plasticity([conn], {0: source, 1: target},
                             plasticity_rate=0.01,
                             threshold_softness=0.02, dt=1.0)
            return conn.weight

        assert run() == pytest.approx(run())

    def test_decay_never_reverses_weight_sign(self):
        """衰减应向零趋近，不会翻转符号。"""
        source = Unit(uid=0, activation=0.01, threshold=0.3, energy=0.8)
        target = Unit(uid=1, activation=0.01, threshold=0.25, energy=0.8)
        conn_exc = Connection(cid=0, source_id=0, target_id=1, weight=0.001)
        conn_inh = Connection(cid=1, source_id=0, target_id=1, weight=-0.001,
                              is_inhibitory=True)
        units = {0: source, 1: target}
        connections = [conn_exc, conn_inh]

        for _ in range(100):
            apply_plasticity(connections, units,
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
            groups=["A_L", "A_R", "B", "C", "D", "F"],
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
