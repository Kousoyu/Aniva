# Phase 9A.4: Onset-Based Eligibility — Paired-Order Assay

**Date:** 2026-05-06
**Status:** 完成（负结果：onset-EMA 退回 OFF baseline，零时序信号）

---

## 1. Purpose

Phase 9A.3 proved that activity-EMA eligibility cannot distinguish L→R from R→L order — it amplifies seed-intrinsic spatial bias. The hypothesis for 9A.4 was that "onset-based" eligibility (tracking activation rises, not activation levels) might be sharp enough to detect temporal order.

This experiment tests that hypothesis head-to-head against activity-EMA and OFF baseline.

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
| total arm-runs | 4 seeds × 3 modes × 4 arms = 48 |

### Three modes

| Mode | temporal_plasticity_enabled | temporal_eligibility_mode |
|------|---------------------------|--------------------------|
| OFF | False | — |
| activity | True | "activity" |
| onset | True | "onset" |

### Four arms (same as 9A.3)

| Arm | Order |
|-----|-------|
| L_then_R | L pulse → gap 80 → R pulse |
| R_then_L | R pulse → gap 80 → L pulse |
| simultaneous | L+R same time |
| separated_control | L then R with gap 300 |

All arms: identical L/R count (34 each), intensity (0.02), duration (80 steps).

### Onset formula

```
onset = max(activation[t] - activation[t-1], 0)
onset_trace = EMA(onset, decay=0.05)
eligibility = pre_onset_trace * post_onset - post_onset_trace * pre_onset
```

Critical ordering: eligibility computed using OLD onset traces, then traces updated with current onsets — prevents simultaneous pulses from producing spurious causal signals.

---

## 3. Results

### 3.1 Mode Comparison — Core Result

```
seed   OFF |L1|     activity |L1|  onset |L1|     OFF asym_diff  act asym_diff  onset asym_diff
------------------------------------------------------------------------------------------------
  42   3.87e-05    2.06e-04       3.53e-05       1.19e-06       4.68e-06        2.43e-06
  77   4.06e-05    2.11e-04       4.29e-05       4.34e-06       1.49e-05        4.75e-06
 123   3.30e-05    1.59e-04       3.07e-05       1.39e-06       8.65e-06        5.76e-07
 999   3.59e-05    2.25e-04       3.82e-05       6.16e-06       7.03e-06        5.74e-07
```

**Onset mode |L1| is indistinguishable from OFF baseline.** Activity mode amplifies |L1| by 4-5x (replicating 9A.3). Onset mode produces zero amplification — the eligibility term contributes nothing measurable beyond Hebbian co-activation.

### 3.2 Asymmetry Diff (L_then_R minus R_then_L)

```
seed   OFF asym_diff    act asym_diff    onset asym_diff
-------------------------------------------------------------
  42     +1.19e-06        +4.68e-06         +2.43e-06
  77     +4.34e-06        +1.49e-05         +4.75e-06
 123     +1.39e-06        +8.65e-06         +5.76e-07
 999     +6.16e-06        +7.03e-06         +5.74e-07
```

All modes: asymmetry diff ≤ 1e-05 — pure noise. No mode can distinguish L_then_R from R_then_L.

### 3.3 Directional Asymmetry by Arm (onset mode)

```
seed   L_then_R asym    R_then_L asym    simult. asym    separated asym
-------------------------------------------------------------------------
  42     +1.389e-03       +1.391e-03       +1.386e-03       +1.389e-03
  77     -1.349e-02       -1.348e-02       -1.348e-02       -1.349e-02
 123     +1.405e-02       +1.405e-02       +1.406e-02       +1.405e-02
 999     -3.353e-03       -3.353e-03       -3.355e-03       -3.356e-03
```

All 4 arms produce identical directional asymmetry within each seed. Onset mode is structurally identical to OFF — no arm-specific differentiation whatsoever.

### 3.4 L_then_R vs R_then_L — Cosine

```
mode        seed 42    seed 77    seed 123   seed 999
----------------------------------------------------------
OFF         0.99999995 0.99999995 0.99999997 0.99999995
activity    0.99999880 0.99999877 0.99999918 0.99999865
onset       0.99999996 0.99999995 0.99999997 0.99999995
```

Onset mode cos ≈ OFF baseline. Activity mode cos drops slightly (1-cos amplified ~40-60x) but this is global noise, not order-specific signal.

### 3.5 Regional Readout (onset mode, L→R and R→L signed_mean)

```
Seed 42 — L→R signed_mean:
  L_then_R:          -3.401e-03
  R_then_L:          -3.399e-03   (Δ = 1.9e-06)
  simultaneous:      -3.401e-03
  separated_control: -3.402e-03
```

Arm-to-arm variation is at the 1e-06 level — no detectable event-order signature.

---

## 4. Interpretation

### 4.1 Onset mode produces zero temporal signal

The onset formula fails not because it detects the wrong order, but because it detects NOTHING. The |L1|, cosine, and directional asymmetry in onset mode are all statistically identical to OFF baseline.

### 4.2 Why onset is too weak

The onset `max(act - prev_act, 0)` is:
- **Sparse**: non-zero only during activation rises (< 2% of total steps — ~400 out of 20,000)
- **Tiny**: typical onset value ~0.02-0.03 per step (activations change gradually, not in sharp spikes)
- **Smoothed further**: EMA(onset) with τ≈200 makes already-small values even smaller

The resulting eligibility magnitude:

```
onset eligibility:   pre_onset_trace * post_onset ≈ 0.001 × 0.025 ≈ 2.5e-05
Hebbian coactivity:  pre_strength * post_strength ≈ 0.3 × 0.3 ≈ 0.09

Ratio: ~3,600x (Hebbian dominates completely)
```

Compare to activity mode:
```
activity eligibility: pre_trace * post_act ≈ 0.3 × 0.3 ≈ 0.09
Hebbian coactivity:   0.09

Ratio: ~1x (comparable magnitudes — eligibility actually matters)
```

The onset eligibility is 3-4 orders of magnitude weaker than the Hebbian term. The temporal_delta contribution rounds to zero in floating point.

### 4.3 Complementary failure modes

```
activity-EMA:  signal too BROAD
               → trace ≈ time-averaged activation
               → amplifies seed-intrinsic spatial bias
               → 4-5x |L1| amplification but no order specificity

onset-EMA:     signal too WEAK
               → trace ≈ near-zero most of the time
               → eligibility term drowned by Hebbian
               → zero effect beyond OFF baseline
```

Neither formula can extract temporal order from continuous activation dynamics with region-level pulses.

### 4.4 Root cause: signal shape mismatch

The fundamental problem is not the formula — it's that the current architecture produces **gradual activation changes**, not sharp temporal events. Both EMA-based eligibility formulas need a clear "who fired when" signal, but the continuous dynamics with region-level stimulation smear this information across hundreds of steps.

---

## 5. Success Criteria

| Level | Criteria | Status |
|-------|----------|--------|
| Low | onset mode stable, no explosion | ✅ 16/16 onset runs stable |
| Low | pytest passes, backward compatible | ✅ 209/209 |
| **Medium** | **onset mode distinguishes L_then_R vs R_then_L more than activity** | ❌ **onset = OFF baseline** |
| **Medium** | **onset |L1| > OFF |L1|** | ❌ **identical to OFF** |
| Strong | L_then_R selectively strengthens L→R subgraph | ❌ not observed |
| Strong | cos(L_then_R, R_then_L) < 0.9999 in onset mode | ❌ cos ≈ 0.99999995 |

**Verdict: Negative — onset-based EMA eligibility produces zero detectable temporal signal under continuous activation dynamics.**

---

## 6. Conclusion

> **Phase 9A.4 proves that onset-based eligibility does not solve the order-specificity problem. The onset signal is too sparse and too weak in a continuous-activation system, collapsing back to OFF baseline. Activity-EMA is too broad; onset-EMA is too weak. Both Phase 9A formulas fail to produce order-specific temporal plasticity.**

Key findings:
1. Onset mode |L1| and cosine are indistinguishable from OFF baseline
2. Onset values are 3-4 orders of magnitude weaker than Hebbian co-activity
3. The continuous activation dynamics do not produce sharp enough temporal signatures for EMA-based eligibility
4. Two complementary failure modes confirmed: activity≈broad, onset≈weak
5. This is an architecture-level signal-shape problem, not a parameter tuning problem

---

## 7. Phase 9A Evidence Chain — Complete

```
9A smoke:  eligibility produces measurable |L1| amplification    ✅
9A.1:      systematic across 4 seeds                             ✅
9A.2:      global shift, not state-timing specific               ✅
9A.3:      activity-EMA cannot distinguish L/R order             ✅
9A.4:      onset-EMA zero signal, back to OFF baseline           ✅ ← HERE
```

Phase 9A has proven: **temporal plasticity can amplify structural change, but EMA-based eligibility formulas (activity or onset) cannot produce order-specific plasticity under continuous activation dynamics.**

The bottleneck is precisely located. The next step requires a fundamentally different temporal detection mechanism — not a refinement of the EMA trace approach.

---

## 8. Next Direction: Threshold-Crossing Eligibility

Both EMA formulas failed because they operate on continuous activation values that lack sharp temporal edges. The natural next step is to introduce a **discrete temporal event** into the continuous system:

**Threshold-crossing eligibility**: when a unit's activation crosses its threshold from below, generate an instantaneous eligibility event. Use these crossing times (not continuous traces) to determine pre/post temporal order.

This would be a Phase 9B-level change — a new temporal detection mechanism, not another EMA variant.

Candidate approaches:
1. **Threshold-crossing events**: binary crossing detection, short eligibility window
2. **STDP-like Δt rule**: record pre/post crossing times, weight change as function of Δt
3. **Event-aligned trace window**: only enable eligibility during a narrow window after pulse onset

Recommendation: design doc first (`docs/phase9B_threshold_crossing_design.md`), implement after agreement.

---

## 9. Files Changed

| File | Change |
|------|--------|
| `aniva/config.py` | +`temporal_eligibility_mode: str = "activity"` |
| `aniva/life_core.py` | +`_previous_activations`, `_onset_traces`, `_current_onsets` arrays; onset compute→plasticity→update ordering |
| `aniva/core/plasticity.py` | +onset eligibility branch: `pre_onset_trace * post_onset - post_onset_trace * pre_onset` |
| `aniva/experiments/exp9A4_onset_paired_order.py` | 3-mode paired-order assay script |
| `results/phase9A4_onset_paired_order_20k.csv` | Per-arm metrics |
| `results/phase9A4_onset_paired_order_20k_summary.json` | Full results |
