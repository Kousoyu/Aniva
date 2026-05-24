# Phase 10A.3 — Closed-Loop Slow Consolidation Design

> **定位：** design only。不实现，不跑实验。
> Phase 10A.3 第一次在 Phase 10 管线中同时打开 9C event-pair fast plasticity
> 和 9D slow structural consolidation。
>
> 10A.2B.1 found a hairline crack in fast weight.
> 10A.3 asks whether 9D consolidation preserves or amplifies that crack
> into slow structure.

---

## 1. Background

### 1.1 Evidence Chain

```
10A.1     scheduler plumbing — CAVEATED
10A.1B    calibration variant (interval=250) — CLEAN PASS
10A.2     closed-loop + 9C fast plasticity — CLEAN NEGATIVE
          (exact replay ≡ closed, deterministic mirror)
10A.2B    matched replay control redesign — Scheme E selected
10A.2B.1  perturbed replay (ε=0.02) — HAIRLINE POSITIVE
          (mirror reproduced, crack ~4×10⁻⁷ of total fast L1)
10A.2B    decision note — Route B: proceed to 10A.3, no ε ladder
```

### 1.2 From Fast Trace to Slow Structure

Phase 9D established: under a fixed designer-specified schedule, event-pair
dW can be deposited as enduring directional slow structure via the
tag → capture → slow_weight pipeline.

Phase 10A.2/10A.2B.1 established: under state-feedback event generation,
the fast weight trajectory is strongly event-log-dominant, but a t=0 state
perturbation produces a measurable (hairline) fast-weight divergence.

**10A.3 is the first test of whether that hairline fast-weight crack,
when fed through 9D consolidation, becomes a measurable slow-structure
feature.**

### 1.3 The 9D Consolidation Pipeline (Recap)

```
event arrival → apply_event_pair_phi(phi)
  ├── trace × phi → dW (9C fast plasticity)
  ├── weight_cache += dW
  ├── produce_tags(tag_cache, |dW|)     ← 9D tag production
  └── trace += phi

every step:
  ├── decay_tags(tag_cache, τ=5000)     ← tag exponential decay
  └── if not refractory:
        signal = min(1, energy/0.3) × min(1, trace_mass/0.03)
        if signal ≥ 0.5:
          slow_weight += 0.1 × tag_cache    ← capture
          clamp(slow_weight, [-0.1, +0.1])
          refractory = 500 steps

synaptic transmission:
  effective_weight = fast + slow, clamp to [-1, 1]
```

Key property: capture depends on **internal state** (mean energy × trace
mass). Different state trajectories → different capture timing/magnitude
→ different slow_weight endpoints, even with identical event logs.

---

## 2. Research Question

> Does 9D slow consolidation amplify or preserve the hairline fast-weight
> divergence between perturbed and exact replay, producing measurable
> slow-structure differences?

**Sub-questions:**

1. Does perturbed_replay produce different slow_weight than exact_replay?
2. Is the slow-weight divergence larger or smaller than the fast-weight
   divergence (amplification vs. dampening)?
3. Does the no_event arm accumulate zero (or near-zero) slow_weight?
4. Are capture counts, tag masses, and saturation fractions different
   between arms?
5. Are results consistent across both seeds?

---

## 3. Frozen Parameters

### 3.1 Inherited from 10A.2B.1

| Parameter | Value | Source |
|-----------|-------|--------|
| seeds | 42, 77 | 10A.0 |
| unit_count | 300 | 10A.0 |
| total_steps | 7500 | 10A.0 |
| warmup | 2000 | 10A.0 |
| decision_interval | 250 | 10A.1B |
| pulse_duration | 80 | 10A.0 |
| Scheduler θ | w=5.0, b_none=+1.0, b_L/R=-1.5, b_sim=-3.0, τ=1.0 | 10A.0 |
| ε | 0.02 | 10A.2B.1 |
| perturbation_target | activations only, t=0 once | 10A.2B.1 |
| perturbation_distribution | uniform [-ε, +ε], zero-mean, clip [0,1] | 10A.2B.1 |
| perturb_seed_offset | +3000 | 10A.2B.1 |

### 3.2 9C Event-Pair Plasticity (ON)

| Parameter | Value |
|-----------|-------|
| event_pair_plasticity_enabled | True |
| event_pair_trace_tau | 1000.0 |
| event_pair_target_update_l1 | 1e-4 |
| event_pair_gate_mode | "soft_trace_gate" |
| event_pair_trace_gate_ref | 3e-2 |
| event_pair_gate_power | 1.0 |
| event_pair_ledger_enabled | True |

### 3.3 9D Consolidation (ON — NEW for Phase 10)

| Parameter | Value | Notes |
|-----------|-------|-------|
| consolidation_enabled | **True** | First time in Phase 10 |
| consolidation_tag_tau | 5000.0 | AnivaConfig default |
| consolidation_capture_threshold | 0.5 | AnivaConfig default |
| consolidation_slow_weight_max | 0.1 | AnivaConfig default |
| consolidation_slow_weight_rate | 0.1 | AnivaConfig default |
| consolidation_capture_refractory_steps | 500 | AnivaConfig default |
| consolidation_ledger_enabled | **True** | For capture diagnostics |

All 9D parameters use AnivaConfig defaults established in Phase 9D.
They are NOT tuned in 10A.3.

---

## 4. Arms

### 4.1 closed_loop

Scheduler active. Generates event log from state feedback.
Both 9C and 9D ON.

```
for step in range(7500):
    step(env)
    if step in decision_points:
        event = scheduler.propose(activity_L, activity_R)
        if event != "none":
            apply_stimulus(event)
            core.apply_event_pair_phi(phi)  → 9C dW + 9D tag production
    # 9D consolidation step happens inside core.step()
```

### 4.2 exact_replay

Scheduler disabled. Same seed, same initial state, same event log.
Both 9C and 9D ON.

**Expected:** `slow_l1(exact) ≈ slow_l1(closed)` — mirror sanity check.
If this fails, the 9D pipeline has non-deterministic behavior.

### 4.3 perturbed_replay

Scheduler disabled. Same seed, same topology, same weights, same event log.
Initial activations perturbed at t=0 (ε=0.02, same perturbation vector as
would be produced by 10A.2B.1's perturb_seed_offset=+3000 rule).
Both 9C and 9D ON.

**This is the primary test arm.** If `slow_l1(perturbed) ≠ slow_l1(closed)`,
the 9D pipeline has amplified (or at minimum preserved) the hairline
fast-weight divergence into a measurable slow-structure difference.

### 4.4 no_event_control

No events. No scheduler. Both 9C and 9D ON (trace decays, tags only from
Hebbian plasticity — expected near zero).

**Expected:** `slow_l1(no_event) ≈ 0`, `capture_count ≈ 0`.
If no_event accumulates non-trivial slow_weight, the 9D pipeline has a
baseline drift that must be subtracted from other arms.

---

## 5. Metrics

### 5.1 Primary (Per Arm, Per Seed)

| Metric | Source | What It Measures |
|--------|--------|-----------------|
| slow_weight_l1_total | `sum(abs(core._slow_weight_cache))` | Total slow structural mass |
| slow_weight_max_abs | `max(abs(core._slow_weight_cache))` | Saturation check |
| capture_count | `len(core._consolidation_ledger)` | How many times capture fired |
| capture_signals | `[e.capture_signal for e in ledger]` | Strength of each capture |
| tag_mass_final | `sum(abs(core._tag_cache))` | Residual tags at end |
| n_tagged_connections | `sum(core._tag_cache > 0)` | How many connections received tags |
| saturation_frac | fraction of `|effective| ≥ 0.999` | Whether fast+slow is saturating |
| total_slow_delta_l1 | sum of per-capture delta L1 | Total mass transferred to slow |
| fast_weight_l1_total | `sum(abs(core._weight_cache))` | Fast weight reference |
| max_abs_weight | `max(abs(core._weight_cache))` | Explosion check |
| nan_count | 0 required | Health |
| replay_hash_mismatch_count | 0 required | Replay fidelity |

### 5.2 Cross-Arm Deltas

| Delta | Computation |
|-------|-------------|
| closed_vs_exact_slow_l1 | `slow_l1(closed) - slow_l1(exact)` |
| closed_vs_perturbed_slow_l1 | `slow_l1(closed) - slow_l1(perturbed)` |
| exact_vs_perturbed_slow_l1 | `slow_l1(exact) - slow_l1(perturbed)` |
| closed_vs_no_event_slow_l1 | `slow_l1(closed) - slow_l1(no_event)` |
| amplification_ratio | `|exact_vs_perturbed_slow_l1| / |exact_vs_perturbed_fast_l1|` (from 10A.2B.1 baseline) |

### 5.3 Secondary (Reported, Not Gated)

| Metric | Computation |
|--------|-------------|
| per-region slow_weight (L/R/M) | L1 by source region |
| slow_weight_DI | Directional index if L/R asymmetry present |
| capture_timing_distribution | When captures occurred |
| mean_capture_signal | Average signal strength at capture events |
| refractory_utilization | capture_count / max_possible_captures |

---

## 6. Success Criteria (Pilot — 2 Seeds)

### 6.1 Hard Protocol (HARD)

| # | Criterion | Threshold |
|---|-----------|-----------|
| P1 | No NaN | 0 |
| P2 | No explosion | max_abs_weight < 10.0 |
| P3 | Replay hash mismatch = 0 | Both replay arms |
| P4 | Event count match across arms | exact = perturbed = closed |
| P5 | 9C ON, 9D ON confirmed | assert |
| P6 | exact_replay ≈ closed_loop (mirror sanity) | `|closed_vs_exact_slow_l1| / closed_slow_l1 < 0.01` |

### 6.2 Soft — Scientific Signal

| Outcome | Interpretation |
|---------|---------------|
| exact ≈ closed AND perturbed differs in slow_weight | **POSITIVE.** 9D preserves/amplifies state-context divergence into slow structure. |
| exact ≈ closed AND perturbed ≈ closed | **NEGATIVE.** 9D does not amplify the hairline crack. Pipeline remains event-log-dominant at ε=0.02. |
| exact ≠ closed | **PROTOCOL BUG.** Do not interpret perturbed result. |
| no_event slow_l1 non-trivial (> 10% of closed) | **BASELINE DRIFT.** Subtract no_event from all arms before comparison. |
| slow_weight saturated (saturation_frac > 0.5) | **SATURATION.** Slow weight ceiling hit — effect may be capped. Report saturation, do not retune max. |

### 6.3 What "Positive" Means (and Does NOT Mean)

**A positive 10A.3 result means:**
- Under ε=0.02 initial state perturbation, 9D slow consolidation produces
  measurable slow-structure divergence between exact and perturbed replay.
- The 9D capture mechanism (state-gated by energy × trace mass) amplifies
  what was a hairline fast-weight difference into a detectable slow feature.
- This supports the hypothesis that closed-loop feedback context can leave
  a structural trace beyond matched replay baseline.

**A positive 10A.3 result does NOT mean:**
- Digital life validated.
- Consciousness, sentience, or personhood established.
- The effect is large or functionally significant.
- The scheduler is optimal or adaptive.
- The result generalizes to 4 seeds (that's 10A.4).

---

## 7. Failure Modes and Interpretation

| Failure | Interpretation |
|---------|---------------|
| exact ≠ closed | Non-determinism in 9D pipeline (capture timing, tag accumulation). Debug before interpreting. |
| perturbed ≈ exact (slow) | 9D does not amplify the hairline crack. The state-gated capture mechanism may not be sensitive to activation-level differences at this scale. |
| no_event accumulates slow_weight | Hebbian plasticity alone produces enough dW to trigger captures. Need to subtract no_event baseline. |
| slow_weight saturated | `slow_weight_max=0.1` ceiling hit. The headroom may be too small for 7500 steps × many captures. |
| Only one seed shows effect | Seed-dependent dynamics. Report per-seed, do not average. This is a finding, not a failure. |

---

## 8. Interpretation Rules (Locked Before Run)

1. **exact_replay MUST be close to closed_loop.** If `|closed-exact|/closed > 0.01`,
   the 9D pipeline behaves non-deterministically with identical inputs.
   Investigate capture timing / refractory / tag decay interactions.

2. **Do NOT tune ε if perturbed ≈ exact.** ε=0.02 is frozen. If 10A.3 is negative,
   the pre-registered fallback (from 10A.2B decision note) is to return to
   ε sensitivity ladder as diagnostic — not to find a "working ε."

3. **Do NOT tune 9D parameters** (capture_threshold, refractory, slow_weight_max,
   tag_tau) if the result is negative. These are AnivaConfig defaults, validated
   in Phase 9D.

4. **Do NOT drop the exact_replay arm** even if it's "obviously a mirror." It is
   the sanity check that validates the entire 9D pipeline within-run.

5. **All results reported per-seed.** No averaging across seeds for primary claims.

---

## 9. Runtime Estimate

| Arm | Per-Seed (est.) | Notes |
|-----|-----------------|-------|
| closed_loop | ~2 min | 9C + 9D tag production per event |
| exact_replay | ~2 min | Same 9C+9D load |
| perturbed_replay | ~2 min | Same 9C+9D load |
| no_event | ~1.5 min | Trace/tag decay only, no event updates |

- 4 arms × 2 seeds ≈ **~15 min**
- Borderline for local; if estimate > 15 min, move to ECS
- Estimate-only run before full execution

---

## 10. Output Artifacts

| Artifact | Path |
|----------|------|
| Event logs | `results/phase10A3_{arm}_seed{seed}_events.csv` |
| Slow weight snapshots | `results/phase10A3_{arm}_seed{seed}_slow_weight.csv` |
| Consolidation ledger | `results/phase10A3_{arm}_seed{seed}_ledger.csv` |
| Summary CSV | `results/phase10A3_summary.csv` |
| Summary JSON | `results/phase10A3_summary.json` |
| Smoke notes | `docs/phase10A3_slow_consolidation_smoke_notes.md` |

---

## 11. Relationship to Phase 9D

| Aspect | Phase 9D | Phase 10A.3 |
|--------|----------|-------------|
| Event source | Fixed designer schedule | State-feedback scheduler |
| Replay control | None (no scheduler) | exact_replay + perturbed_replay |
| Primary question | Can event order deposit into structure? | Can closed-loop feedback context amplify fast-trace divergence into structure? |
| Key metric | corrected_slow_DI | closed_vs_perturbed_slow_l1 |
| Seeds | 4 (formal) | 2 (pilot) |
| ε perturbation | Not applicable | ε=0.02 frozen from 10A.2B.1 |

9D proved structure can be deposited from fixed events.
10A.3 asks whether structure amplifies the hairline signal of feedback context.

---

## 12. Boundary

- 9C event-pair plasticity is ON.
- 9D consolidation is ON (first time in Phase 10).
- ε=0.02 is frozen from 10A.2B.1.
- Scheduler θ is frozen from 10A.0.
- Decision interval is frozen from 10A.1B.
- This is a 2-seed pilot. Formal 4-seed is 10A.4.
- 10A.2 CLEAN NEGATIVE is not challenged.
- 10A.2B.1 HAIRLINE POSITIVE is not inflated.
- No digital-life / consciousness / personhood claim.
