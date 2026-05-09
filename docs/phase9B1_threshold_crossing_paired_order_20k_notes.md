# Phase 9B.1 — Threshold-Crossing Paired-Order Assay (20k steps)

**Date:** 2026-05-06
**Status:** Clean negative result
**Branch:** `phase9-temporal-plasticity`

## Summary

Phase 9B.1 tested whether threshold-crossing eligibility can produce order-specific
structural divergence (L→R vs R→L) in the paired-pulse assay. Four modes were compared
across 4 seeds on an Alibaba Cloud ECS (c9i.xlarge, 4-seed parallel):

- OFF (no plasticity control)
- activity (EMA eligibility, Phase 9A baseline)
- onset (EMA eligibility on onset only)
- threshold_crossing (signed-delta with linear decay kernel)

**Result: threshold_crossing does NOT produce directional signal above OFF baseline.**

## Key Numbers

### Directional Asymmetry |L_then_R - R_then_L|

| seed | OFF | activity | onset | threshold_crossing |
|------|-----|----------|-------|--------------------|
| 42 | 2.83e-06 | 1.38e-05 | 2.53e-06 | **2.32e-06** |
| 77 | 2.02e-06 | 2.55e-05 | 4.03e-06 | **3.23e-06** |
| 123 | 7.62e-07 | 2.58e-06 | 4.95e-07 | **3.48e-06** |
| 999 | 4.72e-06 | 2.71e-06 | 2.37e-06 | **2.68e-06** |

All four seeds show threshold_crossing |asym_diff| in the same range as OFF baseline
(1e-06 to 5e-06). activity mode shows larger values due to known global-shift artifact
(see Phase 9A.3), not order-specific signal.

### Crossing Diagnostics (threshold_crossing mode, averaged across arms)

| seed | xing/unit | frac_steps | mean interval | Q4/Q1 |
|------|-----------|------------|---------------|-------|
| 42 | 15.8 | 20.8% | 1262 | 1.38 |
| 77 | 16.9 | 21.6% | 1183 | 1.10 |
| 123 | 13.6 | 17.8% | 1472 | 0.72 |
| 999 | 17.8 | 23.0% | 1126 | 0.91 |

Crossing detection is working — units cross threshold regularly, Q4/Q1 ratio shows
threshold-dependent variation. The mechanism itself is functional.

## Why It Failed

The core mismatch is **time-scale**:

- Mean inter-crossing interval: **1100–1500 steps**
- Paired-pulse gap: **80 steps**

The 80-step L→R vs R→L timing difference is two orders of magnitude smaller than
the typical interval between crossing events. The signed-delta eligibility tries to
capture "which side crossed first," but the crossing events are too sparse — both
sides cross within a similar window relative to the ~1200-step inter-crossing gap.

This is the same category of problem as Phase 9A (EMA too broad / too weak), just
at a different level: **crossing events exist, but their temporal granularity is
too coarse for the signal we're trying to detect.**

## Interpretation

This is a clean negative result. It does NOT mean:

- Aniva's direction is wrong
- Phase 9's temporal plasticity question is wrong
- threshold-crossing as a concept is useless

It DOES mean: under the current paired-pulse gap (80 steps) and crossing timescale
(~1200 steps), threshold-crossing eligibility cannot resolve L→R vs R→L order.

The problem is **time-scale alignment**, not mechanism validity.

## Next Steps

Recommended Phase 9B.2: **time-scale matching**.

A. **Lengthen paired-pulse gap** to match crossing event timescale:
   - Test gap ∈ {500, 1000, 1500} steps
   - If gap ~ crossing interval still fails → threshold-crossing itself insufficient

B. **Increase crossing frequency** (lower threshold, narrower window, stronger drive):
   - Target mean inter-crossing interval 50–200 steps
   - More crossings = finer temporal sampling

Route A is preferred first step — minimal code change, cleanest interpretation.

## Experiment Details

- **Config:** 277 units (139 L, 138 R), beta=0.5, decay=0.05
- **Temporal:** crossing_window=200, crossing_strength=0.5, refractory=10 steps
- **Pulse:** duration=80, gap=80, interval=600
- **Arms:** L_then_R, R_then_L, simultaneous, separated_control
- **Seeds:** 42, 77, 123, 999
- **Total:** 4 modes × 4 arms × 4 seeds = 64 arm-runs × 20k steps
- **Runtime:** ~78 min on ecs.c9i.xlarge (4 parallel)
- **CSV bug:** initial run crashed at CSV write (missing crossing fieldnames); fixed post-hoc, smoke-verified
