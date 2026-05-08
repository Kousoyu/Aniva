# Phase 9C.4 Full Integration Smoke — Results Notes

> **Status: PASSED.** This is integration smoke, not new scientific validation.
> It verifies that the core path reproduces the 9C.3 diagnostic mechanism behavior
> under full-size 300-unit settings.

---

## 1. What was tested

The three-link core path:
```
Environment.phi_vector → LifeCore.apply_event_pair_phi → plasticity_event_pair.apply_event_pair_update
```

With Hebbian plasticity ENABLED (normal LifeCore.step), unlike 9C.3 diagnostic
where temporal plasticity was disabled.

Parameters: seed=42, unit_count=300, gap=500, tau=1000, num_pairs=5,
rest_window=5000, target=1e-4, gate_ref=3e-2, gate_power=1.0,
gate_mode=soft_trace_gate.

Arms: L_then_R, R_then_L (sequential only).

---

## 2. Root cause found and fixed

The first run exposed a trace-decay unit mismatch:

- 9C.3 diagnostic: `trace *= exp(-Δsteps / tau)` — step-based decay
- 9C.4 core path (initial): `trace *= exp(-config.dt / tau)` per step, with `config.dt=0.5`

Result: effective tau doubled, stale trace decayed ~12.7x slower than intended.
gate_c inflated from ~0.02 to ~0.38, contamination from ~0.01 to ~0.20.

**Fix commit:** `7b10e4b` — "fix: use step units for event-pair trace decay".
Changed decay to `exp(-1.0 / tau)` per step, matching 9C.3 step-based semantics.

---

## 3. Final results (after fix)

| Metric | L_then_R | R_then_L | 9C.3 seed42 |
|--------|:--------:|:--------:|:-----------:|
| gate_w | 1.0000 | 1.0000 | 1.000 |
| gate_c | 0.0268 | 0.0233 | 0.023–0.027 |
| contamination | 0.0171 | 0.0087 | 0.017 (max) |
| acc_dW_DI | +0.9658 | −0.9826 | — |

Cross-arm:

| Metric | 9C.4 | 9C.3 seed42 |
|--------|:----:|:-----------:|
| acc_dW_OS | **+1.9485** | +1.949 |

- schedule_ok: all true
- NaN: 0
- saturation: 0

**acc_dW_OS differs from 9C.3 reference by < 0.05%.**

---

## 4. Interpretation

- Core path successfully reproduces the 9C.3 diagnostic mechanism under full
  300-unit scale with Hebbian plasticity enabled.
- Hebbian plasticity (continuous, rate=0.0001) did NOT drown the event-pair
  directional signal.
- The trace-decay unit mismatch was a plumbing issue (not a mechanism failure)
  and was caught exactly where full integration smoke should catch it.
- This is integration verification, NOT new validation — 9C.3 already validated
  the mechanism across 4 seeds.

---

## 5. Success criteria

- [x] schedule_ok: all true
- [x] mean_gate_within ≈ 1.0 (≥ 0.95)
- [x] mean_gate_cross < 0.05
- [x] gate_cross / gate_within ≥ 10x gap
- [x] contamination_ratio < 0.05 (per arm)
- [x] acc_dW_OS > 0
- [x] 0 NaN
- [x] 0 weight explosion
- [x] CSV / JSON output complete

---

## 6. What was NOT tested

- Multi-seed generalization (that's 9C.3's job)
- Other gap/tau/num_pairs values
- Simultaneous / separated_control arms
- Optimal Hebbian/event-pair ratio
- Long-term structural consolidation

---

## 7. Files

- `aniva/experiments/exp9C4_full_integration_smoke.py` — runner script
- `docs/phase9C4_full_integration_smoke_design.md` — pre-run design
- `docs/phase9C4_full_integration_smoke_notes.md` — this file
- `results/phase9C4_full_integration_smoke_seed42_seq.csv` — merged CSV
- `results/phase9C4_full_integration_smoke_seed42_seq_summary.json` — merged JSON
