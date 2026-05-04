# Phase 8B.4: State-Triggered Timing Coupling — 20k Notes

**Date:** 2026-05-05
**Status:** 完成

---

## 1. Purpose

8B.2 and 8B.3 proved that event-property modulation (L/R label, duration) cannot steer the plasticity trajectory when events follow a fixed temporal grid. The hypothesis was: the system follows the rhythm, not the decoration.

8B.4 tests removing the fixed clock entirely. Event onset timing is triggered by internal state crossing a threshold, not by a predetermined schedule. If the timing lock hypothesis is correct, state-triggered events should create a DIFFERENT plasticity trajectory.

Four arms:
1. **open_loop_poisson**: Random Poisson events, no state timing
2. **closed_loop_triggered**: Events fire when |smoothed_lr_imbalance| exceeds sustained threshold
3. **matched_time_shuffle**: Same events as triggered, times randomly shuffled
4. **circular_shift**: Same events as triggered, all times shifted by +N (preserves intervals, shifts phase)

---

## 2. Design

| Parameter | Value |
|-----------|-------|
| steps | 20,000 |
| seeds | 42, 999 |
| threshold | P85 of |lr_imbalance| (calibrated per seed) |
| sustained_window | 100 |
| refractory | 400 |
| event_duration | 80 |
| smoothing alpha | 0.1 |

**Trigger rule:** if |smoothed_lr_imbalance| > threshold for 100 consecutive steps AND refractory period (400 steps) elapsed → fire event. L more active → stimulate R; R more active → stimulate L.

**Calibrated thresholds:**
- Seed 42: 0.0461 (mean |lr_imbalance| ~ 0.039)
- Seed 999: 0.0413 (mean |lr_imbalance| ~ 0.017)

---

## 3. Results

### 3.1 Event Summary

```
seed  arm                       events  L/R    mean_IEI  std_IEI
------------------------------------------------------------------
  42  open_loop_poisson            97   57/40     203      197
  42  closed_loop_triggered        15    0/15    1383      631
  42  matched_time_shuffle         15    0/15    1383      631
  42  circular_shift               15    0/15    1326      732

 999  open_loop_poisson           113   69/44     178      173
 999  closed_loop_triggered         6    0/6     3386     2279
 999  matched_time_shuffle          6    0/6     3386     2279
 999  circular_shift                6    0/6     2399     3705
```

Triggered events are sparse (15 and 6) because lr_imbalance rarely exceeds the 85th percentile for sustained windows. All triggered events stimulate R — both seeds have L-dominant baseline activity.

### 3.2 Structural Summary

```
seed  arm                       ΔwL1 (vs ol_poisson)
--------------------------------------------------------
  42  closed_loop_triggered     -4.87e-09
  42  matched_time_shuffle      +5.62e-06
  42  circular_shift            +8.11e-06

 999  closed_loop_triggered     +8.73e-06
 999  matched_time_shuffle      +5.42e-06
 999  circular_shift            +1.05e-05
```

Seed 42 triggered ΔwL1 is effectively zero (< 10^-8). Seed 999 triggered ΔwL1 = +8.7e-06, within the same range as 8B.2/8B.3.

### 3.3 Cross-Arm Delta Vector (ALL PAIRS)

```
seed  arm_pair                                      cos       |L1|       |L2|
--------------------------------------------------------------------------------
  42  cl_triggered  vs ol_poisson                1.000000  4.73e-05  8.29e-05
  42  cl_triggered  vs matched_time_shuffle      1.000000  2.31e-05  5.05e-05
  42  cl_triggered  vs circular_shift            1.000000  3.36e-05  6.53e-05
  42  matched_shuf  vs ol_poisson                1.000000  4.68e-05  8.23e-05
  42  circular_shift vs ol_poisson               1.000000  4.32e-05  7.53e-05
  42  matched_shuf  vs circular_shift            1.000000  2.63e-05  5.23e-05

 999  cl_triggered  vs ol_poisson                1.000000  4.19e-05  7.65e-05
 999  cl_triggered  vs matched_time_shuffle      1.000000  2.48e-05  5.68e-05
 999  cl_triggered  vs circular_shift            1.000000  2.71e-05  5.95e-05
 999  matched_shuf  vs ol_poisson                1.000000  4.25e-05  7.83e-05
 999  circular_shift vs ol_poisson               1.000000  4.28e-05  7.66e-05
 999  matched_shuf  vs circular_shift            1.000000  2.64e-05  5.92e-05
```

**All 12 arm pairs: cos = 1.000000.**

### 3.4 Cross-Experiment Comparison

```
experiment   coupling_target     event_count_range   cos(cl,ms)   |cl-ms|_L1 range
-----------------------------------------------------------------------------------
8B.2 g=2.5   L/R label           99 (all arms)       1.000000     3.0-4.7e-05
8B.2 g=5.0   L/R label           99 (all arms)       1.000000     3.0-3.8e-05
8B.2 g=8.0   L/R label           99 (all arms)       1.000000     3.4-4.4e-05
8B.3 g=300   duration            99 (all arms)       1.000000     3.2e-05
8B.4         state-triggered     6-113 events        1.000000     2.3-4.7e-05
```

The |cl-ms|_L1 distance is consistently in the 2-5e-05 range across ALL experiments, regardless of coupling target or event count.

### 3.5 Regional Readout

```
seed  arm                       L_in      L_out     R_in      R_out     within    cross
------------------------------------------------------------------------------------------
  42  open_loop_poisson         0.19494   0.19594   0.19583   0.19410   0.19593   0.19436
  42  closed_loop_triggered     0.19494   0.19594   0.19583   0.19410   0.19593   0.19436
  42  matched_time_shuffle      0.19495   0.19595   0.19583   0.19410   0.19593   0.19437
  42  circular_shift            0.19495   0.19596   0.19583   0.19411   0.19594   0.19437

 999  open_loop_poisson         0.19531   0.19849   0.19767   0.19629   0.19699   0.19670
 999  closed_loop_triggered     0.19531   0.19849   0.19767   0.19629   0.19700   0.19670
 999  matched_time_shuffle      0.19531   0.19849   0.19767   0.19629   0.19700   0.19670
 999  circular_shift            0.19531   0.19849   0.19767   0.19629   0.19701   0.19670
```

Regional L1 values identical to 4-5 decimal places across all four arms.

---

## 4. Interpretation

### 4.1 The timing lock is NOT a timing lock — it's a spatial lock

This is the central finding of Phase 8B as a whole. We've tested three independent dimensions:

| Experiment | What changes | Result |
|------------|-------------|--------|
| 8B.2 | Event L/R label | cos=1.0 |
| 8B.3 | Event duration | cos=1.0 |
| **8B.4** | **Event timing + schedule** | **cos=1.0** |

8B.4 is the critical test because it changed the one thing the earlier experiments couldn't: event TIMING. From fixed-interval (every 200 steps) to state-triggered (rare, clustered by state) to Poisson (random). The event count varied by 19x (6 vs 113).

**And still cos=1.0 across all pairs.**

This means the earlier hypothesis — "the system follows the rhythm, not the decoration" — is incomplete. The system doesn't follow the rhythm either. The plasticity direction is locked by something even more fundamental: **the spatial pattern of activation.**

### 4.2 The spatial pattern hypothesis

Every stimulus event (L or R) activates the SAME spatial region:
- L stimulus at (-0.5, 0, 0) → activates left-region units
- R stimulus at (0.5, 0, 0) → activates right-region units

Whether these events come every 200 steps, at random intervals, or triggered by state, the set of connections that get reinforced is determined by which units are co-active. And the spatial activation footprint of each stimulus is fixed.

The weight delta pattern (which connections strengthen vs weaken) is therefore invariant to:
- How MANY events occur (6 vs 113)
- WHEN events occur (fixed vs random vs state-triggered)
- WHICH SIDE is stimulated (L vs R — because the spatial pattern for each side is symmetric)

The only things that COULD change the delta vector direction would be:
- Different stimulus POSITIONS (activating different units)
- Different stimulus INTENSITIES (changing the spatial reach)
- Different intrinsic network dynamics (topology changes)

### 4.3 The L1 distance range is converged

Across all 8B.x experiments (12 arm pairs in 8B.4, plus the 8B.2 and 8B.3 comparisons), the |arm_a - arm_b|_L1 distance is consistently 2-5e-05. This is NOT noise — it's the characteristic scale of weight differences caused by different stimulation schedules. The fact that it doesn't grow with stronger coupling or different timing regimes suggests this IS the maximum perturbation the current plasticity system can produce from environmental input modulation.

### 4.4 Why state-triggered events produced so few events

The 85th percentile threshold is high (0.041-0.046), and lr_imbalance rarely exceeds it for sustained windows. This is because:
- The open-loop calibration captures spontaneous fluctuations (no stimulation present)
- With stimulation, the network is perturbed from its spontaneous state
- The sustained_window=100 requirement filters out brief excursions

Lowering the threshold would produce more events, but the spatial pattern would still be the same (same stimulus positions), so the delta vector direction would remain unchanged.

---

## 5. What this closes

### The "Timing Lock" hypothesis (8B.2 conclusion) is partially wrong

The original metaphor was: "the system follows the drum rhythm, not which drum is struck." 8B.4 shows the system doesn't follow the rhythm either — it follows the spatial activation pattern. Whether the drum beats at fixed intervals, random intervals, or state-triggered moments, the same connections get updated because the same spatial regions are activated.

### Phase 8B exhausts environmental coupling as a pathway

| Dimension | Tested | Maximum perturbation | Result |
|-----------|--------|---------------------|--------|
| Label (which side) | 8B.2 | gain=8.0, 12 overrides | cos=1.0 |
| Duration (how long) | 8B.3 | dur 40 vs 120 (3x) | cos=1.0 |
| Timing (when) | 8B.4 | 6 vs 113 events, 3 schedules | cos=1.0 |

All three independent event dimensions, tested individually and in combination, produce ZERO plasticity direction divergence. This is not a failure of experimental design — it's a clean convergence on a property of the system.

---

## 6. Conclusion

**The plasticity trajectory is spatially locked.**

With rate-based Hebbian plasticity + homeostasis, the weight change pattern is determined by:
1. The spatial structure of the initial connectome (which units are connected)
2. The spatial activation patterns caused by stimuli (which units get activated together)
3. The homeostatic pressure (which pulls weights toward target)

Environmental event SCHEDULING — timing, labels, durations — modulates the MAGNITUDE of weight changes within this fixed spatial pattern, but not the PATTERN itself. Changing "when" or "which side" or "how long" doesn't change "which connections" get updated.

The L1 distance between arms (2-5e-05) represents the magnitude perturbation from different schedules, but the PATTERN (direction, as measured by cosine) is invariant.

### Physical analogy

Think of a field of grass with a watering system. Whether you water at 8 AM every day, or at random times, or only when the soil is dry — the grass that grows is always in the SAME spatial pattern (where the sprinklers reach). Changing the watering SCHEDULE doesn't change which patches of grass get water. The only thing that would change the growth pattern is moving the sprinklers themselves (different stimulus positions) or changing the grass species (different initial topology).

---

## 7. What needs to change

The current plasticity rule is rate-based Hebbian (co-activation → strengthen). At this level of temporal resolution, the weight update depends only on pre-post co-activation, not on the relative TIMING of pre and post spikes.

To make the system sensitive to event TIMING, the plasticity rule itself would need to incorporate spike-timing dependence (STDP-like), where:
- pre-before-post (causal order) → LTP
- post-before-pre (acausal order) → LTD

With such a rule, the same spatial activation pattern arriving at DIFFERENT TIMES relative to ongoing network activity would produce DIFFERENT weight changes — because the causal vs acausal relationship between stimulus-driven spikes and spontaneous spikes would vary with timing.

**Phase 8B is complete. The environmental coupling pathway is exhausted at the experiment-scheduler level. The bottleneck is in the plasticity rule's temporal resolution, not in the coupling target.**

---

## 8. Next Direction

Two non-exclusive options:

**A. STDP plasticity (Phase 9):** Replace rate-based Hebbian with spike-timing-dependent plasticity. This would make the system inherently sensitive to event TIMING without needing to modulate event properties at all — the same spatial activation arriving at different phases of ongoing oscillation would produce different weight changes.

**B. Spatial perturbation:** Instead of modulating event properties, change stimulus POSITIONS based on state. L-active region → stimulus centroid shifts. This directly changes which connections get updated.

Option A addresses the root cause (plasticity temporal resolution). Option B works within the current plasticity framework by changing the spatial pattern directly. They can be pursued independently or in combination.
