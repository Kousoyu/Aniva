# Phase 10A.0 — Pre-Registration

> **定位：** 实验开始前的正式注册。填死所有空位。
> 此文件在 10A.1 启动前 commit，之后不修改。
> 如果后续阶段需要改参数，应新建 config variant，不覆盖此文件。

---

## Research Question

Does a world-generated closed-loop event history induce structural
differentiation beyond (a) matched open-loop replay and
(b) shared nuisance baselines?

### Sub-Questions per Phase

| Phase | Question |
|-------|---------|
| 10A.1 | Can a parameterized stochastic scheduler produce varied, non-degenerate event histories without cheating? |
| 10A.2 | Do closed-loop events change fast weight trajectory relative to matched replay? |
| 10A.3 | Does closed-loop event history deposit into slow structure beyond matched replay? |
| 10A.4 | Are results reproducible across 4 seeds? |

---

## Design

### Arms

| Arm | Event Source | Present in |
|-----|-------------|-----------|
| closed_loop | parameterized stochastic scheduler from state | 10A.1+ |
| matched_open_loop_replay | exact replay of closed_loop event log, scheduler disabled | 10A.1+ |
| random_uniform_control | same expected event count, uniform random timing/type, scheduler disabled | 10A.2+ |
| simultaneous_geometry_control | combined L+R phi, fixed schedule (3 pairs, matching 9D.3) | 10A.3+ |
| no_event_control | no events, full step count | 10A.2+ |

### Seeds

- Pilot (10A.1, 10A.2, 10A.3 pilot): **42, 77**
- Formal (10A.3 formal, 10A.4): **42, 77, 123, 999**

### Horizon

- total_steps: **7500** (matching 9D.3 scale)
- warmup: **2000** (no decisions before warmup)
- decision_interval: **500** (11 decision points per run)
- pulse_duration: **80**

---

## Scheduler Contract

### Type: Parameterized Stochastic (Tier 2)

Not rule-based. Not online RL. Fixed θ, no learning.

### Allowed Inputs

```
obs = {
    "activity_L": float,  # mean unit activation, x < -0.1
    "activity_R": float,  # mean unit activation, x > 0.1
}
t: int                  # current step
history_view: HistView  # bounded window available at time t only
```

### Disallowed Inputs

- `arm_label` — scheduler is arm-agnostic
- future observations / post-hoc summaries / validation metrics
- `event_count` / event history / internal counters
- `slow_weight_cache`, `tag_cache`, `connections`, `_weight_cache`
- any field generated after decision time t

### Formula (Frozen)

```
logit_none = +1.0
logit_L    = +5.0 × activity_R − 1.5
logit_R    = +5.0 × activity_L − 1.5
logit_sim  = −3.0

probs = softmax([logit_none, logit_L, logit_R, logit_sim] / 1.0)
```

### Frozen Parameters

```
θ = {
    w:          5.0,
    b_none:    +1.0,
    b_L:       −1.5,
    b_R:       −1.5,
    b_sim:     −3.0,
    τ:         1.0,
}
```

θ is **frozen at commit time**. Changes require a new config variant
registered in a new commit, with rationale documented. The original
variant is never overwritten.

### Event Set

```
E = {none, L, R, simultaneous}
```

### RNG Separation

```
seed_env   = seed          # LifeCore init, environment noise
seed_sched = seed + 1000   # Scheduler RNG
```

---

## Primary Criteria

### 10A.1 — Scheduler Plumbing (Protocol Layer)

| # | Criterion | Threshold | Hard/Soft |
|---|-----------|-----------|-----------|
| P1 | no crash, no NaN | 0 | HARD |
| P2 | event_log all required fields present | 100% | HARD |
| P3 | scheduler input allowlist not violated | 0 violations | HARD |
| P4 | matched replay trace_hash exact | 0 mismatch | HARD |
| B1 | event_count > 0 | ≥ 1 | SOFT |
| B2 | none_rate in bounds | 30% < none_rate < 90% | SOFT |
| B3 | event type diversity | ≥ 2 types among non-none | SOFT |
| B4 | seed 42 ≠ seed 77 trace_hash | different | SOFT |

### 10A.2 — Fast Plasticity (Pilot, 2 seeds)

| # | Criterion | Threshold |
|---|-----------|-----------|
| P1–P4 | same as 10A.1 protocol layer | HARD |
| F1 | fast_weight differs from no_event baseline | qualitative |
| F2 | fast_weight difference not explainable by event count alone | matched control check |

### 10A.3 — Slow Consolidation (Pilot: 2 seeds | Formal: 4 seeds)

| # | Criterion | Threshold | Stage |
|---|-----------|-----------|-------|
| P1–P4 | same as 10A.1 protocol layer | HARD | all |
| S1 | corrected structural distance (closed vs replay) > 0 | measurable | pilot |
| S2 | S1 not explained by event count / intensity / total stimulus | matched control | pilot |
| S3 | |simultaneous_corrected_effect| ≤ ε_sim = 0.05 | pilot |
| S4 | |no_event_effect| ≤ ε_null = 1e-15 | pilot |
| S5 | ≥ 3/4 seeds direction-consistent | — | formal |

### 10A.4 — Formal Validation (4 seeds)

| # | Criterion | Threshold |
|---|-----------|-----------|
| P1–P4, S1–S5 | all above | HARD |
| F1 | bootstrap CI on seed-level corrected effect excludes 0 | ≥ 95% CI |

---

## Secondary Criteria（Reported, Not Gated）

- event_history_divergence(closed_loop, random_control): JS / Wasserstein
- repeated_vs_single ratio (if using repeated-pair comparison, 10A.3+)
- sign consistency across seeds: n_positive / n_seeds
- event count histogram per seed / per arm

---

## Stopping Rule

- **Fixed horizon.** total_steps = 7500, no early stopping.
- No interim peeking for significance.
- If run crashes (NaN, OOM, timeout), it is re-run with same seed+config.
  Re-run count is reported.
- No parameter tuning between seeds or between pilot and formal.

---

## Exclusion Rules

A seed's result is excluded from formal aggregate if:

1. `replay_hash_mismatch_count > 0`
2. `nan_count > 0`
3. event_log missing required fields
4. code_sha or config_sha mismatch with preregistered values

Exclusion is documented with reason. No silent exclusion.

---

## Claim Boundary

### A positive result means:

- Closed-loop event history produced a reproducible structural effect
  above matched replay and shared nuisance baselines.
- The effect is not attributable to event count, intensity, total stimulus,
  or geometry projection asymmetry alone.

### A positive result does NOT mean:

- Digital life validated.
- Consciousness, sentience, subjectivity, or personhood established.
- General intelligence or autonomous agency established.
- The system "understands" or "experiences" the world.
- The scheduler is optimal or adaptive — it is a fixed-θ stochastic policy.

---

## Diagnostics（Offline Only, Not Used for Pass/Fail）

- Ablation: disable feedback (use stale-state or random-state instead of current obs)
- Stale-state control: scheduler sees obs from t − Δ instead of current t
- OPE sanity check: if logged propensities available, evaluate a uniform-random
  policy on the logged data as sanity benchmark
- Geometry-aware correction: subtract simultaneous geometry baseline from
  directional metrics (reuse 9D.3 framework)

---

## Commit Checklist（Before 10A.1 Implementation Starts）

- [ ] This preregistration is committed with a tagged commit
- [ ] `docs/phase10A0_design_freeze.md` is committed
- [ ] Scheduler θ values are frozen in code as constants with a comment
      referencing this document
- [ ] Anti-cheat checklist (12 items) is reviewed and signed off
- [ ] CI passes on the preregistration commit
