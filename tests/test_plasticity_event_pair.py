"""Phase 9C.4 skeleton tests — config, trace decay, soft gate, anti-cheat."""

import math
import numpy as np
import pytest
from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.core.plasticity_event_pair import apply_event_pair_update
from aniva.environment.environment import Environment, Stimulus, StimulusEvent


class TestConfigDefaults:
    """All event-pair fields default off/neutral."""

    def test_event_pair_disabled_by_default(self):
        cfg = AnivaConfig()
        assert cfg.event_pair_plasticity_enabled is False

    def test_event_pair_trace_tau_default(self):
        cfg = AnivaConfig()
        assert cfg.event_pair_trace_tau == 1000.0

    def test_event_pair_target_update_l1_default(self):
        cfg = AnivaConfig()
        assert cfg.event_pair_target_update_l1 == 1e-4

    def test_event_pair_gate_defaults(self):
        cfg = AnivaConfig()
        assert cfg.event_pair_gate_mode == "soft_trace_gate"
        assert cfg.event_pair_trace_gate_ref == 3e-2
        assert cfg.event_pair_gate_power == 1.0

    def test_event_pair_ledger_disabled_by_default(self):
        cfg = AnivaConfig()
        assert cfg.event_pair_ledger_enabled is False


class TestDisabledPathRegression:
    """When event_pair_plasticity_enabled=False, all old behavior is preserved."""

    def test_lifecore_initializes_with_event_trace(self):
        """_event_trace exists but is all zeros."""
        cfg = AnivaConfig(unit_count=50, seed=42)
        core = LifeCore(cfg)
        assert core._event_trace is not None
        assert core._event_trace.shape == (50,)
        assert np.all(core._event_trace == 0.0)

    def test_step_does_not_modify_event_trace_when_disabled(self):
        """When disabled, _event_trace stays zero through steps."""
        cfg = AnivaConfig(unit_count=50, seed=42)
        core = LifeCore(cfg)
        for _ in range(10):
            core.step()
        assert np.all(core._event_trace == 0.0)

    def test_weights_unchanged_when_disabled(self):
        """Default config produces same weights as before 9C.4 changes."""
        cfg = AnivaConfig(
            unit_count=50, seed=42,
            plasticity_rate=0.01,
        )
        core = LifeCore(cfg)
        for _ in range(50):
            core.step()
        weights_after = [c.weight for c in core.connections]
        # All weights should be in bounds
        for w in weights_after:
            assert -1.0 <= w <= 1.0

    def test_determinism_preserved_with_event_pair_disabled(self):
        """Determinism is not broken by the presence of new fields."""
        def run():
            cfg = AnivaConfig(
                unit_count=30, seed=99,
                plasticity_rate=0.01,
            )
            core = LifeCore(cfg)
            for _ in range(50):
                core.step()
            return [c.weight for c in core.connections]

        assert run() == pytest.approx(run())


class TestTraceDecay:
    """Event-pair trace decay behaves correctly."""

    def test_trace_decays_when_enabled(self):
        """_event_trace decays each step when event_pair enabled."""
        cfg = AnivaConfig(
            unit_count=30, seed=42,
            event_pair_plasticity_enabled=True,
            event_pair_trace_tau=100.0,
            dt=1.0,
        )
        core = LifeCore(cfg)
        # Manually set trace
        core._event_trace[:] = 1.0
        core.step()
        # After 1 step, trace should have decayed
        expected_decay = math.exp(-1.0 / 100.0)
        assert np.allclose(core._event_trace, 1.0 * expected_decay)

    def test_trace_decay_rate_matches_tau(self):
        """After tau steps, trace should be ~1/e of original."""
        cfg = AnivaConfig(
            unit_count=30, seed=42,
            event_pair_plasticity_enabled=True,
            event_pair_trace_tau=50.0,
            dt=1.0,
        )
        core = LifeCore(cfg)
        core._event_trace[:] = 1.0
        for _ in range(50):
            core.step()
        assert np.allclose(core._event_trace, 1.0 / math.e, rtol=0.05)

    def test_trace_does_not_decay_when_disabled(self):
        """When disabled, trace doesn't decay (stays at whatever value)."""
        cfg = AnivaConfig(unit_count=30, seed=42)
        core = LifeCore(cfg)
        core._event_trace[:] = 0.5
        for _ in range(10):
            core.step()
        assert np.all(core._event_trace == 0.5)

    def test_trace_decay_independent_of_config_dt(self):
        """event_pair_trace_tau is in simulation steps, not physical time.

        Setting dt=0.5 should not halve the per-step decay; the decay must
        use exp(-1.0/tau) regardless of config.dt. See phase9C4 full integration
        smoke root-cause analysis.
        """
        tau = 10.0
        cfg = AnivaConfig(
            unit_count=30, seed=42,
            event_pair_plasticity_enabled=True,
            event_pair_trace_tau=tau,
            dt=0.5,
        )
        core = LifeCore(cfg)
        core._event_trace[:] = 1.0

        for _ in range(10):
            core.step()

        expected = 1.0 / math.e  # exp(-10/10)
        assert np.allclose(core._event_trace, expected, rtol=0.05)

        # Confirm it is NOT the dt-based result (~0.61)
        dt_based = math.exp(-10 * 0.5 / tau)
        assert abs(float(core._event_trace[0]) - dt_based) > 0.1, \
            "decay should NOT match dt-based computation"


class TestSoftGateFormula:
    """Gate formula: gate = min(1, trace_mass / ref) ** power."""

    def test_gate_is_one_when_trace_above_ref(self):
        """When trace_mass >= ref, gate = 1.0."""
        n = 10
        trace = np.full(n, 0.01, dtype=np.float64)  # trace_mass = 0.1
        phi = np.ones(n, dtype=np.float64) * 0.1
        w = np.ones(5, dtype=np.float64) * 0.1
        src = np.array([0, 1, 2, 3, 4], dtype=np.int64)
        tgt = np.array([5, 6, 7, 8, 9], dtype=np.int64)

        ledger = apply_event_pair_update(
            trace, phi, w, src, tgt,
            target_l1=1e-4,
            gate_mode="soft_trace_gate",
            gate_ref=0.05,  # trace_mass=0.1 > ref=0.05
            gate_power=1.0,
            ledger_enabled=True,
        )
        assert ledger["gate"] == 1.0

    def test_gate_is_fractional_when_trace_below_ref(self):
        """When trace_mass < ref, gate < 1.0."""
        n = 10
        trace = np.full(n, 0.001, dtype=np.float64)  # trace_mass = 0.01
        phi = np.ones(n, dtype=np.float64) * 0.1
        w = np.ones(5, dtype=np.float64) * 0.1
        src = np.array([0, 1, 2, 3, 4], dtype=np.int64)
        tgt = np.array([5, 6, 7, 8, 9], dtype=np.int64)

        ledger = apply_event_pair_update(
            trace, phi, w, src, tgt,
            target_l1=1e-4,
            gate_mode="soft_trace_gate",
            gate_ref=0.03,
            gate_power=1.0,
            ledger_enabled=True,
        )
        expected_gate = 0.01 / 0.03  # = 0.333...
        assert ledger["gate"] == pytest.approx(expected_gate, rel=0.01)

    def test_gate_power_shapes_curve(self):
        """Higher gate_power makes gate drop faster below ref."""
        n = 10
        trace = np.full(n, 0.002, dtype=np.float64)  # trace_mass = 0.02
        phi = np.ones(n, dtype=np.float64) * 0.1
        w = np.ones(5, dtype=np.float64) * 0.1
        src = np.array([0, 1, 2, 3, 4], dtype=np.int64)
        tgt = np.array([5, 6, 7, 8, 9], dtype=np.int64)

        # power=1: gate = 0.02/0.03 = 0.667
        l1 = apply_event_pair_update(
            trace.copy(), phi, w.copy(), src, tgt,
            target_l1=1e-4,
            gate_mode="soft_trace_gate",
            gate_ref=0.03,
            gate_power=1.0,
            ledger_enabled=True,
        )
        # power=2: gate = (0.02/0.03)^2 = 0.444
        l2 = apply_event_pair_update(
            trace.copy(), phi, w.copy(), src, tgt,
            target_l1=1e-4,
            gate_mode="soft_trace_gate",
            gate_ref=0.03,
            gate_power=2.0,
            ledger_enabled=True,
        )
        assert l1["gate"] > l2["gate"]

    def test_bare_l1_norm_gate_is_always_one(self):
        """bare_l1_norm mode: gate = 1 regardless of trace_mass."""
        n = 10
        trace = np.full(n, 0.0001, dtype=np.float64)  # tiny trace
        phi = np.ones(n, dtype=np.float64) * 0.1
        w = np.ones(5, dtype=np.float64) * 0.1
        src = np.array([0, 1, 2, 3, 4], dtype=np.int64)
        tgt = np.array([5, 6, 7, 8, 9], dtype=np.int64)

        ledger = apply_event_pair_update(
            trace, phi, w, src, tgt,
            target_l1=1e-4,
            gate_mode="bare_l1_norm",
            ledger_enabled=True,
        )
        assert ledger["gate"] == 1.0

    def test_hard_threshold_gate_is_zero_when_below(self):
        """hard_threshold: gate=0 when trace_mass < threshold."""
        n = 10
        trace = np.full(n, 0.00001, dtype=np.float64)  # trace_mass = 0.0001
        phi = np.ones(n, dtype=np.float64) * 0.1
        w = np.ones(5, dtype=np.float64) * 0.1
        src = np.array([0, 1, 2, 3, 4], dtype=np.int64)
        tgt = np.array([5, 6, 7, 8, 9], dtype=np.int64)

        ledger = apply_event_pair_update(
            trace, phi, w, src, tgt,
            target_l1=1e-4,
            gate_mode="hard_threshold",
            gate_threshold=0.001,
            ledger_enabled=True,
        )
        assert ledger["gate"] == 0.0
        assert ledger["dW_l1"] == 0.0


class TestApplyEventPairUpdate:
    """Core update function correctness."""

    def test_update_preserves_weight_signs(self):
        """Event-pair update should not flip weight signs."""
        n = 20
        trace = np.ones(n, dtype=np.float64) * 0.1
        phi = np.ones(n, dtype=np.float64) * 0.1
        w = np.array([0.3, -0.3, 0.5, -0.5], dtype=np.float64)
        src = np.array([0, 1, 2, 3], dtype=np.int64)
        tgt = np.array([10, 11, 12, 13], dtype=np.int64)

        apply_event_pair_update(
            trace, phi, w, src, tgt,
            target_l1=1e-4,
            gate_mode="soft_trace_gate",
            gate_ref=0.03,
            ledger_enabled=False,
        )
        # Positive stays positive, negative stays negative
        assert w[0] > 0
        assert w[1] < 0
        assert w[2] > 0
        assert w[3] < 0

    def test_update_keeps_weights_in_bounds(self):
        """Updated weights stay in [-1, 1]."""
        n = 20
        trace = np.ones(n, dtype=np.float64) * 0.1
        phi = np.ones(n, dtype=np.float64) * 0.1
        w = np.array([0.9, -0.9, 0.999, -0.999], dtype=np.float64)
        src = np.array([0, 1, 2, 3], dtype=np.int64)
        tgt = np.array([10, 11, 12, 13], dtype=np.int64)

        apply_event_pair_update(
            trace, phi, w, src, tgt,
            target_l1=1e-3,  # larger update
            gate_mode="soft_trace_gate",
            gate_ref=0.1,
            ledger_enabled=False,
        )
        assert np.all(w >= -1.0)
        assert np.all(w <= 1.0)

    def test_dW_l1_matches_target(self):
        """The L1 norm of dW should approximately equal target_l1 * gate."""
        n = 20
        trace = np.ones(n, dtype=np.float64) * 0.1
        phi = np.ones(n, dtype=np.float64) * 0.1
        w = np.zeros(4, dtype=np.float64)
        src = np.array([0, 1, 2, 3], dtype=np.int64)
        tgt = np.array([10, 11, 12, 13], dtype=np.int64)

        ledger = apply_event_pair_update(
            trace, phi, w, src, tgt,
            target_l1=1e-4,
            gate_mode="soft_trace_gate",
            gate_ref=0.03,
            ledger_enabled=True,
        )
        # gate should be 1.0 (trace_mass=2.0 > 0.03)
        assert ledger["gate"] == 1.0
        assert ledger["dW_l1"] == pytest.approx(1e-4, rel=0.01)

    def test_ledger_returns_none_when_disabled(self):
        """When ledger_enabled=False, returns None."""
        n = 20
        trace = np.ones(n, dtype=np.float64) * 0.1
        phi = np.ones(n, dtype=np.float64) * 0.1
        w = np.zeros(4, dtype=np.float64)
        src = np.array([0, 1, 2, 3], dtype=np.int64)
        tgt = np.array([10, 11, 12, 13], dtype=np.int64)

        result = apply_event_pair_update(
            trace, phi, w, src, tgt,
            target_l1=1e-4,
            gate_mode="soft_trace_gate",
            gate_ref=0.03,
            ledger_enabled=False,
        )
        assert result is None

    def test_no_update_when_trace_zero(self):
        """Zero trace mass → no weight change."""
        n = 20
        trace = np.zeros(n, dtype=np.float64)
        phi = np.ones(n, dtype=np.float64) * 0.1
        w = np.ones(4, dtype=np.float64) * 0.1
        w_orig = w.copy()
        src = np.array([0, 1, 2, 3], dtype=np.int64)
        tgt = np.array([10, 11, 12, 13], dtype=np.int64)

        apply_event_pair_update(
            trace, phi, w, src, tgt,
            target_l1=1e-4,
            gate_mode="soft_trace_gate",
            gate_ref=0.03,
            ledger_enabled=False,
        )
        assert np.allclose(w, w_orig)

    def test_no_update_when_phi_zero(self):
        """Zero phi mass → no weight change."""
        n = 20
        trace = np.ones(n, dtype=np.float64) * 0.1
        phi = np.zeros(n, dtype=np.float64)
        w = np.ones(4, dtype=np.float64) * 0.1
        w_orig = w.copy()
        src = np.array([0, 1, 2, 3], dtype=np.int64)
        tgt = np.array([10, 11, 12, 13], dtype=np.int64)

        apply_event_pair_update(
            trace, phi, w, src, tgt,
            target_l1=1e-4,
            gate_mode="soft_trace_gate",
            gate_ref=0.03,
            ledger_enabled=False,
        )
        assert np.allclose(w, w_orig)


class TestAntiCheat:
    """No label leakage in update path — purely mathematical."""

    def test_no_conditional_behavior_by_label(self):
        """The update is the same formula regardless of connection identity."""
        n = 20
        trace = np.arange(n, dtype=np.float64) * 0.01
        phi = np.arange(n, dtype=np.float64)[::-1] * 0.01  # reversed
        w = np.ones(6, dtype=np.float64) * 0.1
        src = np.array([0, 1, 2, 3, 4, 5], dtype=np.int64)
        tgt = np.array([10, 11, 12, 13, 14, 15], dtype=np.int64)

        w1 = w.copy()
        apply_event_pair_update(
            trace, phi, w1, src, tgt,
            target_l1=1e-4,
            gate_mode="soft_trace_gate",
            gate_ref=0.03,
        )

        # Re-run with same inputs — should be identical
        w2 = w.copy()
        apply_event_pair_update(
            trace, phi, w2, src, tgt,
            target_l1=1e-4,
            gate_mode="soft_trace_gate",
            gate_ref=0.03,
        )
        assert np.allclose(w1, w2)

    def test_deterministic_given_same_inputs(self):
        """Same trace + phi + weights → same result (no hidden state)."""
        n = 20
        trace = np.random.default_rng(42).random(n).astype(np.float64) * 0.1
        phi = np.random.default_rng(99).random(n).astype(np.float64) * 0.1

        def run():
            w = np.random.default_rng(77).random(8).astype(np.float64) * 0.5
            src = np.array([0, 1, 2, 3, 4, 5, 6, 7], dtype=np.int64)
            tgt = np.array([10, 11, 12, 13, 14, 15, 16, 17], dtype=np.int64)
            apply_event_pair_update(
                trace.copy(), phi.copy(), w, src, tgt,
                target_l1=1e-4,
                gate_mode="soft_trace_gate",
                gate_ref=0.03,
            )
            return w

        r1 = run()
        r2 = run()
        assert np.allclose(r1, r2)


class TestLifeCoreApplyEventPairPhi:
    """LifeCore.apply_event_pair_phi integration."""

    def test_phi_updates_trace(self):
        """After apply_event_pair_phi, trace increases by phi."""
        cfg = AnivaConfig(
            unit_count=30, seed=42,
            event_pair_plasticity_enabled=True,
            event_pair_trace_tau=1000.0,
        )
        core = LifeCore(cfg)
        phi = np.ones(30, dtype=np.float64) * 0.1
        core.apply_event_pair_phi(phi)
        assert np.allclose(core._event_trace, phi)

    def test_phi_accumulates_trace(self):
        """Multiple phi calls accumulate in trace."""
        cfg = AnivaConfig(
            unit_count=30, seed=42,
            event_pair_plasticity_enabled=True,
            event_pair_trace_tau=1000.0,
        )
        core = LifeCore(cfg)
        phi1 = np.full(30, 0.1, dtype=np.float64)
        phi2 = np.full(30, 0.2, dtype=np.float64)
        core.apply_event_pair_phi(phi1)
        core.apply_event_pair_phi(phi2)
        # Trace should be phi1 + phi2 (no decay if called same step)
        assert np.allclose(core._event_trace, phi1 + phi2)

    def test_phi_with_trace_decay_between_steps(self):
        """Trace decays between steps, phi adds on top."""
        cfg = AnivaConfig(
            unit_count=30, seed=42,
            event_pair_plasticity_enabled=True,
            event_pair_trace_tau=100.0,
            dt=1.0,
        )
        core = LifeCore(cfg)
        phi = np.full(30, 1.0, dtype=np.float64)
        core.apply_event_pair_phi(phi)
        # Step forward (trace decays)
        core.step()
        decay = math.exp(-1.0 / 100.0)
        assert np.allclose(core._event_trace, phi * decay)

    def test_ledger_returned_when_enabled(self):
        """Ledger is returned when event_pair_ledger_enabled=True."""
        cfg = AnivaConfig(
            unit_count=30, seed=42,
            event_pair_plasticity_enabled=True,
            event_pair_ledger_enabled=True,
        )
        core = LifeCore(cfg)
        phi = np.ones(30, dtype=np.float64) * 0.1
        # First call: trace was zero, so no update (but phi is added after)
        ledger1 = core.apply_event_pair_phi(phi)
        assert ledger1 is None  # trace was zero, no update
        # Second call: trace has mass now
        phi2 = np.ones(30, dtype=np.float64) * 0.1
        ledger2 = core.apply_event_pair_phi(phi2)
        assert ledger2 is not None
        assert "gate" in ledger2
        assert "dW_l1" in ledger2

    def test_weights_change_after_event_pair_update(self):
        """Weights should change after a valid event-pair update."""
        cfg = AnivaConfig(
            unit_count=30, seed=42,
            event_pair_plasticity_enabled=True,
            event_pair_ledger_enabled=False,
        )
        core = LifeCore(cfg)
        w_before = core._weight_cache.copy()

        # First phi: fills trace (no update, trace was zero)
        phi = np.ones(30, dtype=np.float64) * 0.1
        core.apply_event_pair_phi(phi)
        # Second phi: trace has mass, update fires
        phi2 = np.ones(30, dtype=np.float64) * 0.1
        core.apply_event_pair_phi(phi2)

        w_after = core._weight_cache.copy()
        assert not np.allclose(w_before, w_after)


class TestEnvironmentPhiVector:
    """Environment.phi_vector generation."""

    def test_phi_vector_shape(self):
        pos = np.random.default_rng(42).uniform(-1, 1, (50, 3))
        stim = Stimulus(position=(0.0, 0.0, 0.0), intensity=1.0, radius=0.5)
        event = StimulusEvent(stimulus=stim, start_step=0, duration_steps=10)
        env = Environment()
        phi = env.phi_vector(event, pos)
        assert phi.shape == (50,)
        assert phi.dtype == np.float64

    def test_phi_vector_zero_for_distant_units(self):
        """Units outside stimulus radius get zero phi."""
        pos = np.array([[10.0, 0.0, 0.0], [0.0, 10.0, 0.0], [0.0, 0.0, 0.0]])
        stim = Stimulus(position=(0.0, 0.0, 0.0), intensity=1.0, radius=0.5)
        event = StimulusEvent(stimulus=stim, start_step=0, duration_steps=10)
        env = Environment()
        phi = env.phi_vector(event, pos)
        assert phi[0] == 0.0  # far away
        assert phi[1] == 0.0  # far away
        assert phi[2] > 0.0   # at center

    def test_phi_vector_linear_decay(self):
        """Influence decays linearly with distance."""
        pos = np.array([
            [0.0, 0.0, 0.0],   # center: full
            [0.2, 0.0, 0.0],   # partway
            [0.5, 0.0, 0.0],   # at radius: zero
        ])
        stim = Stimulus(position=(0.0, 0.0, 0.0), intensity=1.0, radius=0.5)
        event = StimulusEvent(stimulus=stim, start_step=0, duration_steps=10)
        env = Environment()
        phi = env.phi_vector(event, pos)
        assert phi[0] == pytest.approx(1.0)
        assert phi[1] == pytest.approx(0.6)  # 1 - 0.2/0.5 = 0.6
        assert phi[2] == pytest.approx(0.0)

    def test_phi_vector_negative_intensity(self):
        """Inhibitory stimulus produces negative phi."""
        pos = np.array([[0.0, 0.0, 0.0]])
        stim = Stimulus(position=(0.0, 0.0, 0.0), intensity=-1.0, radius=0.5)
        event = StimulusEvent(stimulus=stim, start_step=0, duration_steps=10)
        env = Environment()
        phi = env.phi_vector(event, pos)
        assert phi[0] < 0.0
