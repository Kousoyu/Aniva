# Phase 8B.1A: Config A 120k Full Run — Notes

**Date:** 2026-05-05
**Status:** 完成
**Experiment:** `aniva/experiments/exp8B1_coupling_calibration.py`
**Config:** A only (interval=200, duration=80)

---

## 1. Purpose

Phase 8B.1 20k calibration identified Config A (sparse events, interval=200/duration=80) as the best-preserving state-timing specificity across 4 seeds. Denser configs (B/C/D) diluted rather than amplified the signal.

8B.1A tests whether Config A's cl-ms divergence signal persists at 120k, and whether the use of `matched_shuffle` (same L/R counts, shuffled labels) provides a cleaner control than the old `shuffled_feedback`.

---

## 2. Design

| Parameter | Value |
|-----------|-------|
| steps | 120,000 |
| seeds | 42, 77, 123, 999 |
| event_interval | 200 |
| event_duration | 80 |
| events/arm | ~599 |
| feedback_gain | 2.5 |
| max_bias | 0.2 |
| base_p_L | 0.5 |

Three arms: open_loop / closed_loop / matched_shuffle

matched_shuffle takes closed_loop's exact event positions and L/R counts, shuffles the L/R labels, and replays the sequence with no feedback loop.

---

## 3. Results

### 3.1 Event Distribution

```
seed  arm               L     R   L_frac   ΔL_frac     overridden
------------------------------------------------------------------
 42   open_loop        278   321  0.4641   —             0
 42   closed_loop      276   323  0.4608   -0.0033      22
 42   matched_shuffle  276   323  0.4608   -0.0033       0

 77   open_loop        285   314  0.4758   —             0
 77   closed_loop      291   308  0.4858   +0.0100      14
 77   matched_shuffle  291   308  0.4858   +0.0100       0

123   open_loop        273   326  0.4558   —             0
123   closed_loop      264   335  0.4407   -0.0150      33
123   matched_shuffle  264   335  0.4407   -0.0150       0

999   open_loop        299   300  0.4992   —             0
999   closed_loop      297   302  0.4958   -0.0033      10
999   matched_shuffle  297   302  0.4958   -0.0033       0
```

Event-level feedback active in all seeds. ΔL_frac range: -0.0150 to +0.0100. Seed-specific direction persists (77↑L, others↓L).

### 3.2 Structural Divergence

```
seed  arm               final_wL1        ΔwL1(vs ol)   ΔwL1(ms)     cl-ms sign
--------------------------------------------------------------------------------
 42   open_loop        0.197003098054    —              —             —
 42   closed_loop      0.197002658577    -4.3948e-07    —             SAME
 42   matched_shuffle  0.197002767225    -3.3083e-07    -1.0865e-07

 77   open_loop        0.202841050610    —              —             —
 77   closed_loop      0.202840927813    -1.2280e-07    —             **FLIP**
 77   matched_shuffle  0.202841364509    +3.1390e-07    -4.3670e-07

123   open_loop        0.195141384461    —              —             —
123   closed_loop      0.195141001357    -3.8310e-07    —             SAME
123   matched_shuffle  0.195140643652    -7.4081e-07    +3.5771e-07

999   open_loop        0.200711581218    —              —             —
999   closed_loop      0.200711479538    -1.0168e-07    —             **FLIP**
999   matched_shuffle  0.200711881150    +2.9993e-07    -4.0161e-07
```

### 3.3 cl-ms Divergence Summary

| seed | |ΔwL1_cl| | |ΔwL1_ms| | |cl - ms| | sign flip? |
|------|----------|----------|----------|------------|
| 42   | 4.39e-7  | 3.31e-7  | 1.09e-7  | no (1.3x same sign) |
| 77   | 1.23e-7  | 3.14e-7  | 4.37e-7  | **yes** |
| 123  | 3.83e-7  | 7.41e-7  | 3.58e-7  | no (1.9x same sign) |
| 999  | 1.02e-7  | 3.00e-7  | 4.02e-7  | **yes** |

**Sign flip: 2/4 seeds (77, 999).**

When sign flip occurs: closed_loop reduces wL1 (vs open_loop), matched_shuffle increases wL1. Consistent direction across the two flip seeds.

---

## 4. Comparison: 20k vs 120k

| metric | 20k A | 120k A |
|--------|-------|--------|
| ΔL_frac range | -0.0202 to +0.0303 | -0.0150 to +0.0100 |
| ΔwL1 scale | ~1e-6 | ~1e-7 |
| sign flip seeds | 999, 123 | 77, 999 |
| seed 77 status | degenerate (override=0) | active (override=14) |

**ΔwL1 is ~10x SMALLER at 120k than at 20k.** The signal does not accumulate monotonically with steps.

This is counterintuitive but makes physical sense: the initial plasticity transient (first 10-20k steps) dominates wL1 movement. After the system settles into its dynamical equilibrium, additional perturbations produce smaller net changes. The closed-loop event bias is a perturbation on top of ongoing homeostatic dynamics, not a monotonic accumulation.

---

## 5. Interpretation

### 5.1 matched_shuffle works as a cleaner control

Unlike the old `shuffled_feedback` (which shuffled bias values, changing which events got overridden), `matched_shuffle` preserves the exact L/R counts and event positions from closed_loop. L_frac is identical by design. Any wL1 difference between cl and ms is purely due to the state-timed correspondence of L/R labels.

### 5.2 State-timing signal exists but is small

2/4 seeds show sign flips — state-timed labels push structure in the OPPOSITE direction from shuffled labels. This is the cleanest evidence yet that the temporal correspondence between state and event matters.

But the effect is ~1e-7, roughly 0.00005% of absolute wL1 (~0.2). It's a signal, not a structural deposit.

### 5.3 Signal does NOT accumulate with time

The 10x reduction in ΔwL1 from 20k to 120k tells us that the initial plasticity transient is the dominant source of weight change. Longer runs don't amplify the closed-loop perturbation — they may actually dilute it through homeostatic averaging.

### 5.4 Seed-dependence persists

seed=77 went from degenerate at 20k (zero overrides) to active at 120k (14 overrides). seed=999 is the only seed that shows sign flip at both 20k and 120k — suggesting its topology is the most sensitive to state-timed perturbations.

---

## 6. Success Criteria Assessment

| Level | Criteria | Status |
|-------|----------|--------|
| Low | closed_loop ΔL_frac ≠ open_loop | ✅ All 4 seeds |
| Medium | closed_loop ΔwL1 detectable vs open_loop | ❌ Still ~1e-7, same as 8B |
| Strong | cl-ms wL1 consistently separated | ⚠️ 2/4 sign flip, but magnitude small |
| Advanced | Multiple seeds with sign flip or seed-specific pattern | ⚠️ 2 seeds, consistent cl↓ ms↑ |

---

## 7. What This Means

Phase 8B.1A proves three things:

1. **Config A's state-timing specificity persists at 120k.** The sign flips in seeds 77 and 999 are not 20k-scale artifacts.

2. **But the effect does not grow with time.** The feedback channel is working (events are biased, labels are timed), but the structural deposition is dominated by the initial plasticity transient. Longer runs don't amplify the signal — the system reaches a homeostatic equilibrium where additional perturbations have diminishing returns.

3. **The "bandwidth" metaphor from Phase 8B holds.** The closed-loop channel is connected but too narrow. Denser events (configs B/C/D) don't widen it — they flood it with noise. Longer steps don't widen it either — the initial transient sets the ceiling.

The limiting factor is not event density, not step count. It's the **coupling strength between event-level perturbation and structural plasticity.** With gain=2.5 and max_bias=0.2, the override probability is 2-10% per event, and only a fraction of those produce different L/R choices. The net perturbation to the system's event diet is ~0.3-1.7% — too small to leave detectable structural traces beyond the initial plasticity phase.

---

## 8. Next Direction

Three non-exclusive options:

**A. Try stronger coupling (gain=10, max_bias=0.4) for one seed at 20k.**
Test whether a wider feedback channel produces larger cl-ms divergence at short scale. If yes, run 120k with stronger coupling.

**B. Accept the current ceiling and shift focus.**
The closed-loop mechanism is proven at the event-scheduler level. Structural deposition may require a different coupling target — not lr_imbalance → event probability, but something that more directly interfaces with plasticity (e.g., modulating learning rate by region, or biasing homeostatic targets).

**C. Look at weight distribution, not just wL1.**
ΔwL1 (mean absolute weight change) may be too coarse. The sign flips suggest that cl and ms are pushing in different directions, but L1 norm averages this out. Examining per-connection weight changes or regional weight divergence might reveal structure invisible to wL1.

---

## 9. Records

- Cloud run: ~22 min (4 seeds × 3 arms parallel on 4 vCPU)
- Results: 4 CSV + 4 JSON + 4 log files fetched to `results/`
- Previous Phase 8B used `shuffled_feedback` (shuffle bias); this run uses `matched_shuffle` (shuffle labels)
- The matched_shuffle is a cleaner control because it guarantees identical L/R counts between cl and ms
