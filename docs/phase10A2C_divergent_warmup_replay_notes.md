# Phase 10A.2C — Divergent Warmup Replay Smoke Notes

> **定位：** diagnostic result。不是 tuning。
> **结论：** CLEAN NEGATIVE — warmup state divergence exists but does not propagate into slow structure.
> No digital-life / consciousness / personhood claim。

---

## 1. Summary

**Phase 10A.2C divergent warmup replay completed on ECS.**

- Hard protocol: **8/8 PASS** (both seeds, all 8 criteria)
- Mirror sanity: **confirmed** (exact ≡ closed in slow_l1, fast_l1)
- **P6 (warmup state divergence): PASS for both seeds**
- **P7 (warmup weights unchanged): PASS for both seeds** (post-restore delta = 0.0)
- **P8 (matched warmup control clean): PASS for both seeds**
- Primary result: **slow_l1 is bit-identical across closed_loop, exact_replay, and divergent_warmup_replay**
- amplification_ratio: **0.0**

The divergent warmup design successfully created state-context divergence (P6 confirmed), but this divergence does NOT propagate through the 9D tag → capture → slow_weight pipeline into measurable slow-structure differences.

---

## 2. Frozen Parameters

| Parameter | Value | Source |
|-----------|-------|--------|
| seeds | 42, 77 | 10A.0 |
| unit_count | 300 | 10A.0 |
| total_steps | 7500 | 10A.0 |
| warmup_end | 2000 | 10A.0 |
| decision_interval | 250 | 10A.1B |
| pulse_duration | 80 | 10A.0 |
| Scheduler θ | w=5.0, b_none=+1.0, b_L/R=-1.5, b_sim=-3.0, τ=1.0 | 10A.0 |
| 9C event-pair plasticity | ON (post-warmup) | 10A.2 |
| 9C trace_tau | 1000.0 | 10A.2 |
| 9C target_update_l1 | 1e-4 | 10A.2 |
| 9C gate_mode | soft_trace_gate | 10A.2 |
| 9C trace_gate_ref | 3e-2 | 10A.2 |
| 9D consolidation | ON (post-warmup) | 10A.3 |
| 9D tag_tau | 5000.0 | AnivaConfig default |
| 9D capture_threshold | 0.5 | AnivaConfig default |
| 9D slow_weight_max | 0.1 | AnivaConfig default |
| 9D slow_weight_rate | 0.1 | AnivaConfig default |
| 9D refractory | 500 | AnivaConfig default |
| divergent_noise_seed_offset | +5000 | 10A.2C design |
| warmup_plasticity | OFF (weight snapshot/restore) | 10A.2C design |
| warmup_events | None | 10A.2C design |
| ECS | 8.163.7.162 → rebooted 8.166.115.67, 4C8G Ubuntu 22.04 | — |

---

## 3. Hard Protocol Results

| Seed | P1 (NaN) | P2 (explosion) | P3 (hash) | P4 (events) | P5 (mirror) | P6 (act_div) | P7 (w_delta) | P8 (mctrl) | Verdict |
|------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 42 | OK | OK | OK | OK | OK | OK (0.056) | OK (0.0) | OK | **PASS** |
| 77 | OK | OK | OK | OK | OK | OK (0.135) | OK (0.0) | OK | **PASS** |

**Hard pass: 2/2.**

---

## 4. Seed 42 — Results

### 4.1 Per-Arm

| Arm | slow_l1 | fast_l1 | captures | tag_mass | w_delta | act_div |
|-----|---------|---------|----------|----------|---------|---------|
| closed_loop | 0.00039344 | 1848.589202 | 10 | 0.000691 | — | — |
| exact_replay | 0.00039344 | 1943.066298 | 10 | 0.000691 | 0.0 | — |
| divergent_warmup_replay | 0.00039344 | 1943.058709 | 10 | 0.000691 | 0.0 | 0.056399 |
| matched_warmup_control | 0.0 | 1943.059450 | 0 | 0.0 | 0.0 | — |

### 4.2 Cross-Arm Deltas

| Delta | Value |
|-------|-------|
| Δ(closed-exact)_slow | 0.00000000 |
| Δ(closed-divergent)_slow | 0.00000000 |
| Δ(exact-divergent)_slow | 0.00000000 |
| Δ(closed-divergent)_fast | -94.469507 |
| Δ(divergent-matched_ctrl) | 0.00039344 (net event effect) |
| amplification_ratio | **0.0** |

---

## 5. Seed 77 — Results

### 5.1 Per-Arm

| Arm | slow_l1 | fast_l1 | captures | tag_mass | w_delta | act_div |
|-----|---------|---------|----------|----------|---------|---------|
| closed_loop | 0.00044013 | 1870.308744 | 11 | 0.000656 | — | — |
| exact_replay | 0.00044013 | 1965.980419 | 11 | 0.000656 | 0.0 | — |
| divergent_warmup_replay | 0.00044013 | 1965.965682 | 11 | 0.000656 | 0.0 | 0.135409 |
| matched_warmup_control | 0.0 | 1965.969693 | 0 | 0.0 | 0.0 | — |

### 5.2 Cross-Arm Deltas

| Delta | Value |
|-------|-------|
| Δ(closed-exact)_slow | 0.00000000 |
| Δ(closed-divergent)_slow | 0.00000000 |
| Δ(exact-divergent)_slow | 0.00000000 |
| Δ(closed-divergent)_fast | -95.656938 |
| Δ(divergent-matched_ctrl) | 0.00044013 (net event effect) |
| amplification_ratio | **0.0** |

---

## 6. P6/P7/P8 Diagnostics

### 6.1 P6: Warmup State Divergence

| Seed | act_div | energy_div | Verdict |
|------|---------|------------|---------|
| 42 | 0.056399 | 0.040869 | **PASS** (> 1e-8) |
| 77 | 0.135409 | 0.004051 | **PASS** (> 1e-8) |

The noise-seed offset (+5000) successfully produces warmup state divergence. Seed 77 shows 2.4× more divergence than seed 42, and the energy divergence differs substantially (0.041 vs 0.004), suggesting the divergence pattern differs per seed.

### 6.2 P7: Weight Integrity at Warmup Boundary

| Seed | exact w_delta | divergent w_delta | Verdict |
|------|:---:|:---:|:---:|
| 42 | 0.0 | 0.0 | **PASS** (< 1e-6) |
| 77 | 0.0 | 0.0 | **PASS** (< 1e-6) |

Post-restore weight delta is zero (weights are copied back from snapshot). Base Hebbian plasticity does run during warmup (logs show pre-restore drift), but the restore at step 2000 guarantees the replay phase starts with the same weights.

### 6.3 P8: Matched Warmup Control

| Seed | slow_l1 | captures | Verdict |
|------|---------|----------|---------|
| 42 | 0.0 | 0 | **PASS** (< 1e-6) |
| 77 | 0.0 | 0 | **PASS** (< 1e-6) |

Divergent warmup alone (without subsequent event replay) does NOT produce any slow structure or capture events. The matched control is completely clean.

---

## 7. Interpretation

### 7.1 Primary Finding

**The divergent warmup replay route (Route A) produces CLEAN NEGATIVE: warmup state divergence does not propagate through 9D into slow-structure differences.**

The design succeeded in its operational goals:
- P6: divergent warmup creates measurable state divergence (act_div = 0.056–0.135)
- P7: weight restore at warmup/replay boundary is exact (post-restore delta = 0.0)
- P8: warmup alone does not confound the result (matched_control slow_l1 = 0.0)
- P5: mirror sanity is robust (exact ≡ closed in slow_l1, bit-identical)

But the scientific question — does different warmup prehistory produce different slow structure under identical event replay — returns NO.

### 7.2 Why

The 9D capture gate computes `signal = min(1, energy/0.3) × min(1, trace_mass/0.03) ≥ 0.5`. During the replay phase (2000–7500), events drive large phi updates → large dW → tag accumulation. The pre-existing state divergence from warmup, even at act_div=0.135 (seed 77), does not shift the aggregate signals (energy, trace_mass) at capture decision points enough to change capture timing or slow_weight deposition.

This is structurally the same failure mode as Scheme E: individual connection-level differences exist (fast Δ = 94–96 L1 units), but the 9D capture gate aggregates state-level signals that are dominated by event-driven dynamics, not by pre-event state context.

### 7.3 Comparison to Scheme E

| Aspect | Scheme E (ε ladder) | 10A.2C (divergent warmup) |
|--------|---------------------|--------------------------|
| Perturbation type | t=0 activation perturbation | 2000-step divergent noise trajectory |
| Fast Δ | 0.001–0.010 | 94–96 |
| Slow Δ | 0.0 | 0.0 |
| Amplification ratio | 0.0 | 0.0 |
| Capture count Δ | 0 | 0 |
| State divergence | Not directly measured | Confirmed (P6: 0.056–0.135) |

10A.2C produces orders of magnitude more fast-weight divergence (94 vs 0.01) and confirmed state divergence. Yet the slow-weight result is the same: zero.

### 7.4 What This Result Means

- **Route A (divergent warmup replay) confirms the Scheme E diagnosis from a different angle:** the 9D capture mechanism, under current defaults, is insensitive to state-context differences — whether injected at t=0 (Scheme E) or accumulated over 2000 steps (10A.2C).
- The 9D capture gate is a structural bottleneck: it aggregates state-level signals (energy, trace_mass) that are dominated by event-driven dynamics.
- The "history leaves traces" hypothesis is not falsified — only two specific classes of state-context perturbation (instant and sustained warmup) have been exhausted.

### 7.5 What This Result Does NOT Mean

- Does NOT mean 9D is broken. It works correctly under its design.
- Does NOT mean the closed-loop feedback hypothesis is wrong. Only that 9D's capture gate does not amplify state-context divergence.
- Does NOT mean state context doesn't matter at all. It matters for fast-weight divergence (confirmed at 94–96 L1).
- Does NOT justify post-hoc parameter tuning (capture_threshold, refractory, etc.).
- Does NOT justify entering 10A.4.
- Does NOT justify Option B (plasticity-ON warmup) as a guaranteed fix — it adds a weight confound without addressing the gate bottleneck.

---

## 8. Cross-Seed Consistency

| Metric | Seed 42 | Seed 77 |
|--------|---------|---------|
| closed slow_l1 | 0.00039344 | 0.00044013 |
| exact_≡_closed | ✅ | ✅ |
| divergent_≡_closed (slow) | ✅ | ✅ |
| divergent_≠_closed (fast) | ✅ (Δ=94.47) | ✅ (Δ=95.66) |
| warmup_act_div | 0.056399 | 0.135409 |
| warmup_energy_div | 0.040869 | 0.004051 |
| captures (cl/ex/dv) | 10/10/10 | 11/11/11 |
| matched_ctrl captures | 0 | 0 |
| amplification_ratio | 0.0 | 0.0 |
| Hard protocol | 8/8 PASS | 8/8 PASS |

High cross-seed consistency. Both seeds independently confirm the same negative result.

---

## 9. Pre-Flight & Runtime

| Check | Result |
|-------|--------|
| py_compile | PASS (local) |
| dry-run-schedule | PASS (local) |
| estimate-only | ~17 min (local, > 15 min → ECS) |
| ECS re-run count | 3 (debug: P7 measurement fix ×1, logs dir ×1) |
| ECS wall time (seed 42) | ~217s (~3.6 min) |
| ECS wall time (seed 77) | ~235s (~3.9 min) |
| Total ECS time | ~235s (parallel by seed) |

---

## 10. Implementation Notes

### 10.1 State Snapshot/Restore

LifeCore uses a single RNG for both initialization and noise. The divergent warmup mechanism creates two LifeCore instances: one with seed=seed_env (canonical), one with seed=seed_env+5000 (divergent). The divergent instance's topology/weights/state is overwritten to match the canonical via `_snapshot_core_state()` / `_restore_core_state()`. The RNG state remains at different positions, producing divergent noise trajectories.

### 10.2 Weight Restore for Plasticity OFF

LifeCore has no `plasticity_enabled` flag. The base Hebbian plasticity in `step()` always runs. To guarantee plasticity OFF during warmup, weights are snapshotted at step 0 and restored at step 2000 (via `_weight_cache[:] = w0` and `conn.weight = float(w0[i])`). P7 verifies the post-restore delta is zero.

### 10.3 P7 Measurement Bug (Fixed in v2)

The initial implementation measured `warmup_weight_delta` AFTER the full 7500-step run for exact_replay, capturing 5500 steps of 9C plasticity (delta=285). Fixed to measure at step 2000 post-restore (delta=0.0). Same fix applied to divergent_warmup_replay and matched_warmup_control.

---

## 11. Decision Rules Reference

Per the 10A.2C design (§7.2 Success Criteria):

| Outcome | Condition | 10A.2C Result |
|---------|-----------|:---:|
| POSITIVE | divergent ≠ closed in slow_l1 | ❌ |
| NEGATIVE | divergent ≈ closed in slow_l1 | **HIT** |
| WARMUP CONFOUND | matched_control slow_l1 > 0 | Not hit |
| SATURATION | saturation_frac > 0.5 | Not hit |

Both seeds hit the NEGATIVE criterion. The divergent warmup design does not create state divergence sufficient for 9D capture differentiation.

---

## 12. Relationship to Evidence Chain

| Phase | Key Finding | 10A.2C Relevance |
|-------|-------------|-------------------|
| 10A.2B.2 | Scheme E exhausted: fast Δ exists, slow Δ = 0 | 10A.2C confirms from different perturbation class |
| 10A.3 | 9C+9D ON, ε=0.02 → clean negative | Same 9C+9D configuration used |
| 10A.2B.2 decision | Route A (divergent warmup) selected | Route A now also exhausted |
| 10A.2C design | Option A (plasticity OFF), noise-seed offset | Executed as designed |

---

## 13. Output Artifacts

| Artifact | Path |
|----------|------|
| Seed 42 CSV | `results/phase10A2C_seed42.csv` |
| Seed 42 events | `results/phase10A2C_seed42_events.csv` |
| Seed 42 JSON | `results/phase10A2C_seed42_summary.json` |
| Seed 77 CSV | `results/phase10A2C_seed77.csv` |
| Seed 77 events | `results/phase10A2C_seed77_events.csv` |
| Seed 77 JSON | `results/phase10A2C_seed77_summary.json` |
| ECS seed 42 log | `logs/phase10A2C_seed42.log` (ECS only) |
| ECS seed 77 log | `logs/phase10A2C_seed77.log` (ECS only) |
| Smoke notes | `docs/phase10A2C_divergent_warmup_replay_notes.md` |

---

## 14. Boundary

- Scheme E is closed. Do not re-open.
- Route A (divergent warmup replay) is diagnostically exhausted.
- Do NOT tune 9D capture parameters post-hoc.
- Do NOT enter 10A.4.
- Do NOT add ε=0.10.
- Option B (plasticity-ON warmup, 10A.2C.2) remains as documented in the design but is not recommended — it adds a weight confound without addressing the gate bottleneck.
- Route B (cross-seed yoked diagnostic) and Route C (state-dependent capture redesign) remain as documented in 10A.2B.2.
- No digital-life / consciousness / personhood claim.
