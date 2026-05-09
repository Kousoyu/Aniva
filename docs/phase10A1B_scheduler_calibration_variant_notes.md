# Phase 10A.1B — Scheduler Calibration Variant Notes

> **定位：** registered variant from `a18f59c`。只改 decision_interval，不改 θ。
> 9C event-pair plasticity OFF。9D consolidation OFF。
> No structural plasticity claim。
> No digital-life / consciousness / personhood claim。

---

## 1. Summary

**Phase 10A.1B scheduler calibration variant completed under registered parameters.**

- Hard protocol: **2/2 seeds pass**
- Soft non-degeneration: **2/2 seeds pass**
- Overall verdict: **CLEAN PASS**

This supports the interpretation that the 10A.1 seed77 soft fail was caused
by coarse decision resolution (11 points), not necessarily scheduler θ being
too event-hot. At 22 decision points, both seeds land comfortably within the
preregistered [0.30, 0.90] none_rate window.

10A.1B (interval=250) becomes the preferred plumbing config for 10A.2.
No 10A.1C b_none calibration variant is needed at this time.

---

## 2. Frozen Parameters

| Parameter | 10A.1 | 10A.1B |
|-----------|-------|--------|
| seeds | 42, 77 | 42, 77 |
| unit_count | 300 | 300 |
| total_steps | 7500 | 7500 |
| warmup | 2000 | 2000 |
| decision_interval | 500 | **250** |
| decision_points | 11 | **22** |
| pulse_duration | 80 | 80 |
| w | 5.0 | 5.0 |
| b_none | +1.0 | +1.0 |
| b_L | -1.5 | -1.5 |
| b_R | -1.5 | -1.5 |
| b_sim | -3.0 | -3.0 |
| τ | 1.0 | 1.0 |
| 9C event-pair plasticity | OFF | OFF |
| 9D consolidation | OFF | OFF |

---

## 3. Results

| Metric | Seed 42 | Seed 77 |
|--------|---------|---------|
| decisions | 22 | 22 |
| events | 12 | 11 |
| none_count | 10 | 11 |
| none_rate | 0.45 | **0.50** |
| L_count | 6 | 6 |
| R_count | 6 | 5 |
| simultaneous_count | 0 | 0 |
| n_unique_types | 2 | 2 |
| NaN | 0 | 0 |
| hard_pass | PASS | PASS |
| soft_pass | PASS | PASS |

### Criteria Breakdown

| # | Criterion | Seed 42 | Seed 77 |
|---|-----------|---------|---------|
| P1 | no crash / NaN | PASS | PASS |
| P2 | event_log fields complete | PASS | PASS |
| B1 | event_count > 0 | PASS (12) | PASS (11) |
| B2 | 0.30 < none_rate < 0.90 | PASS (0.45) | **PASS (0.50)** |
| B3 | n_unique_types ≥ 2 | PASS (2) | PASS (2) |

---

## 4. Comparison: 10A.1 vs 10A.1B

### Seed 42

| Metric | 10A.1 | 10A.1B |
|--------|-------|--------|
| decisions | 11 | 22 |
| events | 5 | 12 |
| none_rate | 0.55 | 0.45 |
| L/R | 4/1 | 6/6 |
| verdict | PASS | PASS |

### Seed 77

| Metric | 10A.1 | 10A.1B |
|--------|-------|--------|
| decisions | 11 | 22 |
| events | 8 | 11 |
| none_rate | **0.27 (FAIL)** | **0.50 (PASS)** |
| L/R | 3/5 | 6/5 |
| verdict | SOFT FAIL | PASS |

Seed 77's none_rate shifted from 0.27 (below 0.30) to 0.50 (mid-range)
purely by doubling the decision point count. The scheduler θ was identical
across both runs.

---

## 5. Interpretation

10A.1B supports the decision-resolution explanation for the 10A.1 seed77
soft fail. At 11 decision points, a single event vs none had a 0.09 impact
on none_rate; seed77 landing at 3/11 = 0.27 was within one decision unit of
the 0.30 boundary. At 22 points, the same scheduler dynamics produce
none_rate = 0.50, well within bounds.

Notably, seed77's event count increased only from 8 to 11 while decision
points doubled — the scheduler was not "firing every chance." The additional
decision points included more none outcomes, stabilizing the rate.

Both seeds show balanced L/R distributions in 10A.1B, compared to 10A.1's
more asymmetric splits. No simultaneous events triggered in either variant,
consistent with b_sim = -3.0.

---

## 6. Policy

- 10A.1 remains a **caveated/partial pass** — do not rewrite its result.
- 10A.1B is a **clean pass** under a separate registered config variant.
- 10A.1B (interval=250) becomes the **preferred plumbing config for 10A.2**.
- No 10A.1C b_none adjustment is needed at this time.
- 10A.0 preregistration is NOT modified.

---

## 7. Implication for Next Steps

With 10A.1B confirming that the scheduler plumbing works at adequate
measurement resolution, the next step is 10A.2:

- Open 9C event-pair fast plasticity for the first time
- Compare closed_loop vs matched_open_loop_replay
- Scheduler θ and decision_interval frozen from 10A.1B

---

## 8. Boundary

- This is scheduler plumbing calibration only.
- 9C event-pair plasticity was OFF.
- 9D consolidation was OFF.
- No structural plasticity was measured or claimed.
- No digital-life / consciousness / personhood claim is made.
- 10A.1 results are not overwritten.
- 10A.0 preregistration is not modified.
