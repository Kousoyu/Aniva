# Phase 10A.1B — Scheduler Calibration Variant Design

> **定位：** 注册一个 calibration variant，不改 scheduler θ，不改 10A.0 prereg，
> 不改 10A.1 结果。只换更细的刻度尺（decision_interval），看 seed77 soft fail
> 是否来自采样分辨率不足。

---

## 1. Background

### 10A.1 Recap

| Item | Result |
|------|--------|
| Commit | `67f28aa` |
| Hard protocol | **2/2 PASS** |
| Soft non-degeneration | **1/2 PASS** |
| Seed 42 | PASS (none_rate=0.55) |
| Seed 77 | **FAIL** (none_rate=0.27 < 0.30) |

### Seed 77 Failure Analysis

Seed 77's none_rate = 3/11 = 0.27 falls just below the preregistered lower
bound of 0.30. With 11 decision points, shifting a single decision from
event to none gives 4/11 = 0.36 — a 0.09 jump across the threshold.

The none_rate metric at 11 decision points has a granularity of 1/11 ≈ 0.091.
A criterion window of [0.30, 0.90] is 0.60 wide — but the gap between the
observed 0.27 and the threshold 0.30 is narrower than one decision unit.

**This does not mean the scheduler is broken.** It means the measurement
scale may be too coarse to distinguish "genuinely too event-hot" from
"one unlucky draw."

### Why Not Tune b_none First

b_none changes the scheduler's inherent preference — it shifts what the
scheduler *wants* to do. Decision interval changes the measurement scale —
it shifts how finely we *observe* what the scheduler does.

If we tune b_none first and it passes, we won't know whether:
- the scheduler was genuinely too event-hot, OR
- 11 points was too coarse to measure a fundamentally ok distribution.

If we increase decision points first:
- Pass → coarseness was the issue; θ is fine.
- Still fail → θ is genuinely too event-hot; next variant tunes b_none.

**Resolution before bias.**

---

## 2. Variant Rationale

10A.1B is a **calibration variant**, not a bug fix. It exists to answer
one narrow question:

> Does the 10A.1 seed77 soft fail persist when the none_rate metric
> is measured at finer temporal resolution?

The only change: `decision_interval: 500 → 250`.

Everything else — seeds, θ, horizon, event set, plasticity OFF, consolidation
OFF — is identical to 10A.1.

---

## 3. Frozen Parameters

### 3.1 Inherited from 10A.1 (Unchanged)

| Parameter | Value | Source |
|-----------|-------|--------|
| seeds | 42, 77 | 10A.0 |
| unit_count | 300 | 10A.0 |
| total_steps | 7500 | 10A.0 |
| warmup | 2000 | 10A.0 |
| pulse_duration | 80 | 10A.0 |
| 9C event-pair plasticity | OFF | 10A.0 |
| 9D consolidation | OFF | 10A.0 |

### 3.2 Scheduler θ (Unchanged)

| Parameter | Value |
|-----------|-------|
| w | 5.0 |
| b_none | +1.0 |
| b_L | -1.5 |
| b_R | -1.5 |
| b_sim | -3.0 |
| τ | 1.0 |

### 3.3 Changed from 10A.1

| Parameter | 10A.1 | 10A.1B |
|-----------|-------|--------|
| decision_interval | 500 | **250** |
| decision_points (expected) | 11 | **21** |

- `decision_points = (total_steps - warmup) / decision_interval`
- 10A.1B: (7500 − 2000) / 250 = 22 (exact) → 21 or 22 depending on off-by-one
- Decision points span from `warmup` to `total_steps` (exclusive) at interval steps

### 3.4 Scheduler Inputs (Unchanged)

```
Allowed:
  activity_L: float  # mean activation, x < -0.1
  activity_R: float  # mean activation, x > 0.1

Disallowed:
  arm_label, event_count, event history, weights, tags, connections,
  future observations, post-hoc metrics
```

### 3.5 RNG Separation (Unchanged)

```
seed_env   = seed          # LifeCore init
seed_sched = seed + 1000   # Scheduler RNG
```

---

## 4. Expected Impact of Decision Interval Change

### 4.1 Metric Granularity

| Variant | Points | none_rate granularity |
|---------|--------|----------------------|
| 10A.1 | 11 | ~0.091 |
| 10A.1B | 21-22 | ~0.048 |

At 21 points, the B2 criterion [0.30, 0.90] means:
- Lower bound 0.30 → at least ~6.3 none decisions (so ≥ 7 / 21)
- Upper bound 0.90 → at most ~18.9 none decisions (so ≤ 18 / 21)

The window accommodates 7–18 none decisions, a range of 12 possible
none counts — much finer than 10A.1's range of 4–9 (6 possible values
within [0.30, 0.90]).

### 4.2 Potential Outcomes

| Scenario | Interpretation |
|----------|---------------|
| Both seeds pass B2 | 10A.1 seed77 soft fail was coarseness artifact; 10A.1B becomes preferred plumbing config for 10A.2 |
| Seed77 still fails B2 | Scheduler θ is genuinely too event-hot for seed77 dynamics; next variant 10A.1C tunes b_none |
| Event count collapses (all-none or near-all-none) | Interval change interacts with state dynamics in unexpected way; investigate before 10A.2 |
| New failures appear (crash, NaN, etc.) | Decision interval change exposed a latent bug; fix separately, not under 10A.1B label |

### 4.3 What 10A.1B Does NOT Test

- Does NOT test whether b_none = +1.0 is the right value
- Does NOT test whether the scheduler formula is well-specified
- Does NOT test whether 7500 steps is enough horizon
- Does NOT enter 10A.2 (fast plasticity)
- Does NOT open 9C or 9D

---

## 5. Pass/Fail Criteria

### 5.1 Hard Protocol (HARD — any FAIL invalidates 10A.1B)

| # | Criterion | Threshold |
|---|-----------|-----------|
| P1 | No crash, no NaN | 0 |
| P2 | Event log all required fields present | 100% |
| P3 | 9C event-pair plasticity confirmed OFF | assert |
| P4 | 9D consolidation confirmed OFF | assert |
| P5 | Scheduler inputs: activity_L, activity_R only | code review |

### 5.2 Soft Non-Degeneration (SOFT — reported, not gated)

| # | Criterion | Threshold |
|---|-----------|-----------|
| B1 | event_count > 0 | ≥ 1 (per seed) |
| B2 | none_rate in bounds | 0.30 < none_rate < 0.90 (per seed) |
| B3 | Non-none event type diversity | ≥ 2 types across non-none events (per seed) |
| B4 | Seed 42 ≠ Seed 77 trace_hash | different |

### 5.3 Aggregate Reporting

- Report per-seed: none_rate, event_count, type distribution, pass/fail
- Report aggregate: n_hard_pass / n_seeds, n_soft_pass / n_seeds
- Do NOT average none_rate across seeds — each seed evaluates independently
- If one seed fails B2, the aggregate is CAVEATED, not CLEAN

---

## 6. Interpretation Rules (Locked Before Run)

1. **If 2/2 soft pass:** 10A.1 seed77 failure was likely a decision-count
   coarseness artifact. 10A.1B (interval=250) becomes the preferred plumbing
   config for 10A.2 and beyond.

2. **If seed77 still fails B2 (none_rate < 0.30):** The scheduler θ is
   genuinely too event-hot for seed77's activity distribution. The next
   variant (10A.1C) should adjust b_none upward (e.g., +1.5 or +2.0),
   with rationale documented. Do NOT adjust b_none under the 10A.1B label.

3. **If event_count collapses (all-none or near-all-none):** The shorter
   decision interval may interact with state dynamics — the system has less
   time to develop activity asymmetry between decisions, potentially shifting
   logit balances. Investigate with diagnostics before proceeding.

4. **If seed42 fails but seed77 passes:** Unexpected — both seeds should
   benefit from finer resolution. Report without post-hoc explanation.

5. **In all cases:** 10A.1 results are NOT retroactively edited. 10A.1B is
   a separate config variant with its own commit and its own result file.
   The original `none_rate=0.27` for seed77 in 10A.1 stands.

---

## 7. Anti-Cheat (Same as 10A.1)

- [ ] Scheduler function signature does not include `arm_label`
- [ ] Scheduler does not import plasticity or consolidation modules
- [ ] Scheduler does not access `_slow_weight_cache`, `_tag_cache`, `_weight_cache`
- [ ] Scheduler does not access `connections`
- [ ] Scheduler has no internal counter (does not count event_count)
- [ ] Event generation uses only `obs` + `sched_rng`
- [ ] `env_rng` and `sched_rng` independently initialized
- [ ] `sched_rng` seed recorded in event log
- [ ] Summary/metrics computed offline, not in step loop
- [ ] No `if arm == "closed_loop"` branch inside scheduler
- [ ] All config parameters frozen in dict, SHA256 recorded
- [ ] No parameter tuning after seeing results under 10A.1B label

---

## 8. Output Artifacts

| Artifact | Path |
|----------|------|
| Event log | `results/phase10A1B_scheduler_events.csv` |
| Summary CSV | `results/phase10A1B_scheduler_summary.csv` |
| Summary JSON | `results/phase10A1B_scheduler_summary.json` |
| Smoke notes | `docs/phase10A1B_scheduler_calibration_smoke_notes.md` |

---

## 9. Relationship to Other Configs

```
10A.0 prereg  ──→  10A.1 (interval=500, 11 pts)
                      │
                      ├── seed42: PASS
                      └── seed77: SOFT FAIL (none_rate=0.27)
                              │
                              ▼
                      10A.1B (interval=250, 21 pts)  ← THIS DOCUMENT
                              │
                              ├── 2/2 pass → 10A.1B becomes preferred config
                              └── still fail → 10A.1C (b_none adjustment)
```

10A.1B is a **calibration variant**, not a replacement for 10A.1.
Both results are reported. The better-performing config becomes the
baseline for 10A.2.

---

## 10. Boundary

- This is a scheduler plumbing calibration only.
- 9C event-pair plasticity remains OFF.
- 9D consolidation remains OFF.
- No structural plasticity claim.
- No digital-life / consciousness / personhood claim.
- 10A.0 preregistration is NOT modified.
- 10A.1 results are NOT overwritten.
- This document registers intent before any code is written or run.
