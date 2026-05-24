# Phase 10A.3 — Closed-Loop Slow Consolidation Pilot Notes

> **定位：** 2-seed pilot。9C ON + 9D ON。结果收档。
> 不改 ε。不进入 10A.4。
> No digital-life / consciousness / personhood claim。

---

## 1. Summary

**Phase 10A.3 completed as 2-seed slow consolidation pilot.**

- Hard protocol: **2/2 PASS**
- Exact replay: **mirror reproduced** (closed_vs_exact_slow_l1 = 0.0)
- Perturbed replay: **no slow_weight divergence detected**
- Amplification ratio: **0.0** for both seeds
- Scientific signal: **NEGATIVE**

ε=0.02 activation perturbation is not captured or amplified by current
9D slow consolidation. The 9D capture mechanism (state-gated by energy ×
trace mass) is event-log-dominant at this perturbation scale.

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
| ε | 0.02 | 10A.2B.1 (frozen) |
| perturbation_target | activations only, t=0 once | 10A.2B.1 |
| perturbation_distribution | uniform [-ε, +ε], zero-mean, clip [0,1] | 10A.2B.1 |
| perturb_seed_offset | +3000 | 10A.2B.1 |
| 9C event-pair plasticity | ON | 10A.2 |
| 9D consolidation | ON | 10A.3 (first time in Phase 10) |
| 9D tag_tau | 5000.0 | AnivaConfig default |
| 9D capture_threshold | 0.5 | AnivaConfig default |
| 9D slow_weight_max | 0.1 | AnivaConfig default |
| 9D slow_weight_rate | 0.1 | AnivaConfig default |
| 9D refractory | 500 | AnivaConfig default |

---

## 3. Pre-Flight Checks

| Check | Result |
|-------|--------|
| py_compile | PASS |
| dry-run-schedule | PASS |
| estimate-only | seed42 ~302s, seed77 ~275s, total ~9.6 min |

---

## 4. Protocol Results

### 4.1 Hard Protocol

| # | Criterion | Seed 42 | Seed 77 |
|---|-----------|:---:|:---:|
| P1 | No NaN | PASS | PASS |
| P2 | No explosion (max_abs_w < 10) | PASS | PASS |
| P3 | Replay hash mismatch = 0 | PASS | PASS |
| P4 | Event count match | PASS (12/12/12) | PASS (12/12/12) |
| P5 | 9C ON, 9D ON confirmed | PASS | PASS |
| P6 | exact ≈ closed (mirror sanity) | PASS (Δ=0.0) | PASS (Δ=0.0) |

**Hard pass: 2/2.**

### 4.2 Replay Fidelity

| Check | Seed 42 | Seed 77 |
|-------|:---:|:---:|
| Trace hash match (exact vs closed) | `7703cc1bad4f5ff5` | `38efd91fb1912b1c` |
| Trace hash match (perturbed vs closed) | `7703cc1bad4f5ff5` | `38efd91fb1912b1c` |
| Event count (closed / exact / perturbed) | 12 / 12 / 12 | 12 / 12 / 12 |

---

## 5. Seed 42 Results

### 5.1 Per-Arm Metrics

| Metric | closed_loop | exact_replay | perturbed_replay | no_event |
|--------|-------------|--------------|------------------|----------|
| fast_weight_l1 | 1848.587960 | 1848.587960 | 1848.588220 | 1848.601988 |
| slow_weight_l1 | 0.00039344 | 0.00039344 | 0.00039344 | 0.0 |
| slow_weight_max_abs | 4.611e-05 | 4.611e-05 | 4.611e-05 | 0.0 |
| capture_count | 10 | 10 | 10 | 0 |
| tag_mass_final | 0.00069106 | 0.00069106 | 0.00069106 | 0.0 |
| n_tagged_connections | 42 | 42 | 42 | 0 |
| saturation_frac | 0.0 | 0.0 | 0.0 | 0.0 |
| max_abs_weight | 0.829 | 0.829 | 0.829 | 0.829 |
| nan_hit | False | False | False | False |

### 5.2 Cross-Arm Deltas

| Delta | Value |
|-------|-------|
| closed_vs_exact_slow_l1 | 0.0 |
| closed_vs_perturbed_slow_l1 | 0.0 |
| exact_vs_perturbed_slow_l1 | 0.0 |
| closed_vs_no_event_slow_l1 | 0.00039344 |
| amplification_ratio | **0.0** (fast ref = 0.00080134) |

---

## 6. Seed 77 Results

### 6.1 Per-Arm Metrics

| Metric | closed_loop | exact_replay | perturbed_replay | no_event |
|--------|-------------|--------------|------------------|----------|
| fast_weight_l1 | 1870.308868 | 1870.308868 | 1870.298935 | 1870.306806 |
| slow_weight_l1 | 0.00044013 | 0.00044013 | 0.00044013 | 0.0 |
| slow_weight_max_abs | 2.433e-05 | 2.433e-05 | 2.433e-05 | 0.0 |
| capture_count | 11 | 11 | 11 | 0 |
| tag_mass_final | 0.00065626 | 0.00065626 | 0.00065626 | 0.0 |
| n_tagged_connections | 79 | 79 | 79 | 0 |
| saturation_frac | 0.0 | 0.0 | 0.0 | 0.0 |
| max_abs_weight | 0.829 | 0.829 | 0.829 | 0.829 |
| nan_hit | False | False | False | False |

### 6.2 Cross-Arm Deltas

| Delta | Value |
|-------|-------|
| closed_vs_exact_slow_l1 | 0.0 |
| closed_vs_perturbed_slow_l1 | 0.0 |
| exact_vs_perturbed_slow_l1 | 0.0 |
| closed_vs_no_event_slow_l1 | 0.00044013 |
| amplification_ratio | **0.0** (fast ref = 0.00046194) |

---

## 7. Interpretation

### 7.1 Mirror Sanity Confirmed

exact_replay slow_l1 ≡ closed_loop slow_l1 to 8 decimal places for both
seeds. The 9D pipeline is deterministic under identical inputs — no
capture-timing nondeterminism, no tag-accumulation divergence, no
refractory-timing variance.

### 7.2 No Amplification

perturbed_replay slow_l1 ≡ closed_loop slow_l1 for both seeds.
amplification_ratio = 0.0.

The hairline fast-weight divergence from ε=0.02 (established in 10A.2B.1)
did not propagate into slow structure. Three reasons likely contribute:

1. **Capture is gated by aggregate state (energy × trace_mass), not
   individual weight differences.** A ~4×10⁻⁷ perturbation in total fast
   weight does not meaningfully shift these aggregate signals.

2. **Capture timing is dominated by event arrivals.** Events drive large
   trace × phi updates, which dominate the tag production and capture
   signal relative to Hebbian background.

3. **Refractory coarseness.** At 500-step refractory and 7500 total steps,
   max possible captures ≈ 15. With 10–11 actual captures, the system is
   operating near the ceiling — the refractory schedule may not leave
   enough headroom for state-context differences to shift capture timing.

### 7.3 Fast-Layer Divergence Still Exists

Although slow_weight is identical, fast_weight differs between perturbed
and closed in both seeds:

| Seed | closed fast_l1 | perturbed fast_l1 | Δ |
|------|---------------|-------------------|---|
| 42 | 1848.587960 | 1848.588220 | −0.000261 |
| 77 | 1870.308868 | 1870.298935 | +0.009933 |

Seed 77's fast Δ (0.00993) is larger than the 10A.2B.1 baseline
(0.00046), likely because 9D is now ON — slow_weight feedback alters the
effective synaptic landscape and thus the fast-weight trajectory. But even
this larger fast Δ did not shift capture timing.

### 7.4 What This Result Does NOT Mean

- Does NOT mean 9D is broken or invalid.
- Does NOT mean ε=0.02 was "too small" — it was preregistered and frozen.
- Does NOT mean the closed-loop feedback hypothesis is falsified.
- Does NOT justify post-hoc ε tuning to "find one that works."
- Does NOT justify skipping ε sensitivity and going straight to 10A.4.

---

## 8. Policy

- ε=0.02 remains frozen.
- 9D parameters remain at AnivaConfig defaults.
- This is a clean negative — not a crash, not a bug, not a protocol failure.
- Do not reinterpret this as "9C+9D pipeline doesn't work."
- Next step: ε sensitivity ladder (10A.2B.2) as diagnostic — not as a
  tool to select a "better ε."
- Do not enter 10A.4.

---

## 9. Relationship to Prior Evidence

| Phase | Key Finding | 10A.3 Relevance |
|-------|-------------|-----------------|
| 10A.2 | CLEAN NEGATIVE (exact replay ≡ closed) | Mirror confirmed inside 10A.3 |
| 10A.2B.1 | HAIRLINE POSITIVE (perturbed ≠ closed, ~4×10⁻⁷) | Fast Δ reference for amplification ratio |
| 10A.2B | Route B decision (10A.3 with ε=0.02) | This decision is now executed |
| 9D | Tag→capture→slow_weight pipeline validated | Pipeline is deterministic but state-insensitive at ε=0.02 |

---

## 10. Output Artifacts

| Artifact | Path |
|----------|------|
| Summary CSV | `results/phase10A3_summary.csv` |
| Events CSV | `results/phase10A3_events.csv` |
| Summary JSON | `results/phase10A3_summary.json` |
| Smoke notes | `docs/phase10A3_closed_loop_slow_consolidation_notes.md` |

---

## 11. Boundary

- 9C event-pair plasticity was ON.
- 9D consolidation was ON (first time in Phase 10 pipeline).
- ε=0.02 was frozen from 10A.2B.1.
- No post-hoc parameter tuning.
- No digital-life / consciousness / personhood claim.
- 10A.0 preregistration is NOT modified.
- 10A.2 CLEAN NEGATIVE is NOT challenged.
- 10A.2B.1 HAIRLINE POSITIVE is NOT inflated.
- 10A.2B decision (Route B) is executed and closed.
- This is a 2-seed pilot. 4-seed formal is 10A.4 — not entered.
