"""Phase 9D.1 consolidation skeleton tests — tag, capture, slow_weight."""

import math
import numpy as np
import pytest
from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.core.plasticity_consolidation import (
    produce_tags, decay_tags, compute_capture_signal,
    apply_capture, compute_effective_weights,
)


class TestConfigDefaults:
    """All consolidation fields default off/neutral."""

    def test_consolidation_disabled_by_default(self):
        cfg = AnivaConfig()
        assert cfg.consolidation_enabled is False

    def test_tag_tau_default(self):
        cfg = AnivaConfig()
        assert cfg.consolidation_tag_tau == 5000.0

    def test_capture_threshold_default(self):
        cfg = AnivaConfig()
        assert cfg.consolidation_capture_threshold == 0.5

    def test_slow_weight_max_default(self):
        cfg = AnivaConfig()
        assert cfg.consolidation_slow_weight_max == 0.1

    def test_slow_weight_rate_default(self):
        cfg = AnivaConfig()
        assert cfg.consolidation_slow_weight_rate == 0.1

    def test_capture_refractory_default(self):
        cfg = AnivaConfig()
        assert cfg.consolidation_capture_refractory_steps == 500

    def test_ledger_disabled_by_default(self):
        cfg = AnivaConfig()
        assert cfg.consolidation_ledger_enabled is False


class TestConsolidationDisabled:
    """consolidation_enabled=False → no effect on behavior."""

    def test_tag_cache_none_when_disabled(self):
        cfg = AnivaConfig(unit_count=30, seed=42)
        core = LifeCore(cfg)
        assert core._tag_cache is None
        assert core._slow_weight_cache is None

    def test_step_does_not_crash_when_disabled(self):
        cfg = AnivaConfig(unit_count=30, seed=42, plasticity_rate=0.01)
        core = LifeCore(cfg)
        for _ in range(20):
            core.step()
        # Should reach here without error
        assert core.step_count == 20

    def test_determinism_preserved_with_9d_disabled(self):
        """Two cores with same seed produce identical results (9D off)."""
        def run():
            cfg = AnivaConfig(unit_count=30, seed=99, plasticity_rate=0.01)
            core = LifeCore(cfg)
            for _ in range(30):
                core.step()
            return core._weight_cache.copy()

        r1 = run()
        r2 = run()
        assert np.allclose(r1, r2)


class TestTagProduction:
    """Tags are produced from event-pair dW."""

    def test_produce_tags_adds_absolute_dw(self):
        tag_cache = np.zeros(5, dtype=np.float64)
        dW = np.array([0.1, -0.2, 0.0, 0.05, -0.03], dtype=np.float64)
        produce_tags(tag_cache, dW)
        expected = np.abs(dW)
        assert np.allclose(tag_cache, expected)

    def test_produce_tags_accumulates(self):
        tag_cache = np.array([0.1, 0.2, 0.0], dtype=np.float64)
        dW = np.array([0.05, -0.1, 0.3], dtype=np.float64)
        produce_tags(tag_cache, dW)
        expected = np.array([0.15, 0.3, 0.3], dtype=np.float64)
        assert np.allclose(tag_cache, expected)

    def test_tag_produced_via_apply_event_pair_phi(self):
        """apply_event_pair_phi produces tags when consolidation enabled."""
        cfg = AnivaConfig(
            unit_count=50, seed=42,
            consolidation_enabled=True,
            event_pair_plasticity_enabled=True,
            event_pair_trace_tau=1000.0,
            event_pair_trace_gate_ref=0.03,
            event_pair_target_update_l1=1e-4,
        )
        core = LifeCore(cfg)
        # Set trace so gate > 0
        core._event_trace[:] = 0.01
        phi = np.ones(50, dtype=np.float64) * 0.1
        core.apply_event_pair_phi(phi)
        assert np.any(core._tag_cache > 0), "tag_cache should have non-zero entries after event-pair update"

    def test_tag_accumulates_across_updates(self):
        """Two consecutive event-pair updates → tag sum > single update."""
        cfg = AnivaConfig(
            unit_count=50, seed=42,
            consolidation_enabled=True,
            event_pair_plasticity_enabled=True,
            event_pair_trace_tau=1000.0,
            event_pair_trace_gate_ref=0.03,
            event_pair_target_update_l1=1e-4,
        )
        core = LifeCore(cfg)
        core._event_trace[:] = 0.01
        phi = np.ones(50, dtype=np.float64) * 0.1
        core.apply_event_pair_phi(phi)
        tag_after_1 = float(np.sum(core._tag_cache))

        core._event_trace[:] = 0.01
        core.apply_event_pair_phi(phi)
        tag_after_2 = float(np.sum(core._tag_cache))

        assert tag_after_2 > tag_after_1 + 1e-16, \
            f"tag should accumulate: {tag_after_2} <= {tag_after_1}"


class TestTagDecay:
    """Tags decay with correct time constant."""

    def test_decay_tags_single_step(self):
        tag_cache = np.ones(10, dtype=np.float64)
        tau = 100.0
        decay_tags(tag_cache, tau)
        expected = math.exp(-1.0 / tau)
        assert np.allclose(tag_cache, expected)

    def test_decay_tags_matches_tau(self):
        """After tau steps, tag ≈ 1/e of original."""
        tag_cache = np.ones(5, dtype=np.float64)
        tau = 50.0
        for _ in range(50):
            decay_tags(tag_cache, tau)
        expected = 1.0 / math.e
        assert np.allclose(tag_cache, expected, rtol=0.05)


class TestCaptureSignal:
    """Capture signal is computed from internal dynamics only."""

    def test_signal_zero_when_energy_zero(self):
        s = compute_capture_signal(mean_energy=0.0, trace_mass=0.03)
        assert s == 0.0

    def test_signal_saturated_when_both_high(self):
        s = compute_capture_signal(mean_energy=0.3, trace_mass=0.03)
        assert s == 1.0

    def test_signal_fractional_when_one_low(self):
        s = compute_capture_signal(mean_energy=0.15, trace_mass=0.03)
        assert s == pytest.approx(0.5, rel=0.01)

    def test_signal_pure_function(self):
        """Same inputs always give same output — no hidden state or labels."""
        s1 = compute_capture_signal(0.5, 0.02)
        s2 = compute_capture_signal(0.5, 0.02)
        assert s1 == s2

    def test_signal_uses_no_labels(self):
        """Verify compute_capture_signal source has no arm/L/R/event_index references."""
        import inspect
        src = inspect.getsource(compute_capture_signal)
        # Check only implementation lines, not docstring (which explains what's NOT used).
        forbidden_in_code = ["L_then_R", "R_then_L", "event_index", "episode", "reward", "goal"]
        for token in forbidden_in_code:
            assert token not in src, f"capture signal must not reference '{token}'"


class TestCapture:
    """Capture transfers tags to slow_weight."""

    def test_apply_capture_transfers_tags(self):
        tag = np.array([0.1, 0.2, 0.0], dtype=np.float64)
        slow = np.zeros(3, dtype=np.float64)
        delta_l1 = apply_capture(tag, slow, slow_weight_rate=0.1, slow_weight_max=0.1)
        expected_add = 0.1 * tag
        assert np.allclose(slow, expected_add)
        assert delta_l1 == pytest.approx(float(np.sum(np.abs(expected_add))))

    def test_slow_weight_clamped_by_max(self):
        tag = np.array([10.0, 5.0], dtype=np.float64)
        slow = np.array([0.08, -0.08], dtype=np.float64)
        apply_capture(tag, slow, slow_weight_rate=0.1, slow_weight_max=0.1)
        # slow[0] = 0.08 + 0.1*10 = 1.08 → clamped to 0.1
        # slow[1] = -0.08 + 0.1*5 = 0.42 → clamped to 0.1
        assert slow[0] == 0.1
        assert slow[1] == 0.1

    def test_capture_writes_tag_to_slow_weight(self):
        """Integration: _consolidation_step transfers tags when signal is high."""
        cfg = AnivaConfig(
            unit_count=50, seed=42,
            consolidation_enabled=True,
            event_pair_plasticity_enabled=True,
            consolidation_capture_threshold=0.5,
        )
        core = LifeCore(cfg)
        core._tag_cache[:] = 0.1
        core._energies[:] = 0.5
        core._event_trace[:] = 0.05
        core._capture_refractory_remaining = 0
        slow_before = core._slow_weight_cache.copy()
        core._consolidation_step()
        assert np.any(core._slow_weight_cache != slow_before), \
            "slow_weight should change when capture triggers"

    def test_refractory_prevents_repeated_capture(self):
        """After capture, refractory prevents immediate re-capture."""
        cfg = AnivaConfig(
            unit_count=50, seed=42,
            consolidation_enabled=True,
            event_pair_plasticity_enabled=True,
            consolidation_capture_refractory_steps=500,
        )
        core = LifeCore(cfg)
        core._tag_cache[:] = 0.1
        core._energies[:] = 0.5
        core._event_trace[:] = 0.05
        core._capture_refractory_remaining = 0

        core._consolidation_step()
        assert core._capture_refractory_remaining == 500
        slow_after_first = core._slow_weight_cache.copy()

        # Second call: refractory > 0 → no capture
        core._consolidation_step()
        assert core._capture_refractory_remaining == 499
        assert np.allclose(core._slow_weight_cache, slow_after_first), \
            "slow_weight should not change during refractory"


class TestEffectiveWeights:
    """Effective = fast + slow, clamped to [-1, 1]."""

    def test_effective_equals_fast_when_slow_zero(self):
        fast = np.array([0.5, -0.3, 0.8], dtype=np.float64)
        slow = np.zeros(3, dtype=np.float64)
        eff = compute_effective_weights(fast, slow)
        assert np.allclose(eff, fast)

    def test_effective_clamped_to_one(self):
        fast = np.array([0.9, -0.9], dtype=np.float64)
        slow = np.array([0.2, -0.2], dtype=np.float64)
        eff = compute_effective_weights(fast, slow)
        assert eff[0] == 1.0
        assert eff[1] == -1.0


class TestNoNaN:
    """No NaN anywhere in consolidation pipeline."""

    def test_no_nan_in_consolidation_functions(self):
        tag = np.array([0.1, 0.0, 0.2], dtype=np.float64)
        slow = np.zeros(3, dtype=np.float64)
        fast = np.array([0.5, -0.3, 0.8], dtype=np.float64)

        decay_tags(tag, 5000.0)
        assert not np.any(np.isnan(tag))

        s = compute_capture_signal(0.5, 0.02)
        assert not math.isnan(s)

        apply_capture(tag, slow, 0.1, 0.1)
        assert not np.any(np.isnan(slow))

        eff = compute_effective_weights(fast, slow)
        assert not np.any(np.isnan(eff))

    def test_no_nan_in_full_cycle(self):
        """Run simulation with consolidation + event_pair, check no NaN."""
        cfg = AnivaConfig(
            unit_count=50, seed=42,
            consolidation_enabled=True,
            event_pair_plasticity_enabled=True,
            event_pair_trace_tau=100.0,
            plasticity_rate=0.01,
        )
        core = LifeCore(cfg)
        for step_i in range(30):
            core.step()
            if step_i % 7 == 0:
                phi = core.rng.uniform(0, 1, 50).astype(np.float64)
                core.apply_event_pair_phi(phi)
            assert not np.any(np.isnan(core._tag_cache)), f"NaN in tag_cache at step {step_i}"
            assert not np.any(np.isnan(core._slow_weight_cache)), f"NaN in slow_weight at step {step_i}"
            assert not np.any(np.isnan(core._weight_cache)), f"NaN in weight_cache at step {step_i}"


class TestLedger:
    """Capture debug ledger records events."""

    def test_ledger_empty_when_disabled(self):
        cfg = AnivaConfig(
            unit_count=50, seed=42,
            consolidation_enabled=True,
            consolidation_ledger_enabled=False,
        )
        core = LifeCore(cfg)
        core._tag_cache[:] = 0.1
        core._energies[:] = 0.5
        core._event_trace[:] = 0.05
        core._capture_refractory_remaining = 0
        core._consolidation_step()
        assert len(core._consolidation_ledger) == 0

    def test_ledger_recorded_on_capture(self):
        cfg = AnivaConfig(
            unit_count=50, seed=42,
            consolidation_enabled=True,
            event_pair_plasticity_enabled=True,
            consolidation_ledger_enabled=True,
        )
        core = LifeCore(cfg)
        core._tag_cache[:] = 0.1
        core._energies[:] = 0.5
        core._event_trace[:] = 0.05
        core._capture_refractory_remaining = 0
        core._consolidation_step()
        assert len(core._consolidation_ledger) == 1
        entry = core._consolidation_ledger[0]
        assert "capture_signal" in entry
        assert "mean_energy" in entry
        assert "trace_mass_at_capture" in entry
        assert "tag_mass" in entry
        assert "slow_weight_delta_l1" in entry
        assert "n_tagged_connections" in entry
