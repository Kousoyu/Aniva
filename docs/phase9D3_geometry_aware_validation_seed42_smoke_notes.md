# Phase 9D.3 Geometry-Aware Validation — Seed=42 Smoke Notes

> **定位：** single-seed smoke positive，不是 4-seed formal validation。
> 9D.3 formal validation 仍是 future work。

---

## 1. Summary

**Phase 9D.3 seed=42 geometry-aware smoke passed. 14/14 PASS, POSITIVE verdict.**

Geometry-aware correction worked as designed: simultaneous corrected_DI ≈ 0.
Ordered repeated histories still show direction-correct excess over the shared
geometry baseline.

runtime ≈ 12.4 min (6 arms × ~120s + baseline).

---

## 2. Key Results

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| geometry_baseline_DI | +0.1635 | — | matches 9D.2C ref |
| corrected_LR_repeated | +0.0425 | >0 | PASS |
| corrected_RL_repeated | -0.6752 | <0 | PASS |
| corrected_slow_OS | +0.7177 | >0.3 | PASS |
| corrected_simultaneous | -0.0000 | \|DI\|<0.1 | PASS |
| no_event slow_l1 | 0.0 | <1e-15 | PASS |
| repeated/single LR | 6.12× | >3.0 | PASS |
| repeated/single RL | 6.12× | >3.0 | PASS |
| NaN | 0 | — | PASS |
| saturation | low | <5% | PASS |
| captures (active arms) | ≥6 | ≥1 | PASS |

**14/14 criteria passed.**

---

## 3. Interpretation

### 3.1 Geometry Correction Worked

simultaneous slow_DI = +0.1635
geometry_baseline_DI  = +0.1635
corrected_simultaneous = 0.0000

The +0.1635 bias is fully explained by the shared geometry baseline.
When subtracted, simultaneous control cleanly zeros out.

### 3.2 Directional Excess Confirmed

corrected_LR_repeated = +0.0425 > 0  → L→R event order → L→R direction
corrected_RL_repeated = -0.6752 < 0  → R→L event order → R→L direction
corrected_slow_OS      = +0.7177      → strong directional separation

Ordered repeated event histories produce additional slow-weight directionality
beyond what the shared geometry baseline alone predicts. The direction matches
the event order.

### 3.3 Directional Magnitude Asymmetry

|corrected_LR| (0.04) ≠ |corrected_RL| (0.68). This is expected:
phi_R_mass ≈ 1.8× phi_L_mass, so the two ordered arms experience different
effective stimulus masses. The design doc (v2) specifies directional magnitude
asymmetry as reported-not-gated for 9D.3 first validation.

### 3.4 Single-Pair Arms DI=±1.000

Single-pair arms (L_then_R_single, R_then_L_single) show extreme DI ±1.000
because only one event-pair update occurs, depositing all slow weight on a
single directional mask (contralateral l1=0). These arms are used only for
repeated > single ratio (6.12×), not as primary corrected direction criteria.

---

## 4. What This Means for 9D

| Stage | Status | Notes |
|-------|--------|-------|
| 9D.2 | caveated positive | simultaneous |DI|>0.1, root cause identified as geometry_projection_asymmetry |
| 9D.2C | diagnostic complete | raw_DI = dW_DI = +0.1635, root traced to trace×phi projection |
| 9D.3 seed=42 | **single-seed smoke positive** | geometry-aware correction works, directional excess confirmed |
| 9D.3 formal | future work | 4-seed ECS validation still needed |

---

## 5. Relation to 9D.2

9D.2 remains caveated positive. The 9D.2 simultaneous |DI| < 0.1 threshold
is NOT relaxed or changed post-hoc. 9D.3 uses a different framework
(corrected_slow_DI = slow_DI − geometry_baseline_DI) rather than relaxing
the 9D.2 threshold.

---

## 6. Boundary

- Single-seed smoke only — not formal validation
- 4-seed ECS formal validation remains future work
- 9D.4 NOT started
- No mechanism changes
- No parameter tuning
- 9D.2 conclusion unchanged
