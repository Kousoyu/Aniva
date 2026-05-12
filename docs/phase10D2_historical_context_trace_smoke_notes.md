# Phase 10D.2 — Historical Context Trace Smoke: Notes & Evidence Chain

## 1. v1 Preliminary Run (protocol-failed, not official)

The first run of the 10D.2 runner produced a visually positive H1 signal:
- seed42: `closed_vs_divergent_h_l1 ≈ 5.22` (~9.5x above threshold)
- seed77: `closed_vs_divergent_h_l1 ≈ 5.01` (~9.8x above threshold)

However, P5 and P7 both failed:
- `closed_vs_exact_h_l1 ≈ 2.0–2.4` (should be < 1e-6)
- `warmup_weight_delta_l1 ≈ 108–110` (should be ≈ 0)

Root cause: `event_pair_plasticity_enabled=False` only disables 9C event-pair plasticity.
Base Hebbian (`plasticity_rate=0.0001`) still ran every warmup step, modifying weights by
~108–110 L1 units. This changed the activation trajectory and thus h[u] accumulation,
breaking the exact-mirror invariant between closed_loop and exact_replay.

**v1 result was discarded. H1 signal was not official.**

## 2. v2 Fix: Warmup Weights Frozen in All Arms

Commit: `79894f2` — "fix: freeze warmup weights in phase 10D.2 runner"

Added helper `_run_warmup_weight_frozen(core, warmup_steps, env)`:
- Snapshots `w0 = core._weight_cache.copy()` and `w0_conn` before warmup
- After every warmup step: restores `_weight_cache` and each `conn.weight`
- State (activations, energies, h[u], traces) evolves normally
- Returns `(warmup_weight_delta, nan_hit)`

Applied to all four arms:
- Arm 1 (closed_loop): split into warmup phase + main phase
- Arm 2 (exact_replay): replaced single end-of-warmup restore with per-step freeze
- Arm 3 (divergent_warmup_replay): replaced both `core_div` and `core_ref` warmup loops
- Arm 4 (matched_warmup_control): replaced `core_div` warmup loop

## 3. Official v2 Result

Run date: 2026-05-12. Seeds: [42, 77]. ECS: 4C8G Ubuntu 22.04.

### seed42

| metric | value |
|---|---|
| `closed_vs_exact_h_l1` | **0.00000000** |
| `warmup_weight_delta_l1` (exact_replay) | **0.00000000** |
| `warmup_weight_delta_l1` (divergent) | **0.00000000** |
| `closed_vs_divergent_h_l1` | **7.98224388** |
| H1 threshold (0.01 × h_l1_final) | 0.55674000 |
| H1 ratio | **~14.3x** |
| `slow_weight_l1` (closed / exact / divergent) | 0.000393 / 0.000393 / 0.000393 |
| `nan_hit` | False |
| P1–P7 | all PASS |
| H1 | **PASS** |

### seed77

| metric | value |
|---|---|
| `closed_vs_exact_h_l1` | **0.00000000** |
| `warmup_weight_delta_l1` (exact_replay) | **0.00000000** |
| `warmup_weight_delta_l1` (divergent) | **0.00000000** |
| `closed_vs_divergent_h_l1` | **3.72833405** |
| H1 threshold (0.01 × h_l1_final) | 0.52526600 |
| H1 ratio | **~7.1x** |
| `slow_weight_l1` (closed / exact / divergent) | 0.000518 / 0.000518 / 0.000518 |
| `nan_hit` | False |
| P1–P7 | all PASS |
| H1 | **PASS** |

**Hard pass: 2/2 seeds.**

## 4. Interpretation

`historical_context_trace` h[u] (τ=10000, per-unit slow activation average) successfully
preserves warmup-history differences that are invisible to `event_trace`, `tag_cache`,
and all 9C/9D diagnostics.

Key properties confirmed:
- h[u] is a genuine history container: divergent warmup leaves a measurable imprint
  that persists through the entire 5500-step replay phase
- h[u] does not affect gate, capture, or slow_weight: `slow_weight_l1` is identical
  across closed_loop, exact_replay, and divergent_warmup_replay
- The exact-mirror invariant holds: closed_loop and exact_replay produce h[u] = 0.0 L1
  difference, confirming the protocol is clean
- Current 9D capture is blind to h[u]: capture count and slow_weight are unaffected
  by warmup history

This is a clean positive for h[u] as a history container. It is not yet a claim about
slow structural learning — h[u] is read-only in this experiment.

Context in the evidence chain:
- Phase 10C proved that `tag_cache / event_trace / diagnostics` cannot see warmup history
- Phase 10D.2 proves that h[u] can see it, under a clean protocol with frozen warmup weights
- The "film" is exposed; the question for 10D.3 is what projection of h[u] is most
  informative for capture

## 5. Next Step: Phase 10D.3 Design

Design only — no implementation in this commit.

Direction: h[u] stays default-off and read-only. Add diagnostics only:
- h-tag alignment: correlation between h[u] and tag_cache at capture time
- h-weighted tag energy: slow_weight delta weighted by h[u] magnitude
- h-context capture predictor: does h[u] at capture time predict capture signal strength?

Goal: understand the shape of h[u]'s shadow before connecting it to any mechanism.
