---
phase: 10D.2
title: Historical Context Trace Smoke
status: DESIGN
date: 2026-05-12
prerequisite: 10D.1 (commit 747f3a0) — h[u] implemented, default off, 289/289 tests pass
---

# Phase 10D.2 — Historical Context Trace Smoke Design

## Background

Phase 10A–10C exhausted the replay-control approach:

| Phase | Test | Result |
|---|---|---|
| 10A.2C | scalar slow_l1 differs across arms? | CLEAN NEGATIVE |
| 10C.2 | per-connection diagnostics differ? | CLEAN NEGATIVE |

Root cause: the consolidation pathway is **event-local**.
`tag_cache` starts from zero at replay start.
`event_trace` decays fast enough that warmup differences are overwritten
before the first capture fires.

Phase 10D.1 introduced `historical_context_trace h[u]`:
a per-unit slow variable that updates every step from t=0,
including during warmup, with τ_h = 10000 steps.

Unlike `event_trace` (τ ≈ 1000 steps), `h[u]` is designed to retain
warmup history through the entire replay phase.

## Core Question

> Does `h[u]` differ between `closed_loop` and `divergent_warmup_replay`
> at capture time — where `event_trace` and `tag_cache` showed zero difference?

If yes: the historical container works. Warmup history is now visible
inside the system, even if it does not yet affect any mechanism.

If no: τ_h or the update signal needs adjustment.

## Frozen Parameters

```
seeds:                  [42, 77]
total_steps:            7500
warmup_steps:           2000
decision_interval:      250
pulse_duration:         80
divergent_noise_offset: 5000
scheduler θ:            W=5.0, B_none=+1.0, B_L=-1.5, B_R=-1.5, B_sim=-3.0, τ=1.0

historical_context_enabled:  True
historical_context_tau:      10000.0
historical_context_clip:     True

h[u] update starts at t=0 (includes warmup)
h[u] does NOT affect gate, capture, slow_weight, or any mechanism
9C ON after warmup end (t=2000)
9D ON after warmup end (t=2000)
warmup plasticity: OFF (weight snapshot/restore, same as 10A.2C)
```

## Arms

### Arm 1: closed_loop

Standard run. Scheduler active from t=2000.
`h[u]` accumulates from t=0 through t=7499.
Generates the canonical event log for replay arms.

### Arm 2: exact_replay

Same seed, same topology, same warmup (no divergence).
Replays the closed_loop event log exactly.
`h[u]` should be identical to closed_loop at all times.
**Mirror sanity check**: if `h` differs here, there is a protocol bug.

### Arm 3: divergent_warmup_replay

Same seed/topology/weights as closed_loop.
Warmup uses noise seed +5000 → different activation trajectory.
`h[u]` accumulates a different warmup history.
At t=2000, weights are restored (plasticity OFF guarantee).
Replay phase uses the same event log as closed_loop.

**Primary test arm**: does `h[u]` at capture time differ from closed_loop?

### Arm 4: matched_warmup_control

Same divergent warmup as arm 3.
No event replay after t=2000.
Isolates the warmup-only contribution to `h[u]`.

## Metrics

### Per-arm summary

| Metric | Description |
|---|---|
| `h_l1` | sum of h[u] at final step |
| `h_mean` | mean of h[u] at final step |
| `h_max` | max of h[u] at final step |
| `h_concentration` | HHI of h distribution at final step |
| `h_effective_support` | 1/HHI at final step |
| `slow_weight_l1` | final slow_weight L1 (expected identical across arms 1-3) |
| `capture_count` | number of 9D captures |
| `nan_count` | NaN hits |

### Cross-arm comparison

| Metric | Description |
|---|---|
| `h_divergence_at_warmup_end` | mean\|h_div[u] - h_ref[u]\| at t=2000 |
| `h_divergence_at_final` | mean\|h_div[u] - h_cl[u]\| at t=7499 |
| `activation_divergence_at_warmup_end` | mean\|acts_div - acts_ref\| at t=2000 (P6 check) |
| `closed_vs_exact_h_l1` | \|h_cl - h_ex\| L1 (should be ~0) |
| `closed_vs_divergent_h_l1` | \|h_cl - h_div\| L1 (primary signal) |
| `divergent_vs_matched_ctrl_h_l1` | \|h_div - h_mc\| L1 (event effect on h) |

### Per-capture ledger fields (from 10D.1)

At each 9D capture event, the ledger entry includes:
- `historical_context_l1`
- `historical_context_mean`
- `historical_context_max`
- `historical_context_concentration`
- `historical_context_effective_support`

These are extracted into the per-capture CSV for cross-arm comparison.

## Output Files

```
results/phase10D2_hctrace_captures.csv     — per-capture rows (all arms, all seeds)
results/phase10D2_hctrace_summary.csv      — per-arm summary
results/phase10D2_hctrace_summary.json     — full summary with frozen params
```

### Per-capture CSV schema

```
seed, arm, capture_index, capture_step,
capture_signal, slow_weight_delta_l1, capture_count_so_far,
historical_context_l1, historical_context_mean, historical_context_max,
historical_context_concentration, historical_context_effective_support
```

### Arm summary CSV schema

```
seed, arm, slow_weight_l1, capture_count,
h_l1_final, h_mean_final, h_max_final,
h_concentration_final, h_effective_support_final,
h_divergence_at_warmup_end, h_divergence_at_final,
activation_divergence_at_warmup_end,
closed_vs_exact_h_l1, closed_vs_divergent_h_l1,
warmup_weight_delta_l1, nan_count
```

## Success Criteria

| Check | Criterion | Interpretation if fails |
|---|---|---|
| P1 | no NaN | numerical instability |
| P2 | max_abs_weight < 10 | weight explosion |
| P3 | exact_replay hash mismatches = 0 | event log replay broken |
| P4 | event counts match across arms 1-3 | protocol bug |
| P5 | closed_vs_exact_h_l1 < 1e-6 | h is not deterministic |
| P6 | activation_divergence_at_warmup_end > 1e-8 | warmup divergence absent |
| P7 | warmup_weight_delta_l1 < 1e-6 | plasticity leaked into warmup |
| **H1** | **closed_vs_divergent_h_l1 > 0.01 · h_l1_final** | **h does not capture warmup history** |

P1–P7 are protocol checks (same as 10A.2C).
**H1 is the scientific hypothesis check.**

A relative threshold of 1% is conservative: if warmup divergence
(act_div ≈ 0.056–0.135 from 10A.2C) leaves any trace in h[u],
it should exceed this easily given τ_h = 10000 steps.

## Expected Behavior

At τ_h = 10000 steps, after 2000-step warmup:

```
h[u] at t=2000 ≈ (1 - exp(-2000/10000)) · mean_activation_during_warmup
               ≈ 0.181 · mean_activation_during_warmup
```

The divergent arm has a different activation trajectory during warmup,
so `h_div[u]` at t=2000 should differ from `h_ref[u]` by roughly:

```
Δh ≈ 0.181 · act_div ≈ 0.181 · 0.056 ≈ 0.010  (seed42)
Δh ≈ 0.181 · act_div ≈ 0.181 · 0.135 ≈ 0.024  (seed77)
```

After the replay phase (5500 more steps), the divergence decays:

```
Δh at t=7500 ≈ Δh_at_2000 · exp(-5500/10000) ≈ Δh_at_2000 · 0.578
```

So the expected final divergence is:
- seed42: ~0.006
- seed77: ~0.014

Both are well above the 1% threshold if h_mean ≈ 0.05–0.10.

## Interpretation Matrix

| slow_l1 | h diverges | Interpretation |
|---|---|---|
| identical | YES | **Target outcome.** h stores history; capture is still blind. 10D.3: connect h to capture. |
| identical | NO | h too weak. Adjust τ or signal. Do not proceed to 10D.3. |
| differs | YES | Unexpected. Verify gate invariance. |
| differs | NO | Unexpected. Verify protocol. |

The expected outcome is row 1: slow_l1 identical (as in 10A.2C),
h diverges (new signal from 10D.1).

## Boundaries

- Do not connect `h[u]` to the capture gate in this phase.
- Do not modify 9D gate formula, capture signal, or slow_weight transfer.
- Do not tune τ_h after seeing results (pre-register τ=10000 now).
- Do not enter 10D.3 until H1 is confirmed.
- Do not interpret h divergence as "Aniva has memory" — it is a
  diagnostic signal, not a functional mechanism yet.

## Runtime Estimate

Same structure as 10A.2C / 10C.2: ~15 min for 2 seeds on ECS.
Run on ECS (not local).

## Next Step After This Design

Implement `aniva/experiments/exp10D2_historical_context_trace_smoke.py`:
- Based on 10A.2C / 10C.2 four-arm structure
- Add `historical_context_enabled=True` to `_make_cfg`
- Snapshot `h[u]` at warmup end for cross-arm comparison
- Output per-capture CSV + arm summary CSV + JSON
- Baseline check: slow_l1 must match 10A.2C reference values
