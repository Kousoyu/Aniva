# Phase 10A.2B.2 — Epsilon Sensitivity Ladder Smoke Notes

> **定位：** diagnostic ladder completed。不是 tuning。
> 没有选择默认 ε。没有改 10A.3 结论。
> No digital-life / consciousness / personhood claim。

---

## 1. Summary

**Phase 10A.2B.2 epsilon sensitivity ladder completed on ECS.**

- Hard protocol: **8/8 PASS** (4 ε × 2 seeds, all pass)
- Mirror sanity: **confirmed at all ε** (exact ≡ closed)
- Slow signal: **NONE at all ε** (perturbed ≡ closed in slow_l1)
- Fast signal: **PRESENT at all ε** (perturbed ≠ closed in fast_l1)
- amplification_ratio: **0.0 across all ε**
- Diagnostic verdict: **9D capture is insensitive to initial-activation perturbation class at ε ≤ 0.05.**

The Scheme E perturbation route (initial activation perturbation) is
diagnostically exhausted. Larger fast-weight divergence does not translate
into capture timing or slow_weight differences.

---

## 2. Frozen Parameters

| Parameter | Value | Source |
|-----------|-------|--------|
| seeds | 42, 77 | 10A.0 |
| unit_count | 300 | 10A.0 |
| total_steps | 7500 | 10A.0 |
| warmup | 2000 | 10A.0 |
| decision_interval | 250 | 10A.1B |
| Scheduler θ | w=5.0, b_none=+1.0, b_L/R=-1.5, b_sim=-3.0, τ=1.0 | 10A.0 |
| 9C event-pair plasticity | ON | 10A.2 |
| 9D consolidation | ON | 10A.3 |
| ε ladder | [0.005, 0.01, 0.02, 0.05] | 10A.2B.2 design |
| perturbation_target | activations only, t=0 once | 10A.2B.1 |
| perturb_seed_offset | +3000 | 10A.2B.1 |
| ECS | 8.163.7.162, 4C8G Ubuntu 22.04 | — |

---

## 3. Pre-Flight & Runtime

| Check | Result |
|-------|--------|
| py_compile | PASS (ECS) |
| dry-run-schedule | PASS (ECS) |
| estimate-only | ~20 min (ECS) |
| Actual wall time | ~620s per seed (~10.3 min each) |
| Total ECS time | ~620s (parallel by seed) |

---

## 4. Hard Protocol Results

### 4.1 Per-ε, Per-Seed

| Seed | ε | P1 (NaN) | P2 (explosion) | P3 (hash) | P4 (events) | P5 (mirror) | Verdict |
|------|-----|:---:|:---:|:---:|:---:|:---:|:---:|
| 42 | 0.005 | OK | OK | OK | OK | OK | PASS |
| 42 | 0.01 | OK | OK | OK | OK | OK | PASS |
| 42 | 0.02 | OK | OK | OK | OK | OK | PASS |
| 42 | 0.05 | OK | OK | OK | OK | OK | PASS |
| 77 | 0.005 | OK | OK | OK | OK | OK | PASS |
| 77 | 0.01 | OK | OK | OK | OK | OK | PASS |
| 77 | 0.02 | OK | OK | OK | OK | OK | PASS |
| 77 | 0.05 | OK | OK | OK | OK | OK | PASS |

**Hard pass: 8/8.**

### 4.2 Replay Fidelity

All replay arms at all ε: trace hash match, hash_mismatches = 0, event count match.
Mirror sanity is robust across the full ε ladder — the 9D pipeline remains
deterministic regardless of the perturbation magnitude used for the
perturbed_replay arm (which uses a separate LifeCore instance and does not
affect the closed_loop instance).

---

## 5. Seed 42 — Per-ε Results

### 5.1 Slow Weight (Primary)

| ε | closed slow_l1 | exact slow_l1 | perturbed slow_l1 | slow Δ | amp_ratio |
|---|---------------|---------------|-------------------|--------|-----------|
| 0.005 | 0.00039344 | 0.00039344 | 0.00039344 | 0.0 | 0.0 |
| 0.01 | 0.00039344 | 0.00039344 | 0.00039344 | 0.0 | 0.0 |
| 0.02 | 0.00039344 | 0.00039344 | 0.00039344 | 0.0 | 0.0 |
| 0.05 | 0.00039344 | 0.00039344 | 0.00039344 | 0.0 | 0.0 |

Slow weight is **bit-identical** across all three arms at every ε.

### 5.2 Fast Weight

| ε | closed fast_l1 | exact fast_l1 | perturbed fast_l1 | fast Δ | perturb_l1 |
|---|---------------|---------------|-------------------|--------|------------|
| 0.005 | 1848.589202 | 1848.589202 | 1848.586018 | 0.003184 | 0.384 |
| 0.01 | 1848.589202 | 1848.589202 | 1848.583682 | 0.005520 | 0.767 |
| 0.02 | 1848.589202 | 1848.589202 | 1848.588219 | 0.000983 | 1.535 |
| 0.05 | 1848.589202 | 1848.589202 | 1848.583326 | 0.005876 | 3.837 |

Fast Δ exists at all ε but does not scale monotonically with ε.
perturb_l1 scales linearly with ε (as expected from uniform distribution).

### 5.3 Capture & Tag

| ε | captures (cl/ex/pe) | tag_mass | n_tagged | satur% |
|---|--------------------|----------|----------|--------|
| 0.005 | 10 / 10 / 10 | 0.000691 | 42 | 0.0 |
| 0.01 | 10 / 10 / 10 | 0.000691 | 42 | 0.0 |
| 0.02 | 10 / 10 / 10 | 0.000691 | 42 | 0.0 |
| 0.05 | 10 / 10 / 10 | 0.000691 | 42 | 0.0 |

Capture count, tag mass, and saturation are identical across all arms and ε.
No saturation ceiling hit.

---

## 6. Seed 77 — Per-ε Results

### 6.1 Slow Weight (Primary)

| ε | closed slow_l1 | exact slow_l1 | perturbed slow_l1 | slow Δ | amp_ratio |
|---|---------------|---------------|-------------------|--------|-----------|
| 0.005 | 0.00044013 | 0.00044013 | 0.00044013 | 0.0 | 0.0 |
| 0.01 | 0.00044013 | 0.00044013 | 0.00044013 | 0.0 | 0.0 |
| 0.02 | 0.00044013 | 0.00044013 | 0.00044013 | 0.0 | 0.0 |
| 0.05 | 0.00044013 | 0.00044013 | 0.00044013 | 0.0 | 0.0 |

Slow weight is **bit-identical** across all three arms at every ε.

### 6.2 Fast Weight

| ε | closed fast_l1 | exact fast_l1 | perturbed fast_l1 | fast Δ | perturb_l1 |
|---|---------------|---------------|-------------------|--------|------------|
| 0.005 | 1870.308744 | 1870.308744 | 1870.298631 | 0.010112 | 0.323 |
| 0.01 | 1870.308744 | 1870.308744 | 1870.299404 | 0.009340 | 0.646 |
| 0.02 | 1870.308744 | 1870.308744 | 1870.298935 | 0.009809 | 1.292 |
| 0.05 | 1870.308744 | 1870.308744 | 1870.306615 | 0.002129 | 3.231 |

Fast Δ exists at all ε. Seed 77 shows larger fast Δ than seed 42 at lower ε,
but does not scale monotonically.

### 6.3 Capture & Tag

| ε | captures (cl/ex/pe) | tag_mass | n_tagged | satur% |
|---|--------------------|----------|----------|--------|
| 0.005 | 11 / 11 / 11 | 0.000656 | 79 | 0.0 |
| 0.01 | 11 / 11 / 11 | 0.000656 | 79 | 0.0 |
| 0.02 | 11 / 11 / 11 | 0.000656 | 79 | 0.0 |
| 0.05 | 11 / 11 / 11 | 0.000656 | 79 | 0.0 |

---

## 7. Ladder-Wide Diagnostics

| Diagnostic | Seed 42 | Seed 77 |
|------------|---------|---------|
| slow Δ across ε | [0, 0, 0, 0] | [0, 0, 0, 0] |
| fast Δ across ε | [0.003, 0.006, 0.001, 0.006] | [0.010, 0.009, 0.010, 0.002] |
| amp_ratio across ε | [0, 0, 0, 0] | [0, 0, 0, 0] |
| capture Δ across ε | [0, 0, 0, 0] | [0, 0, 0, 0] |
| monotonic (slow Δ) | True (trivial) | True (trivial) |
| threshold ε | **None** | **None** |
| any slow signal | **False** | **False** |
| any fast signal | True | True |
| any saturation | False | False |

---

## 8. Interpretation

### 8.1 Primary Finding

**9D slow consolidation is insensitive to initial-activation perturbation
of class Scheme E at ε ≤ 0.05.**

Even at ε=0.05 (2.5× the frozen ε=0.02 from 10A.3), where ~3.2–3.8 L1
units of activation perturbation are applied at t=0, the 9D capture
mechanism produces:

- Identical slow_weight_l1
- Identical capture_count
- Identical tag_mass_final
- Identical n_tagged_connections

across closed_loop, exact_replay, and perturbed_replay.

### 8.2 Why

The 9D capture gate computes `signal = min(1, energy/0.3) × min(1, trace_mass/0.03)`.
Both energy and trace_mass are aggregate network-level quantities. A t=0
activation perturbation, even at ε=0.05, does not shift these aggregates
enough to change whether the signal crosses the 0.5 threshold at any
decision point.

The event arrival dynamics dominate both energy and trace_mass. Events
drive large phi updates → large dW → large tag production → tag
accumulation → capture. The perturbation's effect on this chain is
below the detection threshold of the capture mechanism.

### 8.3 Fast Layer vs. Slow Layer

Fast Δ exists at all ε — the perturbation propagates through the 9C
plasticity pipeline and produces measurable fast-weight divergence.
But this divergence exists at the connection level and does not
aggregate into the state-level signals that gate 9D capture.

This confirms the 10A.3 finding and extends it: it's not that ε=0.02
was "too small" — even ε=0.05 with 10× more perturbation L1 (3.84 vs
0.38) produces zero slow signal.

### 8.4 What This Result Means

- **Scheme E (initial activation perturbation) is diagnostically
  exhausted** as a route to slow-structure divergence under current
  9D parameters.
- The 9D capture mechanism is robust to this perturbation class —
  a valid architectural property, not a failure.
- The closed-loop feedback hypothesis is not falsified — only the
  Scheme E perturbation class is exhausted.

### 8.5 What This Result Does NOT Mean

- Does NOT mean 9D is broken.
- Does NOT mean ε=0.05 should become the default.
- Does NOT mean the closed-loop event-feedback hypothesis is wrong.
- Does NOT mean ε=0.10 would work (and it's not tested).
- Does NOT justify post-hoc 9D parameter tuning.
- Does NOT justify entering 10A.4.

---

## 9. Policy

- ε ladder completed as diagnostic. No ε value selected.
- Scheme E perturbation route is exhausted. Do not re-run with larger ε.
- Do not tune capture_threshold, refractory, slow_weight_max, or tag_tau.
- 10A.3 CLEAN NEGATIVE stands unchanged.
- 10A.2B.1 HAIRLINE POSITIVE stands unchanged.
- Next step: new design document for alternative approach to slow-structure
  divergence — not a larger ε, not 9D parameter sweep.

---

## 10. Decision Rules Reference

Per the 10A.2B.2 design:

| Rule | Condition | Action |
|------|-----------|--------|
| #5 | All ε negative | Abandon Scheme E as primary route. New design document needed. |

Rule #5 is triggered. All ε ∈ {0.005, 0.01, 0.02, 0.05} produce slow Δ = 0.

---

## 11. Relationship to Evidence Chain

| Phase | Key Finding | 10A.2B.2 Relevance |
|-------|-------------|-------------------|
| 10A.2B.1 | ε=0.02 hairline positive in fast layer | Fast divergence confirmed at all ε |
| 10A.3 | ε=0.02 + 9D → clean negative | Extended: ε ≤ 0.05 all negative |
| 10A.2B.2 design | Diagnostic ladder, not tuning | Executed as designed |
| 10A.2B decision | Fallback: "if 10A.3 negative, ε ladder" | Fallback executed and closed |

---

## 12. Output Artifacts

| Artifact | Path |
|----------|------|
| Seed 42 summary CSV | `results/phase10A2B2_epsilon_ladder_seed42.csv` |
| Seed 77 summary CSV | `results/phase10A2B2_epsilon_ladder_seed77.csv` |
| Seed 42 events CSV | `results/phase10A2B2_epsilon_ladder_seed42_events.csv` |
| Seed 77 events CSV | `results/phase10A2B2_epsilon_ladder_seed77_events.csv` |
| Seed 42 JSON | `results/phase10A2B2_epsilon_ladder_seed42_summary.json` |
| Seed 77 JSON | `results/phase10A2B2_epsilon_ladder_seed77_summary.json` |
| Seed 42 log | `logs/phase10A2B2_epsilon_ladder_seed42.log` |
| Seed 77 log | `logs/phase10A2B2_epsilon_ladder_seed77.log` |
| Smoke notes | `docs/phase10A2B2_epsilon_sensitivity_ladder_notes.md` |

---

## 13. Boundary

- 9C event-pair plasticity was ON.
- 9D consolidation was ON.
- ε ∈ {0.005, 0.01, 0.02, 0.05}. No ε=0.10.
- No ε value was selected as default.
- No 9C/9D parameters were tuned.
- Scheduler θ was frozen.
- This is a diagnostic result, not a tuning exercise.
- Scheme E perturbation class is exhausted.
- 10A.3 negative stands.
- No digital-life / consciousness / personhood claim.
