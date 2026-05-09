# Phase 9A.1: Temporal Eligibility Trace — 20k 4-Seed Validation

**Date:** 2026-05-05
**Status:** 完成（中等成功，跨 seed 复现）

---

## 1. Purpose

Phase 9A 5k smoke showed that temporal eligibility trace produces a 4-5x amplification of |ol-cl|_L1 in seeds 42 and 999. 9A.1 validates whether this effect holds across 4 seeds (42, 77, 123, 999) at 20k steps.

---

## 2. Design

| Parameter | Value |
|-----------|-------|
| steps | 20,000 |
| seeds | 42, 77, 123, 999 |
| β (temporal_plasticity_rate) | 0.5 |
| τ (1/temporal_trace_decay) | 20 steps |
| arms | open_loop_poisson, closed_loop_triggered |
| modes | TEMPORAL OFF / ON per seed |

---

## 3. Results

### 3.1 TEMPORAL OFF — Baseline

```
seed   ol_ev  cl_ev  cos(ol,cl)      |ol-cl|_L1     1-cos
----------------------------------------------------------------
  42      97     15   0.99999993      4.73e-05       7e-08
  77      98     11   0.99999995      4.26e-05       5e-08
 123      99     18   0.99999994      4.56e-05       6e-08
 999     113      6   0.99999994      4.19e-05       6e-08
```

All 4 seeds in the 4-5e-05 baseline range. Consistent with Phase 8B.4 baseline. OFF mode confirmed stable.

### 3.2 TEMPORAL ON — β=0.5

```
seed   ol_ev  cl_ev  cos(ol,cl)      |ol-cl|_L1     1-cos       L1 ratio
----------------------------------------------------------------------------
  42      97      9   0.99999877      2.10e-04       1.2e-06     4.45x
  77      98     17   0.99999810      2.43e-04       1.9e-06     5.71x
 123      99     19   0.99999928      1.52e-04       7.2e-07     3.33x
 999     113      2   0.99999831      2.48e-04       1.7e-06     5.91x
```

**All 4 seeds show amplification.** Range: 3.33x – 5.91x.

### 3.3 Cross-Mode Summary

```
seed   |L1|_off     |L1|_on      L1_ratio   1-cos_off   1-cos_on   1-cos_ratio
---------------------------------------------------------------------------------
  42   4.73e-05    2.10e-04     4.45x       7e-08        1.2e-06     17x
  77   4.26e-05    2.43e-04     5.71x       5e-08        1.9e-06     38x
 123   4.56e-05    1.52e-04     3.33x       6e-08        7.2e-07     12x
 999   4.19e-05    2.48e-04     5.91x       6e-08        1.7e-06     28x
```

### 3.4 Same-Arm Temporal OFF vs ON |L1|

```
seed   open_loop_poisson    closed_loop_triggered
------------------------------------------------------
  42          3.23e-04              3.34e-04
  77          3.80e-04              3.94e-04
 123          2.24e-04              2.02e-04
 999          4.58e-04              3.91e-04
```

The same-arm off-vs-on |L1| (2-5e-04) is consistently LARGER than the on-mode ol-vs-cl |L1| (1.5-2.5e-04). This means temporal plasticity creates a strong global weight pattern shift, and the differential ol-vs-cl effect is a smaller signal superimposed on that shift.

### 3.5 Regional Readout

```
seed   temporal   arm          L_out-L_in    R_out-R_in    within-cross
------------------------------------------------------------------------
  42   OFF        ol           +1.002e-03    -1.724e-03    +1.567e-03
  42   OFF        cl           +1.002e-03    -1.724e-03    +1.567e-03
  42   ON         ol           +9.759e-04    -1.712e-03    +1.569e-03
  42   ON         cl           +9.801e-04    -1.721e-03    +1.584e-03
```

Regional asymmetry differences between ol and cl within the same mode are at the ~1e-5 level, even with temporal ON. No regional subgraph separation is observed at 20k.

### 3.6 System Stability

All 16 arm-runs show:
- ΔwL1: 0.195-0.197 (stable range)
- global_l1: consistent with ΔwL1
- No activation explosion
- No weight runaway
- Homeostasis active and functional

### 3.7 Trigger Rate Change with Temporal ON

```
seed   cl_ev OFF   cl_ev ON    change
----------------------------------------
  42       15          9         -6
  77       11         17         +6
 123       18         19         +1
 999        6          2         -4
```

Temporal plasticity modifies the trigger rate by altering the network's activity dynamics, which in turn changes lr_imbalance and the threshold-crossing behavior. The effect is seed-dependent — some seeds increase events, others decrease.

---

## 4. Interpretation

### 4.1 The eligibility effect is systematic, not coincidental

4/4 seeds show |L1| amplification (range: 3.33x – 5.91x). This confirms the 9A smoke signal is not specific to seeds 42 and 999 — it's a general property of the eligibility trace mechanism.

### 4.2 Seed-specific temporal sensitivity exists

Seed 123 shows the weakest amplification (3.33x), while seeds 77 and 999 show the strongest (5.71x, 5.91x). This variation is consistent with Phase 7/8 findings that topology-dependent sensitivity creates seed-specific responses to identical mechanisms.

### 4.3 The effect is primarily a global shift, not a differential one

The same-arm off-vs-on |L1| (~3e-04) is consistently larger than the ol-vs-cl |L1| in ON mode (~2e-04). This means temporal plasticity changes the weight pattern EVEN IN THE SAME EVENT SCHEDULE — the eligibility trace is doing work regardless of whether events are random or state-triggered. The differential effect (state-triggered vs random) is a smaller signal on top of the global temporal shift.

This makes physical sense: eligibility trace adds a new dimension to ALL plasticity updates, not just those during state-triggered events. The open_loop_poisson arm also has temporal structure (events at random times still have pre-post order), and the eligibility trace captures that.

### 4.4 Regional separation not yet visible

The L_out-L_in, R_out-R_in, and within-cross asymmetries differ between ol and cl by only ~1e-5 within a mode. At 20k steps, the temporal signal affects the global weight pattern but hasn't yet created detectable subgraph-level divergence.

### 4.5 Cos remains high — but for a different reason than Phase 8B

In Phase 8B, cos=1.0 because rate-based Hebbian couldn't distinguish temporal order at all. In Phase 9A, cos is still high (>0.99999) but for a different reason: the eligibility effect applies broadly to ALL connections (not specifically to state-timed events), so both arms shift in similar directions. The 15-40x increase in 1-cos means there IS a directional difference — it's just small relative to the dominant spatial pattern.

---

## 5. Success Criteria

| Level | Criteria | Status |
|-------|----------|--------|
| Low | OFF preserves baseline across all 4 seeds | ✅ |L1| ~4-5e-05 for all |
| Low | No numerical instability | ✅ 16/16 stable |
| **Medium** | **ON amplifies |L1| in all 4 seeds** | ✅ **4/4 seeds, 3.3-5.9x** |
| **Medium** | **ON amplifies 1-cos** | ✅ **12-38x** |
| Medium | Seed-specific sensitivity observed | ✅ seed 123 weakest (3.3x) |
| Strong | Regional subgraph separation | ❌ not yet at 20k |
| Strong | cos < 0.9999 | ❌ cos ~0.999998-0.999999 |
| Gold | cos < 0.99 | ❌ not yet |

Verdict: **Medium success — confirmed across all 4 seeds.**

---

## 6. Conclusion

> **Phase 9A.1 validates that temporal eligibility trace produces systematic, cross-seed structural amplification. The effect is not a 5k artifact or seed-specific coincidence.**

Key findings:
1. All 4 seeds show |L1| amplification (3.3-5.9x) with temporal ON
2. The effect is robust: even seed 123 (weakest) shows 3.33x
3. The global temporal shift (~3e-04 same-arm) is larger than the differential signal (~2e-04 ol-vs-cl)
4. Regional subgraph separation not yet visible at 20k
5. System remains stable across all 16 arm-runs

The eligibility trace is working as designed — it adds temporal sensitivity to plasticity. The next question is whether this sensitivity can be sharpened to create differential (rather than global) structural effects between state-timed and random-timed event schedules.

---

## 7. Next Direction Options

### A. Increase β to sharpen the differential signal

β=0.5 produces a global shift. Higher β (1.0 or 2.0) might amplify the differential component more than the global one, if the eligibility signal during state-triggered events has different structure than during random events.

### B. Increase temporal resolution (lower τ)

τ=20 steps might be too slow to distinguish state-timed from random-timed events. Lower τ (5-10 steps) would make the trace more sensitive to recent activation, potentially creating sharper eligibility signals during state-triggered events.

### C. Add matched_time_shuffle and circular_shift controls

The 9A.1 ol-vs-cl comparison is a coarse measure. Adding the matched_time_shuffle and circular_shift arms from 8B.4 would isolate whether the eligibility signal is specifically driven by state-timing correlation or just the event count/LR distribution.

### D. 120k long run

The 20k signal might accumulate at longer timescales. A 120k run could reveal whether the differential effect grows relative to the global shift, and whether regional separation eventually emerges.

Recommendation: combine A and C — sweep β (0.5, 1.0) with full 8B.4 4-arm structure at 20k. This isolates whether higher β sharpens the differential without needing a longer run.
