---
phase: 10C.2
experiment: capture_diagnostics_smoke
status: COMPLETE — CLEAN NEGATIVE
date: 2026-05-12
seeds: [42, 77]
---

# Phase 10C.2 Capture Diagnostics Smoke — Results Notes

## Summary

Phase 10C.2 diagnostics smoke completed.
10C.1 instrumentation did not change 9D behavior.

## Baseline Verification

Baseline slow_l1 matches 10A.2C exactly:

| seed | slow_l1 (closed_loop) | expected | diff |
|---|---|---|---|
| 42 | 0.00039344 | 0.00039344 | 0.00e+00 |
| 77 | 0.00044013 | 0.00044013 | 0.00e+00 |

Gate logic confirmed unchanged. closed_loop vs exact_replay mirror remains valid.

## Diagnostic Comparison: closed_loop vs divergent_warmup_replay

| metric | seed42 Δ | seed77 Δ |
|---|---|---|
| tag_trace_alignment | 0.000000 | 0.000000 |
| tag_concentration | 0.000000 | 0.000000 |
| tag_effective_support | 0.000000 | 0.000000 |
| trace_concentration | 0.000000 | 0.000000 |
| trace_effective_support | 0.000000 | 0.000000 |
| tag_weighted_energy | +0.004963 | −0.010562 |

Five of six metrics are exactly zero across both seeds.
`tag_weighted_energy` shows only ~1–2% level difference.

Warmup divergence confirmed present (act_div=0.056 seed42, 0.135 seed77),
but it does not propagate into the capture-visible variables.

## Verdict

**CLEAN NEGATIVE for current 10C diagnostics.**

Not just the scalar gate — even the per-connection diagnostic arrays
(tag_cache, event_trace projections, HHI concentrations) show no
meaningful difference between closed_loop and divergent_warmup_replay.

## Interpretation

The current consolidation pathway is **event-local**:

1. `tag_cache` initializes from zero at replay start (no warmup plasticity →
   no warmup history in tags).
2. `event_trace` decays on a timescale short enough that warmup-end differences
   are overwritten by replay events before the first capture fires.
3. Only `tag_weighted_energy` carries a faint echo of warmup divergence
   (via local energy, which is influenced by activation state), but the
   signal is too small to affect the gate.

The system has no container that accumulates history across events,
across warmup, or across the short event_trace decay window.
State-context differences from warmup do not survive into capture-visible variables.

## What This Rules Out

- Route A (scalar slow_l1 difference): ruled out in 10A.2C.
- Route C (per-connection diagnostic difference): ruled out here.
- Redesigning the gate threshold or signal formula will not help —
  the input arrays themselves carry no history signal.

## What This Points To

The bottleneck is structural: the system needs a **historical context trace** —
a per-unit or per-region slow variable with a time constant much longer than
`event_trace`, capable of accumulating activation/energy/event history
across the full run.

This is the entry point for Phase 10D.

## Do Not

- Do not redesign the gate yet.
- Do not enter 10C.3.
- Do not change capture signal or slow_weight transfer.

## Next Direction

**Phase 10D: historical context trace planning.**

Core question:
> Can we introduce a slow-varying per-unit trace that accumulates
> history across events and warmup, making capture context
> genuinely sensitive to individual history?
