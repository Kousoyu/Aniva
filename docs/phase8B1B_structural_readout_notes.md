# Phase 8B.1B: Structural Readout Audit — 20k Notes

**Date:** 2026-05-05
**Status:** 完成
**Experiment:** `aniva/experiments/exp8B1_coupling_calibration.py` (updated with structural readout)

---

## 1. Purpose

Phase 8B.1A 120k showed sign flip (cl-ms wL1 opposite signs) in 2/4 seeds, but ΔwL1 magnitude was only ~1e-7 and did NOT grow from 20k to 120k.

Question: is the closed-loop structural signal hidden in local connection subgraphs, but averaged away by the global wL1 scalar?

8B.1B adds 12 structural readout metrics to check this without changing any mechanics.

---

## 2. Design

- 20k steps, Config A only, 4 seeds, 3 arms (ol/cl/ms)
- No mechanism changes — purely diagnostic
- Per-connection weight deltas classified by source/target region (L/R/midline)
- New metrics: regional L1, signed mean, pos/neg mass, top-k concentration, within/cross-region, delta vector cosine similarity

---

## 3. Results

### 3.1 Cross-Arm Delta Vector Cosine Similarity

| seed | cos(cl, ol) | cos(ms, ol) | cos(cl, ms) | |cl-ms|_L1 |
|------|-------------|-------------|-------------|------------|
| 42   | 1.000000    | 1.000000    | 1.000000    | 4.72e-5    |
| 77   | 1.000000    | 1.000000    | 1.000000    | 2.03e-5    |
| 123  | 1.000000    | 1.000000    | 1.000000    | 3.58e-5    |
| 999  | 1.000000    | 1.000000    | 1.000000    | 2.99e-5    |

**All cross-arm cosine similarities = 1.000000.**

The delta weight vectors for open_loop, closed_loop, and matched_shuffle all point in the SAME direction. The plasticity system has a dominant principal direction determined by the base event stream and initial topology. The closed-loop perturbation only modulates the MAGNITUDE of weight change along this direction, not the direction itself.

Even when global signed_mean flips sign between cl and ms (seeds 999, 123), the COSINE is still 1.0 — meaning the flip is a very subtle shift in the mean of a nearly-identical distribution, not a directional divergence.

### 3.2 Regional Decomposition

```
seed  arm        L1_global    signed      L→L        R→R        L→R        R→L
-------------------------------------------------------------------------------------
 42   open_loop  0.1952085  -5.140e-05  0.1962103  0.1956422  0.1953818  0.1933318
 42   cl         0.1952017  -4.997e-05  0.1962035  0.1956349  0.1953744  0.1933260
 42   ms         0.1952077  -5.218e-05  0.1962138  0.1956355  0.1953807  0.1933355

 77   open_loop  0.1975221  -2.607e-03  0.1962820  0.1974536  0.1991980  0.1958950
 77   cl         0.1975221  -2.607e-03  0.1962820  0.1974536  0.1991980  0.1958950
 77   ms         0.1975218  -2.607e-03  0.1962816  0.1974544  0.1991989  0.1958932

123   open_loop  0.1944339  -3.109e-04  0.1958175  0.1893692  0.1956439  0.1946606
123   cl         0.1944337  -3.113e-04  0.1958154  0.1893663  0.1956435  0.1946604
123   ms         0.1944356  -3.113e-04  0.1958276  0.1893664  0.1956451  0.1946643

999   open_loop  0.1967327  +1.145e-03  0.1970499  0.1969225  0.2009065  0.1922439
999   cl         0.1967290  +1.146e-03  0.1970459  0.1969211  0.2009037  0.1922425
999   ms         0.1967342  +1.145e-03  0.1970503  0.1969300  0.2009061  0.1922498
```

Regional differences between arms are on the order of 1e-6 to 1e-5 — same scale as the global effect. No individual region shows dramatically larger cl-ms divergence than the global wL1.

### 3.3 Within-Region vs Cross-Region

```
seed  arm        within_L1   cross_L1    within_signed  cross_signed
---------------------------------------------------------------------
 42   open_loop  0.1959296  0.1943612    ...            ...
 42   cl         0.1959225  0.1943545    ...            ...
 42   ms         0.1959281  0.1943624    ...            ...
```

Differences between arms in within-region and cross-region L1 are at the 1e-5 to 1e-6 scale — no amplification in either category.

---

## 4. Interpretation

### 4.1 No hidden signal

The structural readout does NOT reveal a hidden signal that the global wL1 missed. Every metric — regional L1, signed mean, pos/neg mass, within/cross-region, top-k concentration — shows the same picture:

> The plasticity system has a dominant direction of weight change determined by initial topology and base event structure. The closed-loop event perturbation is too weak to steer this direction; it can only slightly modulate the magnitude.

### 4.2 The cosine=1.0 finding is the key result

The delta vectors for all three arms point in the same direction to within 1e-6 cosine precision. This means:

- The base event stream "sets the rails" for plasticity
- State-timed label assignment only changes how fast the train moves, not which track it's on
- Even the sign flips (seeds 999, 123) are tiny mean-shifts of a nearly identical distribution, not directional divergence

### 4.3 What this means for the closed-loop hypothesis

The closed_loop mechanism (lr_imbalance → event bias → override) can change the EVENT DISTRIBUTION (ΔL_frac up to 0.03), but this change is too subtle to meaningfully steer the plasticity trajectory. The system's weight dynamics follow a path that is overwhelmingly determined by the base event structure (which is common to all arms).

In physical terms: the closed-loop is like a gentle breeze on a river. It can create ripples on the surface (event-level ΔL_frac), but it can't change the river's course (plasticity direction). The river's course is set by the riverbed (initial topology + base event stream).

---

## 5. Conclusion

**The bottleneck is real. There is no hidden structural signal.**

The closed-loop mechanism is connected and active, but the coupling from event perturbation → plasticity trajectory is too weak. The dominant plasticity direction is invariant across all three arms.

This finding clears the way for Phase 8B.2: stronger coupling. Finer readout instruments will not change the picture.

---

## 6. Next Step

Phase 8B.2: Coupling bandwidth smoke. Test whether higher gain/max_bias can break the cosine=1.0 lock:

```
A0: gain=2.5, max_bias=0.2  (baseline)
A1: gain=5.0, max_bias=0.3
A2: gain=8.0, max_bias=0.4
```

20k, Config A, seeds 42+999. If higher gain produces cos(cl, ms) < 0.999 or visible regional divergence, then 120k with the winning gain.
