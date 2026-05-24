# Phase 10A.1 — Scheduler Plumbing Smoke Notes

> **定位：** event-generation plumbing only。
> 9C event-pair plasticity OFF。9D consolidation OFF。
> No structural plasticity claim。
> No digital-life / consciousness / personhood claim。

---

## 1. Summary

**Phase 10A.1 scheduler plumbing smoke completed under preregistered 10A.0 parameters.**

- Hard protocol: **2/2 seeds pass**
- Soft non-degeneration: **1/2 seeds pass**
- Overall verdict: **CAVEATED / PARTIAL PASS**, not clean pass.

Scheduler plumbing works: logs generated, no NaN, no crash, seeds produce
different event histories. Seed 77 violates preregistered none_rate lower bound
(0.27 < 0.30).

---

## 2. Frozen Parameters (from 10A.0)

| Parameter | Value |
|-----------|-------|
| seeds | 42, 77 |
| unit_count | 300 |
| total_steps | 7500 |
| warmup | 2000 |
| decision_interval | 500 |
| decision_points | 11 |
| event set | none, L, R, simultaneous |
| w | 5.0 |
| b_none | +1.0 |
| b_L | -1.5 |
| b_R | -1.5 |
| b_sim | -3.0 |
| τ | 1.0 |
| 9C event-pair plasticity | OFF |
| 9D consolidation | OFF |

---

## 3. Results

| Metric | Seed 42 | Seed 77 |
|--------|---------|---------|
| decisions | 11 | 11 |
| events | 5 | 8 |
| none_count | 6 | 3 |
| none_rate | 0.55 | **0.27** |
| L_count | 4 | 3 |
| R_count | 1 | 5 |
| simultaneous_count | 0 | 0 |
| n_unique_types | 2 | 2 |
| NaN | 0 | 0 |
| hard_pass | PASS | PASS |
| soft_pass | PASS | **FAIL** |

### Criteria Breakdown

| # | Criterion | Seed 42 | Seed 77 |
|---|-----------|---------|---------|
| P1 | no crash / NaN | PASS | PASS |
| P2 | event_log fields complete | PASS | PASS |
| B1 | event_count > 0 | PASS (5) | PASS (8) |
| B2 | 0.30 < none_rate < 0.90 | PASS (0.55) | **FAIL (0.27)** |
| B3 | n_unique_types ≥ 2 | PASS (2) | PASS (2) |

---

## 4. Interpretation

### 4.1 Scheduler Is State-Responsive

Different seeds produce different event counts (5 vs 8) and different
L/R distributions (4L/1R vs 3L/5R). The scheduler is not a static
random trigger — the state feedback path (activity → logit → probs → event)
is working.

### 4.2 Seed 77 Soft Fail

Seed 77's none_rate = 3/11 = 0.27 falls below the preregistered lower
bound of 0.30. The scheduler fired on 8 of 11 decision points.

Contributing factors:
- 11 decision points is coarse for a rate metric: shifting 1 decision
  from event to none would give 4/11 = 0.36, passing B2.
- The current θ (especially b_none=+1.0) produces a none probability
  that depends on the seed-specific activity distribution. Seed 77's
  dynamics produce activity levels that push logit_L/logit_R above
  logit_none more often.

### 4.3 No Simultaneous Events

b_sim = -3.0 is conservative. No simultaneous events triggered in
either seed. This is expected.

---

## 5. Policy: No Post-Hoc Tuning

Per 10A.0 preregistration:

- **Do not tune b_none post hoc.**
- **Do not rewrite the none_rate threshold.**
- **Do not rerun with adjusted parameters under the same config label.**
- Any change requires a new config variant (e.g. 10A.1B), committed as a
  separate config, not overwriting 10A.0.

---

## 6. Implication for Next Steps

The soft fail does not indicate mechanism failure. It indicates:

1. The current θ may be slightly too event-hot, especially for seeds
   with higher baseline activity.
2. 11 decision points makes the none_rate threshold coarse — a single
   decision can push the rate across the boundary.

Suggested paths (for separate config variants, not for retroactive editing):

- **10A.1B calibration variant A:** increase decision points
  (e.g. interval=250 → 22 points) to reduce threshold granularity
- **10A.1B calibration variant B:** increase b_none (e.g. +1.5) to
  raise the none baseline
- **10A.1B calibration variant C:** both

---

## 7. Boundary

- This is event-generation plumbing only.
- 9C event-pair plasticity was OFF.
- 9D consolidation was OFF.
- No structural plasticity was measured or claimed.
- No digital-life / consciousness / personhood claim is made.
- Seed 77 soft fail is reported as-is, not hidden or post-hoc fixed.
