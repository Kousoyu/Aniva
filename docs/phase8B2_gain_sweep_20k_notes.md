# Phase 8B.2: Coupling Bandwidth Sweep — 20k Notes

**Date:** 2026-05-05
**Status:** 完成

---

## 1. Purpose

Phase 8B.1B structural readout showed that cross-arm delta vector cosine = 1.000000 for all arm pairs at gain=2.5. The closed-loop perturbation modulated magnitude but could not steer plasticity direction.

8B.2 tests whether higher feedback_gain can break this alignment.

---

## 2. Design

| Parameter | Value |
|-----------|-------|
| steps | 20,000 |
| seeds | 42, 999 |
| config | A only (interval=200, duration=80) |
| max_bias | 0.2 (fixed) |
| arms | open_loop / closed_loop / matched_shuffle |

Three gain levels:
- A0: gain=2.5 (baseline)
- A1: gain=5.0
- A2: gain=8.0

max_bias kept fixed at 0.2 to separate "gain insufficient" from "cap too narrow."

---

## 3. Results

### 3.1 Event-Level Summary

```
gain  seed  ΔL_frac     overrides   ΔwL1(cl)      ΔwL1(ms)      cl-ms sign
----------------------------------------------------------------------------
2.5    42   +0.0303      9          -6.82e-06      -7.53e-07      SAME (9x diff)
2.5   999   -0.0101      5          -3.67e-06      +1.56e-06      FLIP

5.0    42   -0.0505      9          -2.91e-06      +2.24e-06      FLIP
5.0   999   -0.0404      6          +1.29e-06      +7.54e-07      SAME (1.7x)

8.0    42   -0.0202     12          -2.01e-06      -3.35e-06      SAME (1.7x)
8.0   999   -0.0202      4          -1.09e-06      -3.20e-06      SAME (2.9x)
```

### 3.2 Config Ranking

```
gain    mean|ΔL_frac|   mean|ΔwL1|   cl-ms sign flips (/2)
----------------------------------------------------------
2.5     0.0202          5.25e-06      1 (seed 999)
5.0     0.0455          2.10e-06      1 (seed 42)
8.0     0.0202          1.55e-06      0
```

**ΔL_frac peaks at gain=5.0 but ΔwL1 monotonically DECREASES with gain.**

### 3.3 Cross-Arm Delta Vector

```
gain   seed   cos(cl, ol)   cos(ms, ol)   cos(cl, ms)   |cl-ms|_L1
-------------------------------------------------------------------
2.5     42    1.000000      1.000000      1.000000      4.72e-05
2.5    999    1.000000      1.000000      1.000000      2.99e-05
5.0     42    1.000000      1.000000      1.000000      3.80e-05
5.0    999    1.000000      1.000000      1.000000      3.02e-05
8.0     42    1.000000      1.000000      1.000000      4.36e-05
8.0    999    1.000000      1.000000      1.000000      3.41e-05
```

**cos(cl, ms) = 1.000000 at all gain levels.**

The delta vectors remain perfectly aligned regardless of coupling strength. Higher gain does not break the directional lock.

---

## 4. Interpretation

### 4.1 Higher gain does not amplify structural divergence

This is the central finding. Increasing feedback_gain from 2.5 to 8.0:

- Does NOT increase ΔwL1 magnitude (actually decreases it: 5.25e-6 → 1.55e-6)
- Does NOT increase cl-ms divergence (sign flips disappear at gain=8.0)
- Does NOT break cos=1.0 alignment (all cross-arm delta vectors remain perfectly parallel)

### 4.2 What this means

The L/R label bias pathway is fundamentally limited. Even when gain amplifies override probability, the net effect on the plasticity trajectory is bounded — and counterintuitively SHRINKS at higher gain.

The physical interpretation: stronger bias → more overrides → larger event distribution shift. But the larger shift introduces MORE event-level noise (frequent L/R flips) that averages out over the plasticity timescale. Moderate bias (gain=2.5) produces fewer but more coherent perturbations; aggressive bias (gain=8.0) produces more perturbations that partially cancel.

The delta vectors staying at cos=1.0 at ALL gain levels tells us that the plasticity system's dominant direction is determined by factors other than L/R event labels — likely the base event timing structure (event positions) and the initial topology.

### 4.3 The bias cap is active at gain=8.0

With lr_imbalance ~0.038 (seed=42), bias = 8.0 × 0.038 = 0.304, but max_bias=0.2 caps it at 0.2. At gain=5.0, bias ≈ 0.19 (uncapped). So the effective bias difference between gain=5.0 and 8.0 is minimal (0.19 vs 0.20).

But even gain=5.0 (uncapped) doesn't outperform gain=2.5 in structural metrics. The effective bias window is already explored with gain=2.5 (bias ~0.095, ~10% override) vs gain=5.0 (bias ~0.19, ~19% override). Both produce similar structural divergence.

---

## 5. Success Criteria Assessment

| Level | Criteria | Status |
|-------|----------|--------|
| Low | overrides increase with gain | ⚠️ Marginal (9→9→12 for seed 42) |
| Medium | |cl-ms|_L1 increases with gain | ❌ No trend |
| Strong | cos(cl, ms) < 1.0 | ❌ Failed — cos=1.0 at all gains |
| Failure | All metrics flat or negative with gain | ✅ Confirmed |

The sweep is a clear **failure** for the hypothesis that stronger L/R label coupling amplifies state-timed structural divergence.

---

## 6. Conclusion

**The L/R label bias pathway has reached its ceiling at gain=2.5.**

Increasing gain:
- Event-level changes (ΔL_frac) can grow (up to -0.05 at gain=5.0)
- But structural consequences (ΔwL1) do NOT grow — they shrink
- Sign flips between cl and ms disappear at higher gain
- The delta vector direction lock (cos=1.0) is unbreakable by L/R label perturbation alone

This is not an "insufficient force" problem. It is a "wrong lever" problem: changing which side gets stimulated (L/R) at event times, when the event TIMING structure is the dominant plasticity driver, cannot steer the plasticity trajectory away from its base direction.

### Physical analogy

The base event stream is like a drum beat — the TIMING of when the drum hits determines how the system resonates. The closed_loop mechanism only changes which drum (L or R) is struck at each beat. The system's weight dynamics follow the rhythm, not the drum choice. Turning up the volume (gain) doesn't change which drum is more important than the rhythm itself.

---

## 7. Next Direction

The L/R label bias pathway is exhausted. Two branching options:

**A. Change coupling target from label to timing.**

Instead of "which side gets stimulated," bias "when stimulation happens" or "how long it lasts":
- event_duration bias: lr_imbalance → duration modulation
- event_interval bias: lr_imbalance → gap modulation
- anomaly-style sustained perturbation with state-dependent onset

**B. Change coupling target from label to intensity.**

Instead of L/R binary, modulate stimulus intensity by region:
- L intensity = base × (1 + bias)
- R intensity = base × (1 - bias)
This directly changes the magnitude of regional activation, potentially having stronger plasticity impact than label swaps.

Timing-based coupling (option A) aligns better with the Phase 8A finding that duration and continuity are the effective dimensions for structural change.
