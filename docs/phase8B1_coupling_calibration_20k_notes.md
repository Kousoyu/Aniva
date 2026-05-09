# Phase 8B.1: Closed-Loop Coupling Calibration — 20k Notes

**Date:** 2026-05-05
**Status:** 完成
**Experiment:** `aniva/experiments/exp8B1_coupling_calibration.py`

---

## 1. Purpose

Phase 8B 120k 证明了 closed-loop event scheduler 能工作，但 feedback coupling 太弱，未产生可测结构沉积，且旧版 `shuffled_feedback`（shuffle bias 序列）对照不够锋利。

8B.1 的目标不是证明数字生命，而是校准三个旋钮：

1. **Event density**: event_interval 200 → 100 → 50
2. **Event duration**: 80 → 150
3. **Matched shuffle control**: 保留 closed_loop 的 L/R 总数和事件位置，打乱 L/R 标签

核心问题：

> 什么强度的 state → event coupling，才足以让 state-timed feedback 在结构中留下可辨别的痕迹（vs. 随机标签的 matched shuffle）？

---

## 2. Design

### 2.1 Config matrix

| Config | event_interval | event_duration | events/20k | overlap |
|--------|---------------|----------------|------------|---------|
| A      | 200           | 80             | 99         | none    |
| B      | 100           | 80             | 199        | none    |
| C      | 100           | 150            | 199        | yes     |
| D      | 50            | 150            | 399        | heavy   |

### 2.2 Three arms

| Arm | Description |
|-----|------------|
| open_loop | Base event stream as-is, no state feedback |
| closed_loop | State-timed bias → probabilistic overrides of base events |
| matched_shuffle | Replay closed_loop's event positions with same L/R counts but shuffled labels |

matched_shuffle 比旧版 shuffled_feedback 更锋利：它保留了 closed_loop 的事件总数和 L/R 标签数，只是打乱了标签的时序位置。如果 state-timing 真的重要，cl 和 ms 应该产生不同的结构变化（ΔwL1），即使它们的 L/R 事件数完全相同。

### 2.3 Protocol

- Round 1: 4 configs × 2 seeds (42, 999) × 3 arms × 20k steps
- Round 2 (A vs D confirmation): 2 configs × 2 seeds (77, 123) × 3 arms × 20k steps
- All runs: feedback_gain=2.5, max_bias=0.2, base_p_L=0.5

---

## 3. Main Result

**Denser events did not amplify state-timed structural effect. Config A (sparse, no overlap) preserved closed-vs-matched wL1 divergence better than Config D (dense, heavy overlap).**

This is opposite to the pre-experiment intuition that "more events → stronger feedback → larger structural divergence."

---

## 4. Round 1: All 4 Configs (seeds 42, 999)

```
config  seed        arm      L_frac  ΔL_frac      ΔwL1     overridden
------------------------------------------------------------------------
A       42   closed_loop     0.4141  +0.0303  -6.82e-6        9
A       42   matched_shuffle  0.4141  +0.0303  -0.75e-7       —
A       999  closed_loop     0.3737  -0.0101  -3.67e-6        5
A       999  matched_shuffle  0.3737  -0.0101  +1.56e-6       —

B       42   closed_loop     0.4020  +0.0050  +4.33e-6       17
B       42   matched_shuffle  0.4020  +0.0050  +6.15e-6       —
B       999  closed_loop     0.3970   0.0000  -3.30e-6        4
B       999  matched_shuffle  0.3970   0.0000  -4.33e-6       —

C       42   closed_loop     0.4070  +0.0101  +2.28e-6       12
C       42   matched_shuffle  0.4070  +0.0101  +5.44e-6       —
C       999  closed_loop     0.3920  -0.0050  -1.68e-6        5
C       999  matched_shuffle  0.3920  -0.0050  +3.19e-6       —

D       42   closed_loop     0.4436  -0.0226  +5.78e-6       21
D       42   matched_shuffle  0.4436  -0.0226  +6.11e-6       —
D       999  closed_loop     0.4612  -0.0050  +4.25e-6       12
D       999  matched_shuffle  0.4612  -0.0050  +3.78e-6       —
```

### Config ranking

| Config | mean|ΔL_frac| | mean|ΔwL1| | per-event |ΔwL1| | cl-ms divergence |
|--------|---------------|-------------|-------------------|-------------------|
| A      | 0.0202        | 5.25e-6     | 5.3e-8            | strongest |
| B      | 0.0025        | 3.81e-6     | 1.9e-8            | weak |
| C      | 0.0075        | 1.98e-6     | 1.0e-8            | moderate |
| D      | 0.0138        | 5.01e-6     | 1.3e-8            | weakest |

Config A has the highest |ΔL_frac|, highest |ΔwL1|, and highest per-event structural efficiency — despite having the fewest events.

---

## 5. Round 2: A vs D Confirmation (seeds 77, 123)

```
config  seed        arm      L_frac  ΔL_frac      ΔwL1     overridden
------------------------------------------------------------------------
A       77   closed_loop     0.3838   0.0000   0.00e+0         0
A       77   matched_shuffle  0.3838   0.0000  -3.01e-7        —
A      123   closed_loop     0.3636  -0.0202  -2.28e-7         4
A      123   matched_shuffle  0.3636  -0.0202  +1.75e-6        —

D       77   closed_loop     0.4662   0.0000  -2.62e-6        18
D       77   matched_shuffle  0.4662   0.0000  -5.27e-6        —
D      123   closed_loop     0.4662   0.0000  +1.40e-6        12
D      123   matched_shuffle  0.4662   0.0000  +2.88e-6        —
```

---

## 6. Cross-Seed A vs D: cl-ms wL1 Divergence

|ΔwL1_cl − ΔwL1_ms|:

| seed | Config A | Config D | A/D ratio |
|------|----------|----------|-----------|
| 42   | 6.07e-6  | 0.33e-6  | **18x** |
| 999  | 5.23e-6  | 0.47e-6  | **11x** |
| 77   | 3.01e-7* | 2.66e-6  | 0.1x |
| 123  | 1.98e-6  | 1.48e-6  | 1.3x |

\* seed=77 Config A: override=0, feedback loop inactive. Excluded from comparison.

### Sign flip: A only

| Config | cl-ms sign flips / 4 seeds |
|--------|---------------------------|
| A      | 2 (seed 999, 123)         |
| D      | 0                         |

When L/R labels are shuffled in Config A, structural change direction flips for 2/4 seeds. In Config D, cl and ms always drift the same direction with similar magnitude — dense events produce a heat-bath-like average pressure that masks state-timing.

---

## 7. Interpretation

### 7.1 Denser events ≠ stronger coupling

The original assumption was that more events create more opportunities for state-timed feedback to accumulate. The data suggests the opposite: dense overlapping events create a non-specific average pressure that pushes structure in the same direction regardless of timing. The timing signal is diluted, not amplified.

### 7.2 Sparse events preserve timing specificity

Config A's sparse events (99 in 20k, interval 200 > duration 80 = no overlap) give the system enough quiet time between events for the state-timed label assignment to matter. The same number of L and R events, placed at different times, can push structure in different directions.

### 7.3 Seed-dependent closed-loop sensitivity

seed=77 in Config A had **zero overrides**. The bias never crossed the override threshold at any event step. This is not a malfunction — it means certain topologies, under sparse feedback, don't generate enough lr_imbalance fluctuation to trigger the feedback mechanism. Closed-loop sensitivity is itself seed-dependent.

This aligns with the Aniva design principle: seed/topology determines how environment influences the individual.

### 7.4 Per-event structural efficiency

| Config | |ΔwL1| per event |
|--------|-----------------|
| A | 5.3e-8 |
| B | 1.9e-8 |
| C | 1.0e-8 |
| D | 1.3e-8 |

Config A is 4x more efficient per event than Config D. More events produce diminishing structural returns — the system saturates or the effects partially cancel.

---

## 8. Limits

- 20k steps only — structural effect sizes are ~1e-6
- 4 seeds — sufficient for calibration signal, not for statistical proof
- matched_shuffle at 20k has zero ΔL_frac separation from closed_loop by design (same L/R counts)
- ΔwL1 divergence exists but magnitude is small relative to absolute wL1 (~0.2)

This is a **calibration signal**, not final structural proof.

---

## 9. Next Step

**Phase 8B.1A**: Config A only, 120k steps, 4 seeds, with `matched_shuffle` control.

- Use the cleaner `matched_shuffle` arm from this script (not the old `shuffled_feedback`)
- Cloud run: 4 seeds × 3 arms × 120k
- Goal: test whether the Config A cl-ms divergence signal at 20k persists and amplifies at 120k

The B/C/D configs are ruled out as enhancement routes. Config A is the calibration winner.
