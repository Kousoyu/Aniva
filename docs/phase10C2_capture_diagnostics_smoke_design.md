# Phase 10C.2 — Capture Diagnostics Smoke Design

**Status:** Design only. No implementation. No experiment run.
**Depends on:** 10C.1 instrumentation (commit `ea028a7`)
**Branch:** `phase10-closed-loop-event-history`

---

## 1. Purpose

10C.1 added six read-only context metrics to the 9D consolidation ledger.
10C.2 is the first live firing of those sensors: run a 10A.2C-style four-arm
replay under `consolidation_diagnostics_enabled=True` and ask whether the
metrics reveal context differences that the existing gate cannot see.

The gate is not changed. Capture timing is not changed. slow_weight transfer
is not changed. This step is purely observational.

---

## 2. Background

### Route A result (10A.2C)

`slow_l1` was bit-identical across all four arms despite confirmed state
divergence (`act_div` 0.056–0.135). The gate compresses per-unit arrays to
two global scalars (`mean_energy`, `trace_mass`) before the capture decision.
State context is lost at that compression point.

### Route C hypothesis

The gate is context-blind. The new diagnostics (`tag_trace_alignment`,
`tag_weighted_energy`, `tag_concentration`, `trace_concentration`) operate on
per-connection and per-unit arrays before compression. If state divergence
leaves any fingerprint in the network, these metrics should differ between
`closed_loop` and `divergent_warmup_replay` even when `slow_l1` does not.

### 10C.2 question

> Do the new sensors see what the old gate cannot?

If yes → proceed to 10C.3 gate redesign using the informative metric(s).
If no → Route C candidate metrics need rethinking before gate redesign.

---

## 3. Experiment Structure

Identical to 10A.2C except:
- `consolidation_ledger_enabled=True`
- `consolidation_diagnostics_enabled=True`
- Output includes per-capture diagnostic fields

### Arms

| Arm | Description |
|-----|-------------|
| `closed_loop` | Normal run, 9C+9D ON after warmup |
| `exact_replay` | Warmup replayed from identical RNG state |
| `divergent_warmup_replay` | Warmup replayed from noise seed +5000 |
| `matched_warmup_control` | Same divergent noise, but no event history |

### Fixed parameters

```python
seeds                = [42, 77]
total_steps          = 7500
warmup_steps         = 2000
decision_interval    = 250
consolidation_enabled              = True
event_pair_plasticity_enabled      = True
consolidation_ledger_enabled       = True
consolidation_diagnostics_enabled  = True
```

Warmup policy (unchanged from 10A.2C):
- Plasticity OFF during warmup via weight snapshot/restore
- `divergent_warmup_replay` uses `seed + 5000` for noise RNG during warmup
- No event prehistory injected
- No epsilon perturbation

Scheduler θ and all 9C/9D hyperparameters unchanged from 10A.2C baseline.

---

## 4. Outputs

### 4.1 Per-capture CSV

`results/phase10C2_captures_seed{seed}.csv`

| Column | Description |
|--------|-------------|
| `seed` | RNG seed |
| `arm` | closed_loop / exact_replay / divergent_warmup_replay / matched_warmup_control |
| `capture_index` | 0-based index within arm |
| `capture_step` | simulation step at capture |
| `capture_signal` | gate signal value at capture |
| `mean_energy` | global mean energy at capture |
| `trace_mass_at_capture` | L1 trace mass at capture |
| `tag_mass` | L1 tag mass at capture |
| `n_tagged_connections` | count of connections with tag > 0 |
| `slow_weight_delta_l1` | L1 of slow_weight change this capture |
| `tag_trace_alignment` | cosine(tag_cache, projected_trace) |
| `tag_weighted_energy` | tag-weighted mean local energy |
| `tag_concentration` | HHI of tag distribution |
| `tag_effective_support` | 1 / tag_concentration |
| `trace_concentration` | HHI of abs(event_trace) |
| `trace_effective_support` | 1 / trace_concentration |

### 4.2 Arm summary CSV

`results/phase10C2_summary_seed{seed}.csv`

One row per arm. Columns:

```
seed, arm,
capture_count,
tag_trace_alignment_mean, tag_trace_alignment_std,
tag_weighted_energy_mean, tag_weighted_energy_std,
tag_concentration_mean,   tag_concentration_std,
trace_concentration_mean, trace_concentration_std,
final_slow_l1,
final_fast_l1,
warmup_state_divergence_l1,
warmup_weight_delta_l1,
replay_hash_mismatch_count,
hard_pass
```

`hard_pass` = 1 iff all of:
- `warmup_weight_delta_l1 == 0.0` (weight restore worked)
- `replay_hash_mismatch_count == 0` for `exact_replay`
- all diagnostic values finite
- no NaN in any field

---

## 5. Success Criteria

| Check | Pass condition |
|-------|---------------|
| All arms complete | no crash, no timeout |
| Mirror behavior preserved | `closed_loop` slow_l1 ≈ `exact_replay` slow_l1 (within 1e-9) |
| Diagnostics present | all six fields in every ledger entry for capture arms |
| Finite values | no NaN, no Inf in any diagnostic |
| Gate invariance | `slow_l1` values match 10A.2C baseline within 1e-9 (diagnostics are read-only) |
| Weight restore | `warmup_weight_delta_l1 == 0.0` for all arms |

---

## 6. Analysis Questions

After the smoke run, answer these from the summary CSV:

**Q1.** Does `tag_trace_alignment` differ between `closed_loop` and
`divergent_warmup_replay`? (primary signal of interest)

**Q2.** Does `tag_weighted_energy` differ? (local energy context)

**Q3.** Do `tag_concentration` or `trace_concentration` differ?
(structural spread of activity)

**Q4.** If `slow_l1` remains identical across arms, do any diagnostics
show a statistically meaningful difference? (sensors seeing what gate cannot)

**Q5.** Based on Q1–Q4, which Route C candidate direction is supported:

| Label | Direction |
|-------|-----------|
| A | tag-trace alignment gate |
| B | local energy weighted tag gate |
| C | context-modulated transfer |
| D | none — candidate metrics need rethinking |

---

## 7. Runtime Estimate

| Component | Estimate |
|-----------|----------|
| 4 arms × 7500 steps × 2 seeds | ~same as 10A.2C |
| 10A.2C wall time (local) | ~4 min per seed |
| Diagnostics overhead | negligible (only at capture events, ~10–30 per run) |
| Total estimate | < 10 min local |

**Policy:** If estimated wall time ≤ 15 min → local is allowed.
If > 15 min → ECS (8.166.115.67).

---

## 8. Anti-Cheat Constraints (inherited from 10A.2C)

- No arm labels passed to `compute_capture_diagnostics`
- No event indices or history passed to diagnostics function
- Diagnostics computed from internal state only: `tag_cache`, `event_trace`,
  `energies`, `source_indices`, `target_indices`
- Gate signal (`capture_signal`) computed identically to 9D.1 baseline
- `slow_weight` transfer unchanged

---

## 9. What This Step Does NOT Do

- Does not redesign the capture gate
- Does not add new gate conditions
- Does not change `compute_capture_signal`
- Does not change `apply_capture`
- Does not enter 10C.3

---

## 10. Next Step (10C.3, not yet designed)

If Q1–Q4 show at least one diagnostic differs between `closed_loop` and
`divergent_warmup_replay`:
→ Design a new gate that incorporates the informative metric(s).
→ Pre-register the expected direction before implementation.

If no diagnostic differs:
→ Diagnose why. Candidate explanations:
  - State divergence is too small to propagate to tag/trace structure
  - Tag decay (τ=5000) smooths out context differences before capture
  - The four candidate metrics are the wrong abstraction level
→ Redesign the sensor set before proceeding to gate redesign.
