# Phase 9A.2: Temporal Eligibility — 4-Arm Timing Controls

**Date:** 2026-05-05
**Status:** 完成（中间结果：机制有效，特异性不足）

---

## 1. Purpose

Phase 9A.1 proved that temporal eligibility trace amplifies |ol-cl|_L1 by 3-6x across all 4 seeds. But 9A.1 only compared open_loop_poisson vs closed_loop_triggered — a coarse measure. The amplification could come from two sources:

1. **Global temporal plasticity shift**: eligibility trace changes ALL weight updates, regardless of event schedule
2. **State-timed feedback specificity**: eligibility trace specifically amplifies the signal when events fire at state-aligned moments

9A.2 disambiguates these with a full 4-arm design.

---

## 2. Design

| Parameter | Value |
|-----------|-------|
| steps | 20,000 |
| seeds | 42, 77, 123, 999 |
| β (temporal_plasticity_rate) | 0.5 |
| τ (1/temporal_trace_decay) | 20 steps |
| arms | open_loop_poisson, closed_loop_triggered, matched_time_shuffle, circular_shift |
| modes | TEMPORAL OFF, TEMPORAL ON |
| total arm-runs | 4 seeds × 2 modes × 4 arms = 32 |

### Four arms

| Arm | Event source | Timing structure |
|-----|-------------|------------------|
| open_loop_poisson | Poisson process (mean interval 200) | Random, no state feedback |
| closed_loop_triggered | |smoothed_lr_imbalance| > P85 threshold | State-aligned |
| matched_time_shuffle | Same events as triggered | Times shuffled (preserves counts, destroys state alignment) |
| circular_shift | Same events as triggered | Times shifted by +N/2 (preserves intervals, destroys state alignment) |

### Key comparisons

- **closed vs matched**: same events, different times — tests whether state-aligned TIMING matters
- **closed vs circular**: same events, shifted times — orthogonal test of timing specificity
- **matched vs circular**: two non-state-aligned schedules — baseline for ON-mode arm differences

---

## 3. Results

### 3.1 TEMPORAL OFF — Baseline

All 24 arm pairs (6 pairs × 4 seeds) at cos ≈ 0.99999993–0.99999999, |L1| = 1.7–4.7e-05. Consistent with Phase 8B.4 baseline. OFF mode is fully locked. ✓

```
seed   cl vs ms |L1|    cl vs cs |L1|    ms vs cs |L1|
--------------------------------------------------------------
  42      2.31e-05         3.36e-05         2.63e-05
  77      2.29e-05         4.08e-05         4.05e-05
 123      1.69e-05         3.07e-05         3.06e-05
 999      2.48e-05         2.71e-05         2.64e-05
```

### 3.2 TEMPORAL ON — The Real Test

```
seed   cl vs ms |L1|    cl vs cs |L1|    ms vs cs |L1|    ol vs cl |L1|
---------------------------------------------------------------------------
  42      1.86e-04         2.30e-04         2.15e-04         2.10e-04
  77      1.88e-04         1.93e-04         1.95e-04         2.43e-04
 123      9.12e-05         1.50e-04         1.43e-04         1.52e-04
 999      2.06e-04         2.18e-04         2.08e-04         2.48e-04
```

All arm pairs elevated 5-10x vs OFF baseline. But within ON mode, no clear hierarchy — closed does NOT separate from matched/circular more than other pairs separate from each other.

Seed 123 is particularly telling: cl-vs-ms (9.12e-05) is the LOWEST |L1| among all 6 ON pairs. Closed and matched are the MOST similar arms in that seed, not the least.

### 3.3 Global Shift vs Differential Signal

```
seed   same-arm off→on L1    ON cl-ms L1    ON cl-cs L1    ratio (ms/global)
---------------------------------------------------------------------------------
  42        3.30e-04           1.86e-04        2.30e-04           0.56
  77        3.92e-04           1.88e-04        1.93e-04           0.48
 123        2.08e-04           9.12e-05        1.50e-04           0.44
 999        4.16e-04           2.06e-04        2.18e-04           0.49
```

The same-arm OFF→ON |L1| (global temporal shift) is consistently 2x larger than the ON-mode cross-arm |L1|. The eligibility trace pushes ALL arms in a similar direction, and the differences between arms within ON mode are smaller than the overall shift from OFF to ON.

### 3.4 Regional Readout (ON mode, cl minus ms)

```
seed   L→L_diff      R→R_diff      L→R_diff      R→L_diff
------------------------------------------------------------------
  42   +6.10e-06     +8.95e-06     -3.57e-06     +1.25e-05
  77   +1.12e-06     -2.34e-05     +7.42e-06     -3.36e-05
 123   +1.24e-05     +4.86e-07     +1.08e-05     +1.36e-06
 999   -4.28e-06     -3.05e-06     +1.12e-05     -1.00e-05
```

No consistent pattern. Regional differences between closed and matched are at the 1e-05 level — same magnitude as OFF-mode noise. No subgraph-level state-timing signature detected.

### 3.5 Event Counts

```
seed   TEMPORAL OFF              TEMPORAL ON
       ol    cl    ms    cs       ol    cl    ms    cs
---------------------------------------------------------
  42    97    15    15    15       97     9     9     9
  77    98    11    11    11       98    17    17    17
 123    99    18    18    18       99    19    19    19
 999   113     6     6     6      113     2     2     2
```

ms and cs preserve cl's event count by design. The trigger rate change between OFF and ON is seed-dependent (same as 9A.1 observation).

---

## 4. Interpretation

### 4.1 Eligibility produces a global shift, not state-timing specificity

The core finding of 9A.2 is negative but informative:

> **Temporal eligibility amplifies structural differences between ALL arm pairs equally. It does not specifically amplify the signal from state-timed events.**

In TEMPORAL ON mode, the |L1| between any two arms (closed vs matched, matched vs circular, ol vs closed, etc.) is in the same range. The eligibility trace is doing temporal work, but that work is not tuned to the specific temporal structure of state-triggered vs random-timed events.

### 4.2 Why this happens

The eligibility trace captures pre/post firing order:

```
eligibility = pre_trace * post_act - pre_act * post_trace
```

This signal depends on the spatial activation dynamics — which units fire in what order. In all four arms, the same stimulus positions (left/right) activate the same unit populations. The spatial activation sequence (which hemisphere fires before the other, cross-hemisphere propagation delays) is similar regardless of event timing, because the network's intrinsic dynamics dominate over the sparse external events.

Therefore: **same spatial activation order → similar eligibility signal → similar weight change pattern → global shift, not differential.**

### 4.3 The ratio tells the story

The ms/global ratio (0.44–0.56) means cross-arm differences in ON mode are always smaller than the OFF→ON shift itself. If state-timing specificity existed, we would expect cl-vs-ms to be LARGER than some other ON pairs, or at least comparable to the global shift. Neither is observed.

### 4.4 1-cos comparison

```
seed   OFF cl-ms 1-cos    ON cl-ms 1-cos    increase
----------------------------------------------------------
  42      2e-08             1.1e-06            55x
  77      2e-08             1.3e-06            65x
 123      1e-08             3.6e-07            36x
 999      3e-08             1.3e-06            43x
```

1-cos increases 36-65x from OFF to ON. But this is directional noise amplification, not state-timing decoding — because the same increase appears for ALL arm pairs (matched-vs-circular shows similar 1-cos increase).

---

## 5. Success Criteria

| Level | Criteria | Status |
|-------|----------|--------|
| Low | OFF preserves baseline (all arm pairs locked) | ✅ all cos≈1.0, |L1|~2e-05 |
| Low | No numerical instability | ✅ 32/32 stable |
| Medium | ON amplifies |L1| for cross-arm pairs | ✅ 5-10x vs OFF |
| **Medium** | **closed separates from matched/circular more than other pairs** | ❌ **not observed** |
| **Medium** | **cl-ms |L1| > global shift** | ❌ **ratio 0.44-0.56** |
| Strong | Regional subgraph differentiation (cl vs ms) | ❌ at ~1e-05 noise level |
| Gold | cos(cl,ms) < 0.9999 | ❌ cos ~0.999998-0.999999 |

**Verdict: Medium success — mechanism confirmed, specificity not yet achieved.**

---

## 6. Conclusion

> **Phase 9A.2 proves that temporal eligibility trace amplifies structural differences, but the amplification is a global plasticity shift, not state-timed feedback specificity. Temporal sensitivity exists. State-timed specificity is not yet isolated.**

Key findings:
1. TEMPORAL ON elevates ALL cross-arm |L1| by 5-10x — eligibility is real and measurable
2. But closed_loop_triggered does NOT separate from matched_time_shuffle or circular_shift more than other arm pairs
3. The global OFF→ON shift (~3-4e-04) dominates the ON-mode cross-arm differences (~1-2e-04)
4. Seed 123 is a clear counterexample: cl-vs-ms is the LOWEST |L1| among ON pairs
5. Regional subgraph readout shows no consistent differentiation

The eligibility trace acts as a global temporal plasticity modifier — it changes how ALL weight updates respond to temporal order, regardless of whether events are state-timed or random. This is because the spatial activation dynamics (who fires before whom) are similar across all event schedules.

---

## 7. Next Direction: Phase 9A.3 Paired-Order Assay

9A.2 shows the eligibility trace can't distinguish state-timed from random-timed events in a complex closed-loop world. But the root question is more fundamental:

> **Can the eligibility formula itself distinguish "L fires before R" from "R fires before L"?**

Phase 9A.3 should test this directly with a minimal, controlled assay:

- **Arm A**: L stimulus pulse → delay → R stimulus pulse
- **Arm B**: R stimulus pulse → delay → L stimulus pulse
- **Arm C**: simultaneous L+R pulse

All arms matched for total stimulus count, intensity, and duration. Only temporal ORDER differs.

This isolates the eligibility formula's directional sensitivity before reconnecting to the complex closed-loop world.

If 9A.3 CAN distinguish order → connect mechanism back to closed-loop.
If 9A.3 CANNOT distinguish order → eligibility formula or trace dynamics need revision.

---

## 8. Files

| File | Role |
|------|------|
| `aniva/experiments/exp9A2_timing_controls.py` | Experiment script |
| `results/phase9A2_timing_controls_20k.csv` | Per-arm metrics |
| `results/phase9A2_timing_controls_20k_summary.json` | Full results with readout |
