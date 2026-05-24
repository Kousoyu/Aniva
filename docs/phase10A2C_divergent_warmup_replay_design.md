# Phase 10A.2C — Divergent Warmup Replay Design

> **定位：** design only。不实现，不跑实验。
> **性质：** new replay control — same seed / same topology / same event log,
> different warmup prehistory。
>
> Scheme E（initial activation perturbation）已诊断性穷尽。
> 10A.2C 换路线：不让镜子被敲一下，而是让镜子在照同一件事之前，
> 先走过不同河床。
>
> No digital-life / consciousness / personhood claim。

---

## 1. Background

### 1.1 Why Scheme E Exhausted

Scheme E perturbed initial activations at t=0 by uniform [-ε, +ε].
Results across ε ∈ {0.005, 0.01, 0.02, 0.05}:

- Fast-weight divergence: **present** at all ε
- Slow-weight divergence: **zero** at all ε
- amplification_ratio: **0.0** everywhere
- capture_count: **identical** across all arms and ε

The perturbation propagated through the 9C pipeline into measurable
fast-weight differences. But the 9D capture gate (`energy × trace_mass ≥ 0.5`)
never fired differently. The t=0 perturbation decays too quickly and does
not shift the aggregate state signals that gate 9D capture.

The diagnosis is clear: **a single t=0 activation perturbation, regardless
of magnitude, does not create the kind of sustained state-context difference
that 9D can detect as a capture-timing or slow-weight event.**

### 1.2 Why Divergent Warmup

Scheme E perturbed the *initial condition* at a single point.
Divergent warmup perturbs the *trajectory* over a sustained period.

The hypothesis: if two instances of the same network (same seed, same
topology, same initial weights) experience different intrinsic dynamics
during a 2000-step warmup phase, their state contexts (activations,
traces, energy) will diverge. When they then receive the identical event
log, this pre-existing state-context divergence may:

1. Shift the aggregate signals (energy, trace_mass) at capture decision
   points enough to produce different capture timing.
2. Produce different slow_weight endpoints even with identical events.

This is closer to the spirit of "history leaves traces" — the warmup
is a prehistory period that shapes the network's receptivity to
subsequent events.

### 1.3 Evidence Chain

```
10A.2     closed-loop + 9C — mirror discovered, clean negative
10A.2B    replay control redesign — Scheme E selected
10A.2B.1  ε=0.02 perturbed — hairline positive in fast
10A.3     9C+9D ON, ε=0.02 — clean negative
10A.2B.2  ε ladder [0.005–0.05] — FAST DIVERGENCE, NO SLOW SIGNAL
10A.2B.2  decision — Scheme E exhausted, Route A: divergent warmup
→ 10A.2C  (this design)
```

---

## 2. Core Design Decision: Plasticity OFF During Warmup

### 2.1 The Choice

**During the divergent warmup phase (steps 0 → 2000), plasticity is OFF.**

- 9C event-pair plasticity: disabled
- 9D consolidation: disabled
- No events are applied (no external stimuli)
- Only intrinsic dynamics run: activation propagation, energy, noise,
  synaptic transmission via existing weights

### 2.2 Rationale

Two options were considered:

| Option | Plasticity During Warmup | Effect |
|--------|:---:|--------|
| A | OFF | Only state diverges. Weights unchanged. |
| B | ON | Both state and structure diverge. |

**Option A is selected** for three reasons:

1. **Isolate the variable.** We want to test whether different state
   context alone affects subsequent event deposition. If plasticity
   is ON during warmup, the weights also change, and we cannot
   distinguish "different weights at replay start" from "different
   state context at replay start."

2. **Avoid event-history confound.** Plasticity during warmup would
   mean the warmup phase itself deposits structural changes — it
   becomes an event-like period, not a pure prehistory. This is
   Option C from the candidates list, explicitly deferred.

3. **Cleaner matched warmup control.** If only state diverges, the
   matched_warmup_control can verify that warmup-state divergence
   alone (without subsequent events) does not produce slow structure.

Option B may be explored in a future sub-phase (10A.2C.2) if 10A.2C
with Option A is negative.

### 2.3 What Happens During Warmup

```
Steps 0 → 2000 (warmup):
  - core.step() runs normally
  - Activations, energy, traces evolve via intrinsic dynamics
  - Synaptic transmission uses existing weights (fast + slow)
  - NO events applied (no apply_event_pair_phi)
  - NO 9C plasticity (event_pair_plasticity_enabled = False, or
    never calls apply_event_pair_phi)
  - NO 9D consolidation (consolidation_enabled = False)
  - event_trace decays naturally (or is reset — see §2.4)

Steps 2000 → 7500 (event replay):
  - 9C event-pair plasticity: ON
  - 9D consolidation: ON
  - Event log replayed identically from closed_loop
```

### 2.4 Trace Handling

During warmup, no events are applied, so `apply_event_pair_phi` is never
called. The event_trace should remain at or near zero (any residual from
initialization should have decayed by step 2000 given τ=1000 and 2000
steps = 2× τ).

**Decision: do not explicitly reset event_trace.** Natural decay over
2000 steps is sufficient. If the trace is non-zero at step 2000 in any
arm, it will be recorded and reported as a diagnostic check.

---

## 3. Divergence Mechanism

### 3.1 Selected: Noise-Seed Divergent Warmup

The LifeCore uses a random number generator for intrinsic noise.
If we initialize the divergent_warmup_replay arm with the same seed_env
but use a different noise RNG seed during warmup, the intrinsic noise
trajectory differs, producing divergent state dynamics.

However, in the current Aniva codebase, noise is part of the core step
and may not have a separate RNG seed. Two sub-options:

**3.1A: If dynamics already have stochasticity (noise with separate seed)**

Use `seed_env` for topology/weights/initial state (same across arms),
but use `seed_env + OFFSET_DIVERGENT` for the noise/dynamics RNG during
warmup only. After warmup (step 2000), both arms use the same noise
seed for the replay phase.

**3.1B: If dynamics are fully deterministic (no noise, or noise is
deterministic given seed_env)**

Use a minimal state perturbation at t=0 that repeats or persists through
warmup. This is NOT the same as Scheme E (which perturbed once at t=0
and let it propagate). Instead:

- Apply a tiny persistent activation bias during warmup:
  e.g., a constant +δ to L-region units or a small sinusoidal
  perturbation.
- Remove the bias at step 2000, before event replay starts.
- The 2000 steps of biased dynamics create a diverged state context.

This is classified as "extended state-context perturbation" and is
explicitly NOT proof of natural history-dependent divergence. It is
a controlled probe.

**Decision: attempt 3.1A first. If the codebase does not support
separate noise RNG seeds for warmup vs. replay, fall back to 3.1B
with the classification noted above.**

### 3.2 What Must NOT Be Done During Warmup

- NO external events (L, R, simultaneous)
- NO apply_event_pair_phi
- NO tag production or capture
- NO slow_weight updates
- NO changes to _weight_cache or _slow_weight_cache

---

## 4. Arms

### 4.1 Arm Summary

| # | Arm | Warmup Type | Event Source (post-warmup) | 9C | 9D |
|---|-----|-------------|---------------------------|:--:|:--:|
| 1 | closed_loop | Standard (scheduler active, events applied) | Scheduler from state | ON | ON |
| 2 | exact_replay | Standard (no events, mirror check) | Replayed from closed | ON | ON |
| 3 | divergent_warmup_replay | **Divergent** (noise-seed offset) | Replayed from closed | ON | ON |
| 4 | matched_warmup_control | **Divergent** (same as arm 3) | **None** (no events) | ON | ON |

### 4.2 Arm 1: closed_loop

Standard closed_loop arm (identical to 10A.2B.2 / 10A.3).

```
for step in 0..7500:
    step(env)
    if step in [2000, 2250, ..., 7250]:
        event = scheduler.propose(activity_L, activity_R)
        if event != "none":
            apply_stimulus(event) → apply_event_pair_phi(phi)
```
- 9C ON throughout (from step 0, but no events before warmup end)
- 9D ON throughout
- Produces canonical event log E_seed

### 4.3 Arm 2: exact_replay

Standard exact_replay arm (mirror sanity check).

```
warmup (0..2000):
    NO events, NO plasticity
    Only intrinsic dynamics

replay (2000..7500):
    Replay E_seed exactly
    9C ON, 9D ON
```

### 4.4 Arm 3: divergent_warmup_replay (Primary Test)

```
warmup (0..2000):
    Same seed_env (same topology, same initial weights, same initial state)
    DIFFERENT noise/dynamics seed during warmup
    NO events, NO plasticity
    State evolves differently from exact_replay due to different noise

replay (2000..7500):
    SWITCH noise seed back to match exact_replay (or keep divergent —
    freeze this choice before implementation)
    Replay E_seed exactly
    9C ON, 9D ON
    Compare slow_weight, capture_count vs closed_loop and exact_replay
```

**Noise seed during replay phase:** To isolate the effect of warmup
state divergence only, the noise seed during the replay phase
(2000–7500) should either:
- (a) match exact_replay, or
- (b) continue divergent.

Choice (a) isolates warmup state divergence. Choice (b) adds continuing
state divergence on top. **Select (a) for the primary design** — if
positive, it proves warmup state context matters. If negative, (b)
can be tried as a variant.

### 4.5 Arm 4: matched_warmup_control

```
warmup (0..2000):
    Same divergent warmup as arm 3
    Different noise/dynamics seed
    NO events, NO plasticity

post-warmup (2000..7500):
    NO events at all
    9C ON, 9D ON (trace decays, captures may fire from Hebbian bg)
    If captures or slow_weight appear, subtract from arm 3.
```

This controls for: does the divergent warmup alone (without subsequent
event log replay) produce slow structure? If arm 4 shows non-zero
slow_l1, the warmup itself is depositing structure, and arm 3's
slow_l1 must be compared against arm 4, not against zero.

### 4.6 Optional: no_event_control

Same as 10A.3 no_event: no events ever, 9C+9D ON. Included only if
runtime allows. If omitted, the 10A.3 no_event baseline (slow_l1=0.0)
serves as reference.

---

## 5. Frozen Parameters

### 5.1 Inherited (Unchanged)

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

### 5.2 New (10A.2C Specific)

| Parameter | Value | Notes |
|-----------|-------|-------|
| warmup_plasticity | **OFF** | 9C and 9D disabled during steps 0–2000 |
| divergent_noise_seed_offset | **+5000** | seed_env + 5000 for divergent warmup noise |
| replay_noise_seed | **matches exact_replay** | After warmup, noise seed same as arm 2 |
| warmup_events | **None** | No L/R/sim events during warmup |

---

## 6. Metrics

### 6.1 State Divergence at Warmup End

| Metric | Computation | Purpose |
|--------|-------------|---------|
| warmup_act_div | L2 distance of activations (arm3 vs arm2) at step 2000 | Confirm warmup produced state divergence |
| warmup_trace_div | L1 distance of event_trace (arm3 vs arm2) at step 2000 | Confirm trace state differs |
| warmup_energy_div | |mean_energy(arm3) − mean_energy(arm2)| at step 2000 | Energy context divergence |

If warmup_act_div ≈ 0, the divergent warmup design failed to produce
state divergence and the experiment is invalid for interpretation.

### 6.2 Primary (Per Arm, Per Seed)

| Metric | Source |
|--------|--------|
| slow_weight_l1 | `sum(abs(core._slow_weight_cache))` |
| fast_weight_l1 | `sum(abs(core._weight_cache))` |
| capture_count | `len(core._consolidation_ledger)` |
| tag_mass_final | `sum(abs(core._tag_cache))` |
| n_tagged_connections | `sum(core._tag_cache > 0)` |
| saturation_frac | fraction of `|effective| ≥ 0.999` |
| max_abs_weight | `max(abs(core._weight_cache))` |
| max_abs_slow_weight | `max(abs(core._slow_weight_cache))` |
| nan_count | 0 required |
| replay_hash_mismatch_count | 0 required |

### 6.3 Cross-Arm Deltas

| Delta | Computation |
|-------|-------------|
| closed_vs_exact_slow_l1 | Primary mirror check |
| closed_vs_divergent_slow_l1 | Primary test |
| exact_vs_divergent_slow_l1 | Alternate test (removes closed_loop's own noise) |
| closed_vs_matched_control_slow_l1 | Warmup confound check |
| divergent_vs_matched_control_slow_l1 | Net effect of event log on diverged state |
| amplification_ratio | `|exact_vs_divergent_slow_l1| / |exact_vs_divergent_fast_l1|` |

### 6.4 Capture Diagnostics

| Metric | Computation |
|--------|-------------|
| capture_count_delta | captures(divergent) − captures(exact) |
| tag_mass_delta | tag_mass(divergent) − tag_mass(exact) |
| per-region slow_l1 (L/R/M) | Breakdown by source region |
| slow_weight_DI | Directional index if L/R asymmetry present |

---

## 7. Success Criteria

### 7.1 Hard Protocol

| # | Criterion | Threshold |
|---|-----------|-----------|
| P1 | No NaN | 0 |
| P2 | No explosion | max_abs_weight < 10.0 |
| P3 | Replay hash mismatch = 0 | Both replay arms |
| P4 | Event count match across replay arms | exact = divergent = closed |
| P5 | exact ≈ closed (mirror) | `|closed_vs_exact_slow_l1| / closed_slow_l1 < 0.01` |
| P6 | warmup state divergence > 0 | warmup_act_div > 1e-8 |
| P7 | warmup weights unchanged | fast_l1(arm3 at step 2000) ≈ fast_l1(arm3 at step 0) |

P6 and P7 are new for 10A.2C. P6 confirms the warmup design worked.
P7 confirms plasticity was truly OFF during warmup (no weight leakage).

### 7.2 Soft — Scientific Signal

| Outcome | Interpretation |
|---------|---------------|
| exact ≈ closed AND divergent ≠ closed in slow_l1 | **POSITIVE.** Warmup state context propagates through 9D into structure. |
| exact ≈ closed AND divergent ≈ closed | **NEGATIVE.** Current divergent warmup design does not create state divergence sufficient for 9D. |
| matched_control slow_l1 > 0 AND divergent slow_l1 ≈ matched_control | **WARMUP CONFOUND.** Warmup alone creates slow structure. Net event-log effect is zero. |
| divergent ≠ closed but saturation_frac > 0.5 | **SATURATION.** Effect may be capped by slow_weight_max. |
| One seed positive, other negative | Seed-dependent. Report per-seed. |

### 7.3 What "Positive" Means (and Does NOT Mean)

**A positive 10A.2C result means:**
- Sustained state-context divergence from a 2000-step warmup period
  produces measurable slow-structure differences under identical event
  replay.
- The 9D capture mechanism is sensitive to pre-event state context
  when that context is accumulated over time, not injected at a point.
- This supports the "history leaves traces" hypothesis in a way that
  Scheme E could not.

**A positive 10A.2C result does NOT mean:**
- The warmup mechanism is realistic or natural.
- The effect size is functionally significant.
- The result generalizes to 4 seeds.
- Digital life, consciousness, or personhood is validated.
- We should enter 10A.4.

---

## 8. Interpretation Rules (Locked Before Run)

1. **exact_replay MUST mirror closed_loop.** If not, the warmup design
   broke the replay protocol — debug before interpreting.

2. **P6 must pass.** If warmup_act_div ≈ 0, the divergent warmup failed
   to produce state divergence — the experiment is INVALID.

3. **P7 must pass.** If weights changed during warmup, plasticity was
   not truly OFF — the experiment is INVALID.

4. **If divergent ≠ closed in slow_l1:** check matched_warmup_control.
   If matched_control also shows slow_l1, subtract it. The net effect
   is `divergent_slow_l1 − matched_control_slow_l1`.

5. **If matched_control shows captures:** the divergent warmup alone
   drives capture events. This is a finding — report it separately.

6. **Do NOT tune warmup_steps, noise offset, or plasticity schedule**
   post-hoc. If negative, the warmup design is insufficient — a new
   design document is needed.

7. **All results per-seed.** No averaging.

---

## 9. Failure Modes

| Failure | Diagnosis | Action |
|---------|-----------|--------|
| warmup_act_div ≈ 0 | Dynamics too deterministic or noise seed not separated | Check noise implementation. If deterministic, switch to 3.1B. |
| weights changed during warmup | Plasticity not properly disabled | Fix config/code. Re-run. |
| exact ≠ closed | Protocol regression | Debug before interpreting. |
| divergent slow_l1 ≠ closed but matched_control also ≠ 0 | Warmup confound | Report net effect. If net = 0, negative. |
| divergent ≈ closed in slow_l1 | State divergence insufficient for 9D | Option B: plasticity-ON warmup (10A.2C.2). |

---

## 10. Runtime Estimate

| Arm | Per-Seed (est.) | Notes |
|-----|-----------------|-------|
| closed_loop | ~90s | 9C+9D, 12 events |
| exact_replay | ~120s | 9C+9D, 12 events replayed |
| divergent_warmup_replay | ~120s | Same as exact but with divergent warmup |
| matched_warmup_control | ~100s | Divergent warmup, no events |
| **Per seed** | **~430s** (~7 min) | |
| **2 seeds** | **~14 min** | Borderline for local |

If estimate > 15 min on local, use ECS. Parallel by seed on ECS: ~7 min.

---

## 11. Output Artifacts

| Artifact | Path |
|----------|------|
| Event logs | `results/phase10A2C_{arm}_seed{seed}_events.csv` |
| Summary CSV | `results/phase10A2C_summary.csv` |
| Summary JSON | `results/phase10A2C_summary.json` |
| Smoke notes | `docs/phase10A2C_divergent_warmup_replay_notes.md` |

---

## 12. Relationship to Prior Phases

| Phase | Relationship |
|-------|-------------|
| 10A.2 | Same mirror framework. 10A.2C extends the replay control. |
| 10A.2B.2 | Scheme E exhausted. 10A.2C is the Route A successor. |
| 10A.3 | Same 9C+9D ON. 10A.2C replaces ε with warmup divergence. |
| 10A.2B.2 decision | This design executes the Route A recommendation. |

---

## 13. Boundary

- This is a design document. No implementation, no experiment run.
- Scheme E is closed. Do not re-open.
- ε=0.10 is not tested. Do not add it.
- 9D parameters are not tuned.
- Scheduler θ is frozen.
- Plasticity is OFF during warmup (Option A). Option B is a separate
  future sub-phase (10A.2C.2) if needed.
- Warmup prehistory events (Option C) are not used.
- No digital-life / consciousness / personhood claim.
