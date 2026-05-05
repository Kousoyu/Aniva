# Phase 9A.3: Paired-Order Temporal Plasticity Assay — 20k Notes

**Date:** 2026-05-05
**Status:** 完成（负结果：当前公式不能分辨 L/R 顺序）

---

## 1. Purpose

Phase 9A.2 proved that the eligibility trace amplifies structural differences globally, not specifically for state-timed events. But 9A.2 used a complex closed-loop world where firing order may be similar across arms even when event timing differs.

9A.3 asks the most fundamental question:

> **Under identical total stimulation, can the eligibility formula distinguish "L fires before R" from "R fires before L"?**

This is the microscope calibration — if the formula cannot distinguish order here, no amount of world complexity can help.

---

## 2. Design

| Parameter | Value |
|-----------|-------|
| steps | 20,000 |
| seeds | 42, 77, 123, 999 |
| β (temporal_plasticity_rate) | 0.5 |
| τ (1/temporal_trace_decay) | 20 steps |
| pulse_duration | 80 |
| pair_gap | 80 |
| pair_interval | 600 |
| modes | TEMPORAL OFF, TEMPORAL ON |
| total arm-runs | 4 seeds × 2 modes × 4 arms = 32 |

### Four arms — all matched for total stimulation

| Arm | Order | Total L pulses | Total R pulses |
|-----|-------|---------------|---------------|
| L_then_R | L at t, R at t+80 | 34 | 34 |
| R_then_L | R at t, L at t+80 | 34 | 34 |
| simultaneous | L+R at t | 34 | 34 |
| separated_control | L at t, R at t+300 | 34 | 34 |

All arms: identical intensity (0.02), duration (80 steps), total event count (68). Only temporal ORDER differs.

---

## 3. Results

### 3.1 Directional Asymmetry: L→R signed_mean minus R→L signed_mean

This is the key metric. If eligibility can distinguish order, L_then_R and R_then_L should have different asymmetry values.

```
TEMPORAL OFF:
seed   L_then_R asym    R_then_L asym    simult. asym     separated asym
---------------------------------------------------------------------------
  42   +1.389e-03       +1.388e-03       +1.385e-03       +1.389e-03
  77   -1.348e-02       -1.348e-02       -1.348e-02       -1.348e-02
 123   +1.405e-02       +1.405e-02       +1.405e-02       +1.405e-02
 999   -3.356e-03       -3.350e-03       -3.358e-03       -3.355e-03

TEMPORAL ON:
seed   L_then_R asym    R_then_L asym    simult. asym     separated asym
---------------------------------------------------------------------------
  42   +1.385e-03       +1.389e-03       +1.399e-03       +1.377e-03
  77   -1.346e-02       -1.344e-02       -1.344e-02       -1.347e-02
 123   +1.411e-02       +1.410e-02       +1.410e-02       +1.411e-02
 999   -3.347e-03       -3.354e-03       -3.370e-03       -3.356e-03
```

**The directional asymmetry is identical across all 4 arms within each seed.** The maximum arm-to-arm difference is at the 1e-05 level — pure noise.

The asymmetry is a SEED-INTRINSIC constant:
- Seed 42, 123: positive (L→R > R→L in signed mean)
- Seed 77, 999: negative (R→L > L→R in signed mean)

This constant is determined by the network's initial connectivity structure, not by event order.

### 3.2 L_then_R vs R_then_L — cosine and L1

```
TEMPORAL OFF:
seed   cos(L_then_R, R_then_L)    |L1|         |L2|
---------------------------------------------------------
  42       0.99999995           3.87e-05    6.80e-05
  77       0.99999995           4.06e-05    7.00e-05
 123       0.99999997           3.30e-05    5.66e-05
 999       0.99999995           3.59e-05    6.85e-05

TEMPORAL ON:
seed   cos(L_then_R, R_then_L)    |L1|         |L2|
---------------------------------------------------------
  42       0.99999880           2.06e-04    3.49e-04
  77       0.99999877           2.11e-04    3.58e-04
 123       0.99999918           1.59e-04    2.87e-04
 999       0.99999865           2.25e-04    3.73e-04
```

TEMPORAL ON amplifies |L1| by 4-6x. But this amplification is uniform across ALL arm pairs — L_then_R vs R_then_L is not elevated above other pairs.

### 3.3 Within-ON pairwise matrix — all equally separated

```
Seed 42, TEMPORAL ON:
L_then_R vs R_then_L:          |L1| = 2.06e-04
L_then_R vs simultaneous:       |L1| = 2.16e-04
L_then_R vs separated_control:  |L1| = 1.95e-04
R_then_L vs simultaneous:       |L1| = 1.81e-04
R_then_L vs separated_control:  |L1| = 2.02e-04
simultaneous vs separated:       |L1| = 2.23e-04
```

No hierarchy. The pair predicted to be MOST different (L_then_R vs R_then_L) is in the middle of the pack. The eligibility trace amplifies ALL cross-arm distances equally.

### 3.4 Global shift vs differential signal

```
seed   same-arm off→on L1    ON L_then_R vs R_then_L L1    ratio
-------------------------------------------------------------------
  42        3.14e-04                  2.06e-04               0.65
  77        4.08e-04                  2.11e-04               0.52
 123        2.31e-04                  1.59e-04               0.69
 999        4.38e-04                  2.25e-04               0.51
```

Same pattern as 9A.2: cross-arm ON differences are always smaller than the global OFF→ON shift.

### 3.5 Regional readout: identical across arms

```
Seed 42, TEMPORAL ON — L→R signed_mean:
  L_then_R:          -3.200e-03
  R_then_L:          -3.225e-03
  simultaneous:      -3.203e-03
  separated_control: -3.211e-03
```

All four arms produce L→R signed_mean within 2.5e-05 of each other. The event order has zero detectable effect on cross-region weight direction.

---

## 4. Interpretation

### 4.1 The current eligibility formula is a spatial asymmetry amplifier, not a temporal order detector

The formula:

```
eligibility = pre_trace * post_act - pre_act * post_trace
```

uses EMA activity traces with τ ≈ 200 steps. This long time constant makes `pre_trace` and `post_trace` behave as smoothed time-averaged activation levels, not as "who just fired" detectors.

The cross term `pre_trace * post_act - pre_act * post_trace` amplifies the network's INTRINSIC spatial asymmetry — which hemisphere has higher baseline activity, which direction's connections are naturally stronger. This is why:

1. All 4 arms within a seed produce identical directional asymmetry
2. The asymmetry is seed-specific (seed 42 positive, seed 77 negative)
3. TEMPORAL ON amplifies |L1| globally without differentiating between arms

### 4.2 Why the gap doesn't matter

The EMA trace with τ≈200 steps means:
- gap=80: trace decays to ~67% → still strong overlap
- gap=300: trace decays to ~22% → much weaker overlap

But the directional asymmetry is the SAME for both gap values (simultaneous has gap=0, separated has gap=300 — same asymmetry). This confirms that the eligibility signal is dominated by the intrinsic spatial activation pattern, not by the temporal structure of events.

### 4.3 Physical interpretation

The EMA trace is too slow to capture temporal order. It behaves like a leaky integrator with a 200-step window — it remembers "who was active recently" but not "who became active just now, and in what order."

This is why onset-based (derivative-based) detection is needed: it would record "who is transitioning from inactive to active RIGHT NOW" rather than "who has been active on average."

---

## 5. Success Criteria

| Level | Criteria | Status |
|-------|----------|--------|
| Low | TEMPORAL OFF preserves baseline | ✅ 4 seeds, stable |
| Low | No numerical instability | ✅ 32/32 stable |
| **Medium** | **TEMPORAL ON: L_then_R vs R_then_L asymmetry differs** | ❌ **asymmetry identical across all arms** |
| **Medium** | **L_then_R L→R sgn > R_then_L L→R sgn** | ❌ **values overlap within noise** |
| Strong | L→R subgraph selectively strengthened in L_then_R | ❌ not observed |
| Strong | cos(L_then_R, R_then_L) < 0.9999 | ❌ cos ~0.999998+ |

**Verdict: Negative — current activity-EMA eligibility formula cannot distinguish L→R from R→L temporal order.**

---

## 6. Conclusion

> **Phase 9A.3 proves that the current EMA activity-trace eligibility formula is a global temporal plasticity modifier, not a temporal order detector. It amplifies the network's intrinsic spatial asymmetry but cannot distinguish "L before R" from "R before L."**

Key findings:
1. L→R minus R→L signed_mean asymmetry is a seed-intrinsic constant — identical across all 4 arms
2. Swapping event order (L_then_R ↔ R_then_L) produces no detectable change in directional subgraph weights
3. The formula amplifies spatial activation bias, not temporal order structure
4. The long EMA τ (≈200 steps) makes the trace too slow to capture onset ordering
5. This is a FORMULA limitation, not a parameter tuning issue. β sweep would only amplify the same spatial bias more strongly.

---

## 7. Evidence Chain Complete

```
9A smoke:  eligibility trace produces measurable signal         ✅
9A.1:      signal is systematic across 4 seeds                 ✅
9A.2:      signal is global shift, not state-timing specific    ✅
9A.3:      root cause — formula cannot detect temporal order    ✅ ← HERE
```

The bottleneck is now precisely located: **the eligibility formula itself.**

---

## 8. Next Direction: Phase 9A.4 Onset-Based Eligibility

The current formula fails because it uses smoothed activation LEVELS. The fix is to use activation ONSETS (positive derivatives):

```
pre_onset = max(activation[t] - activation[t-1], 0)
post_onset = max(activation[t] - activation[t-1], 0)

eligibility = pre_onset_trace * post_onset - post_onset_trace * pre_onset
```

This captures "who started firing recently" rather than "who has been firing on average." The onset_trace is still an EMA, but now it tracks the history of activation RISES, not activation levels.

Critical implementation detail: eligibility must be computed using OLD onset traces, then traces are updated with current onsets — otherwise simultaneous pulses produce spurious causal signals.

Proposed 9A.4 design: same 4-arm paired-order assay as 9A.3, but running 3 modes:
- TEMPORAL OFF (baseline)
- Activity-EMA eligibility (current formula, for direct comparison)
- Onset-based eligibility (new formula)

This directly answers: does onset detection fix the directional blindness?

---

## 9. Files

| File | Role |
|------|------|
| `aniva/experiments/exp9A3_paired_order.py` | Experiment script |
| `results/phase9A3_paired_order_20k.csv` | Per-arm metrics |
| `results/phase9A3_paired_order_20k_summary.json` | Full results with readout |
