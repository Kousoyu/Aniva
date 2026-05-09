# Phase 9D.3 Geometry-Aware Validation — 4-Seed Formal Results

> **定位：** 4-seed ECS formal validation result。
> 不是 broader digital-life validation。不修改 9D.2 阈值。

---

## 1. Summary

**4/4 seeds (42, 77, 123, 999) — 14/14 PASS each — POSITIVE verdict.**

Geometry-aware correction worked across all seeds: simultaneous corrected_DI ≈ 0
for every seed, while ordered repeated histories consistently show direction-correct
excess over the shared geometry baseline.

ECS runtime: ~11 min wall time (4P parallel on ecs.c9i.xlarge, 4C8G).

---

## 2. Key Results

### 2.1 Per-Seed Summary

| Metric | Seed 42 | Seed 77 | Seed 123 | Seed 999 |
|--------|---------|---------|----------|----------|
| geometry_baseline_DI | +0.1635 | -0.1979 | -0.2840 | -0.3645 |
| corrected_LR_repeated | +0.0425 | +0.3723 | +0.6057 | +0.6546 |
| corrected_RL_repeated | -0.6752 | -0.2843 | -0.1317 | -0.0092 |
| corrected_slow_OS | +0.7177 | +0.6565 | +0.7374 | +0.6639 |
| corrected_simultaneous | -0.0000 | +0.0000 | +0.0000 | +0.0000 |
| repeated/single LR | 6.12× | 6.12× | 5.34× | 6.12× |
| repeated/single RL | 6.12× | 6.12× | 5.34× | 6.12× |
| NaN | 0 | 0 | 0 | 0 |
| Criteria | 14/14 | 14/14 | 14/14 | 14/14 |
| Verdict | POSITIVE | POSITIVE | POSITIVE | POSITIVE |

### 2.2 Criteria Summary

All criteria passed for all 4 seeds:

| Criterion | Seeds Passing |
|-----------|--------------|
| corrected_LR > 0 | 4/4 |
| corrected_RL < 0 | 4/4 |
| corrected_slow_OS > 0 | 4/4 |
| corrected_slow_OS > 0.3 | 4/4 |
| repeated > single LR | 4/4 |
| repeated > single RL | 4/4 |
| simultaneous corrected near zero | 4/4 |
| no_event clean | 4/4 |
| no NaN | 4/4 |
| no explosion | 4/4 |
| low saturation | 4/4 |
| captures present | 4/4 |
| slow below max | 4/4 |

---

## 3. Interpretation

### 3.1 Geometry Baseline Is Seed-Dependent

geometry_baseline_DI ranges from -0.3645 to +0.1635 across seeds. The sign and
magnitude depend on the seed-determined unit positions and connection topology.
This confirms that per-seed shared geometry baseline correction is necessary —
no single global constant can serve as the baseline across seeds.

### 3.2 Geometry Correction Works Across Seeds

For all 4 seeds, simultaneous corrected_DI ≈ 0.0000 (within floating-point
precision). The geometry baseline exactly accounts for the simultaneous arm's
slow_DI, demonstrating that the correction is correctly computed and applied.

### 3.3 Directional Excess Confirmed Across Seeds

All 4 seeds show:
- corrected_LR_repeated > 0 (range: +0.0425 to +0.6546)
- corrected_RL_repeated < 0 (range: -0.6752 to -0.0092)
- corrected_slow_OS > 0.3 (range: +0.6565 to +0.7374)

Ordered repeated event histories produce additional slow-weight directionality
beyond the geometry baseline in the direction matching event order.

### 3.4 Directional Asymmetry (Reported, Not Gated)

|Seed| corrected_LR | |corrected_RL| | Asymmetry |
|----|-------------|-----------------|-----------|
| 42 | +0.04 | 0.68 | RL-dominant |
| 77 | +0.37 | 0.28 | Balanced |
| 123 | +0.61 | 0.13 | LR-dominant |
| 999 | +0.65 | 0.01 | LR-dominant, RL borderline |

Seed 999 corrected_RL = -0.0092 is technically < 0 (PASS) but very close to
zero. This is consistent with the v2 design: directional magnitude asymmetry
is reported-not-gated. The mechanism produces direction-correct signal in all
seeds, but the magnitude balance between LR and RL directions varies with the
seed-dependent phi field geometry.

### 3.5 Repeated >> Single

All seeds show 5.34×-6.12× more slow mass in repeated vs. single-pair arms.
Consolidation accumulates across event pairs as expected.

---

## 4. Relation to 9D.2

| Aspect | 9D.2 | 9D.3 |
|--------|------|------|
| Status | caveated positive | **positive** |
| Seeds | 1 | **4** |
| simultaneous control | raw |DI| > 0.1 | corrected |DI| ≈ 0 |
| Metric | slow_DI, slow_OS | + corrected_slow_DI |
| Threshold changed? | — | No (new framework, not relaxed) |

9D.2 remains caveated positive. Its original |DI| < 0.1 threshold is not
retroactively changed. 9D.3 is a separate validation using a geometry-aware
framework that explains and corrects for the +0.1635 asymmetry.

---

## 5. Boundary

- 4 seeds passed. This is formal validation for 9D.3.
- Not broader digital-life validation.
- 9D.2 conclusion unchanged (caveated positive).
- No mechanism changes.
- No parameter tuning.
- Seed 999 borderline RL noted but not treated as failure.
- 9D.4 not started.

---

## 6. Files

| File | Description |
|------|-------------|
| results/phase9D3_geometry_aware_validation_seed{42,77,123,999}.csv | Per-seed arm-level results |
| results/phase9D3_geometry_aware_validation_seed{42,77,123,999}_summary.json | Per-seed full summary |
| results/phase9D3_geometry_aware_validation_seed{42,77,123,999}.log | Per-seed full log |
| aniva/experiments/exp9D3_geometry_aware_validation.py | Runner script |
| docs/phase9D3_geometry_aware_consolidation_validation_design.md | Design doc |
