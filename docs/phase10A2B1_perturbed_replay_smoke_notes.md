# Phase 10A.2B.1 — Perturbed Initial State Replay Smoke Notes

> **定位：** Scheme E design freeze (ε=0.02) 已执行。
> 不改 10A.2 结论。不调 ε。不开 9D。
> No digital-life / consciousness / personhood claim。

---

## 1. Summary

**Phase 10A.2B.1 completed under frozen Scheme E design.**

- Hard protocol: **2/2 PASS**
- Exact replay: **mirror result reproduced** (closed_vs_exact = 0.0)
- Perturbed replay: **measurable micro-divergence detected**
- Overall verdict: **hairline positive / measurable micro-divergence,**
  not strong fast-layer feedback-context effect.

---

## 2. Frozen Parameters

| Parameter | Value |
|-----------|-------|
| seeds | 42, 77 |
| total_steps | 7500 |
| warmup | 2000 |
| decision_interval | 250 |
| ε | **0.02** |
| perturbation target | activations only, t=0 once |
| perturbation distribution | uniform [-ε, +ε], zero-mean, clip [0,1] |
| perturb_seed_offset | +3000 |
| 9C event-pair plasticity | ON |
| 9D consolidation | OFF |
| Scheduler θ | w=5.0, b_none=+1.0, b_L/R=-1.5, b_sim=-3.0, τ=1.0 |

---

## 3. Results

### 3.1 Per-Arm Fast Weight L1

| Arm | Seed 42 | Seed 77 |
|-----|---------|---------|
| closed_loop | 1848.58977647 | 1870.30457022 |
| exact_replay | 1848.58977647 | 1870.30457022 |
| perturbed_replay | 1848.58897513 | 1870.30503216 |

### 3.2 Cross-Arm Deltas

| Delta | Seed 42 | Seed 77 |
|-------|---------|---------|
| closed − exact | **0.0** | **0.0** |
| closed − perturbed | **+0.00080134** | **−0.00046194** |
| exact − perturbed | +0.00080134 | −0.00046194 |

### 3.3 Perturbation & State Propagation

| Metric | Seed 42 | Seed 77 |
|--------|---------|---------|
| perturb_l1 (applied ε at t=0) | 1.53 | 1.29 |
| act_div at warmup end (closed vs perturbed) | 0.0912 | 0.0027 |
| act_div at warmup end (closed vs exact) | 0.0 | 0.0 |

### 3.4 Protocol

| Check | Seed 42 | Seed 77 |
|-------|:---:|:---:|
| No NaN | ✅ | ✅ |
| No explosion (max_abs_w < 10) | ✅ | ✅ |
| Replay hash_mismatch = 0 | ✅ (both arms) | ✅ (both arms) |
| Event count match | ✅ (12/12/12) | ✅ (11/11/11) |
| closed events (L/R/sim) | 6/6/0 | 6/5/0 |
| none_rate | 0.45 | 0.50 |

---

## 4. Interpretation

### 4.1 Mirror Reproduced

`closed_l1 == exact_l1` to 8 decimal places for both seeds. The deterministic
mirror under same seed / same initial state / same event log is confirmed
within the same run as the perturbation test.

### 4.2 Hairline Crack Detected

`perturbed_l1 ≠ closed_l1` for both seeds. The t=0 activation perturbation
(ε=0.02) propagated through 2000 warmup steps and reached the 9C plasticity
pipeline, producing measurable fast weight divergence.

### 4.3 Effect Size Is Extremely Small

| Scale | Value |
|-------|-------|
| Total fast weight L1 | ~1.85 × 10³ |
| Perturbation-induced Δ | ~5–8 × 10⁻⁴ |
| Effect / total ratio | ~4 × 10⁻⁷ |

The effect is measurable but 4 orders of magnitude below the total fast
weight scale. The 9C event-pair plasticity pipeline remains strongly
event-log-dominant.

### 4.4 Seed-Specific State Propagation

Seed 42 showed 30× larger activation divergence at warmup end than seed 77
(0.091 vs 0.003), but only ~1.7× larger fast weight delta. State divergence
does not linearly translate to 9C plasticity divergence — the pipeline is
robust to activation-level differences as long as the event log is identical.

### 4.5 What This Result Does NOT Mean

- Does NOT prove feedback context is important at fast layer scale.
- Does NOT mean ε=0.02 was "too small" — it was preregistered.
- Does NOT justify post-hoc ε tuning.
- Does NOT justify immediate entry to 10A.3.

---

## 5. Policy

- ε=0.02 is frozen. Do not tune.
- This is a hairline positive, not a strong positive.
- 10A.2 CLEAN NEGATIVE is not challenged or overwritten.
- Do not enter 10A.3 based only on this result.
- Next step: write a decision note (10A.2B next-step) before any further
  experiment — epsilon sensitivity variant vs. 10A.3 with redesigned replay.

---

## 6. Boundary

- 9C event-pair plasticity was ON.
- 9D consolidation was OFF.
- Perturbation was ε=0.02, activations only, t=0 once.
- No post-hoc parameter tuning.
- No digital-life / consciousness / personhood claim.
- 10A.0 preregistration is NOT modified.
- 10A.2 results are NOT overwritten.
