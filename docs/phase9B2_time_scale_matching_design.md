# Phase 9B.2 — Time-Scale Matching Design

**Date:** 2026-05-06
**Status:** Design (no experiment yet)
**Branch:** `phase9-temporal-plasticity`
**Depends on:** Phase 9B.1 (clean negative, `phase-9B1-paired-order-negative`)

## 1. Motivation

Phase 9B.1 was a clean negative result. Threshold-crossing detection is functional
(13–18 crossings/unit, 18–23% of steps have at least one crossing), but it produced
no order-specific structural divergence: |asym_diff| remained at OFF baseline level
(1e-6 to 5e-6) across all 4 seeds.

The most likely explanation is **time-scale mismatch**:

| quantity | value |
|----------|-------|
| paired-pulse gap (L→R vs R→L timing difference) | 80 steps |
| mean inter-crossing interval | ~1100–1500 steps |

The 80-step signal is two orders of magnitude smaller than the typical interval
between crossing events. Both L and R regions cross threshold within a similar
window relative to this ~1200-step gap — the signed-delta eligibility cannot
resolve which side crossed first when both crossings are buried in the same
broad temporal bin.

**This design does NOT modify the threshold-crossing rule itself.** It only
adjusts the paired-pulse gap to test whether time-scale alignment alone can
unlock order-specific divergence.

## 2. Core Hypothesis

> If paired-pulse gap is aligned with the crossing-event timescale,
> threshold-crossing eligibility may begin to distinguish L_then_R
> from R_then_L.

If this hypothesis is confirmed, 9B.1's failure was a time-scale problem,
not a mechanism problem. If it is falsified, threshold-crossing alone
is insufficient for order-specific temporal plasticity.

## 3. Experimental Design

### 3.1 What changes

Only **one knob**: the paired-pulse gap.

| parameter | current (9B.1) | 9B.2 values |
|-----------|---------------|-------------|
| gap | 80 | **80, 500, 1000, 1500** |
| pulse_duration | 80 | 80 (unchanged) |
| interval | 600 | 600 (unchanged) |
| crossing_window | 200 | 200 (unchanged) |
| crossing_strength | 0.5 | 0.5 (unchanged) |
| beta | 0.5 | 0.5 (unchanged) |
| decay | 0.05 | 0.05 (unchanged) |
| refractory | 10 | 10 (unchanged) |

The 80-step gap serves as the within-experiment baseline (replicating 9B.1).

### 3.2 Arm structure

Per (seed, gap) combination, 4 arms:

- `L_then_R`: L pulse → gap → R pulse
- `R_then_L`: R pulse → gap → L pulse
- `simultaneous`: L and R pulses overlap
- `separated_control`: L and R pulses separated by full interval (no temporal overlap)

### 3.3 Recommended progression

```
Step 1: Local smoke — 1 seed × 500 steps, verify no crash
Step 2: Cloud validation — 2 seeds × 20k steps
Step 3: Full run — 4 seeds × 20k steps (only if Step 2 shows signal)
```

### 3.4 Estimated cost

| stage | seeds | steps | gaps | arm-runs | est. time (4-core) |
|-------|-------|-------|------|----------|---------------------|
| smoke | 1 | 500 | 4 | 64 | ~2 min |
| validation | 2 | 20k | 4 | 128 | ~75 min |
| full | 4 | 20k | 4 | 256 | ~150 min |

## 4. Primary Diagnostics (per arm, per seed)

Crossing quality — confirms the mechanism is still functioning:

- `crossing_per_unit_mean` / `crossing_per_unit_median`
- `frac_steps_with_crossing`
- `mean_inter_crossing_interval`
- `crossing_balance_lr` — L/R crossing asymmetry
- `crossing_q4_q1_ratio` — threshold quartile bias

## 5. Primary Order-Specific Metrics

- **Directional asymmetry:** |asym_diff| = |L_then_R asymmetry − R_then_L asymmetry|
- **L_then_R effect on L→R subgraph** vs R→L subgraph
- **R_then_L effect on R→L subgraph** vs L→R subgraph
- **Mode comparison table:** OFF / activity / onset / threshold_crossing per gap
- **Whether |asym_diff| increases monotonically with gap** or peaks near
  the mean inter-crossing interval (~1200 steps)

The `simultaneous` arm serves as a non-directional plasticity control;
`separated_control` checks for mere-exposure effects without temporal pairing.

## 6. Interpretation Rules

### Success

Threshold-crossing shows stronger and directionally consistent L→R / R→L
separation at 500/1000/1500 gaps than at 80-step gap, across multiple seeds.
The |asym_diff| for threshold_crossing mode significantly exceeds OFF baseline
and ideally exceeds activity mode.

**→ threshold-crossing mechanism is valid; 9B.1 failed due to time-scale mismatch.**
Proceed to gap-sensitivity profiling and mechanism refinement.

### Partial success

Signal appears only in some seeds, or only near one gap value (e.g., only at
1000), or direction is inconsistent across seeds.

**→ time-scale alignment helps but is not sufficient alone.**
Seed-topology interaction may be confounding. Consider per-seed crossing
interval normalization before adjusting gap.

### Failure

Crossing diagnostics remain healthy, but no gap (80–1500) produces
order-specific divergence above OFF baseline across seeds.

**→ threshold-crossing mechanism alone is insufficient for order-specific
temporal plasticity.** Phase 9C should consider:
- Explicit event-pair traces (store crossing-time pairs, not just single events)
- STDP-like pair memory with fixed or adaptive temporal windows
- Two-stage eligibility: event detection + pair association

## 7. Guardrails

- Do NOT modify the threshold-crossing rule itself in 9B.2.
- Do NOT add LLM, reward, agent, emotion, goal, personality, or language.
- Do NOT overclaim digital life from this experiment.
- This is still substrate-level temporal plasticity research.
- 9B.1 baseline (gap=80) is already collected — do not re-run it.
- Write notes and commit docs before running any experiment.
