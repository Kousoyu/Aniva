# Phase 10A.2B.2 — Epsilon Sensitivity Ladder Design

> **定位：** design only。不实现，不跑实验。
> **性质：** diagnostic ladder，不是 tuning。
> **目标：** 诊断 9D slow consolidation 对 initial-activation state-context
> perturbation 的 sensitivity threshold，不是找一个"好看的 ε"。
>
> 不改 10A.3 结论。不改 10A.2B.1 结论。不进入 10A.4。
> No digital-life / consciousness / personhood claim。

---

## 1. Background

### 1.1 Evidence Chain Leading Here

```
10A.2     closed-loop + 9C — CLEAN NEGATIVE (mirror)
10A.2B    replay control redesign — Scheme E selected
10A.2B.1  perturbed ε=0.02, 9C ON, 9D OFF — HAIRLINE POSITIVE
          (fast Δ ~4×10⁻⁷ of total, mirror reproduced)
10A.2B    decision note — Route B (10A.3 with ε=0.02 frozen)
10A.3     +9D, ε=0.02 — CLEAN NEGATIVE
          (hard 2/2 PASS, mirror confirmed, amplification_ratio=0.0)
```

### 1.2 What 10A.3 Told Us

ε=0.02 perturbed replay produced identical slow_weight to closed_loop
in both seeds. amplification_ratio = 0.0. The 9D capture mechanism
(energy × trace_mass gate) did not amplify or preserve the hairline
fast-weight divergence into slow structure.

This is a valid finding, not a failure. But it leaves an open question:
**at what ε, if any, does 9D capture become sensitive to initial
activation perturbation?**

### 1.3 Why This Ladder Now

The pre-registered fallback from the 10A.2B decision note:

> If 10A.3 slow consolidation shows no amplification:
> Return to 10A.2B.2 epsilon sensitivity as diagnostic.

The ladder was always intended as a diagnostic after a negative 10A.3,
not as a pre-selection tool. Now is the time to run it.

---

## 2. Positioning: Diagnostic, Not Tuning

This is the most important section of this design.

### 2.1 What This Ladder IS

- A systematic probe of 9D sensitivity to perturbation magnitude.
- A way to characterize whether the 9D capture pipeline has a threshold
  above which state-context divergence becomes detectable.
- A diagnostic that produces a curve (ε vs. slow Δ), not a winner.

### 2.2 What This Ladder IS NOT

- NOT a tool to find "an ε that works" and promote it to default.
- NOT a post-hoc justification for re-running 10A.3 with a larger ε.
- NOT a way to inflate 10A.2B.1's hairline positive into a strong positive.
- NOT a replacement for 10A.3 — 10A.3 stands as a clean negative at ε=0.02.
- NOT a gate for 10A.4.

### 2.3 Selection Prohibition

No ε value from this ladder may become a pipeline default without a
separate, pre-registered design document that explicitly promotes it.
The ladder is read-only on the parameter space.

---

## 3. Frozen Parameters

### 3.1 Unchanged from 10A.3

| Parameter | Value | Source |
|-----------|-------|--------|
| seeds | 42, 77 | 10A.0 |
| unit_count | 300 | 10A.0 |
| total_steps | 7500 | 10A.0 |
| warmup | 2000 | 10A.0 |
| decision_interval | 250 | 10A.1B |
| pulse_duration | 80 | 10A.0 |
| Scheduler θ | w=5.0, b_none=+1.0, b_L/R=-1.5, b_sim=-3.0, τ=1.0 | 10A.0 |
| 9C event-pair plasticity | ON | 10A.2 |
| 9C trace_tau | 1000.0 | 10A.2 |
| 9C target_update_l1 | 1e-4 | 10A.2 |
| 9C gate_mode | soft_trace_gate | 10A.2 |
| 9C trace_gate_ref | 3e-2 | 10A.2 |
| 9C gate_power | 1.0 | 10A.2 |
| 9D consolidation | ON | 10A.3 |
| 9D tag_tau | 5000.0 | AnivaConfig default |
| 9D capture_threshold | 0.5 | AnivaConfig default |
| 9D slow_weight_max | 0.1 | AnivaConfig default |
| 9D slow_weight_rate | 0.1 | AnivaConfig default |
| 9D refractory | 500 | AnivaConfig default |
| perturbation_target | activations only, t=0 once | 10A.2B.1 |
| perturbation_distribution | uniform [-ε, +ε], zero-mean, clip [0,1] | 10A.2B.1 |
| perturb_seed_offset | +3000 | 10A.2B.1 |

### 3.2 The Only Free Parameter: ε

| ε Variant | Status |
|-----------|--------|
| ε = 0.005 | NEW |
| ε = 0.01 | NEW |
| ε = 0.02 | Already run (10A.2B.1 + 10A.3); re-run for ladder consistency |
| ε = 0.05 | NEW |

### 3.3 Why Not ε = 0.10

ε=0.10 is excluded from the default ladder for these reasons:

1. A uniform [-0.10, +0.10] perturbation on activations ∈ [0,1] clips
   heavily — the distribution is no longer uniform, breaking the
   perturbation model.
2. At this magnitude, "perturbation" becomes "scramble" — it ceases to
   be a meaningful probe of sensitivity to initial conditions.
3. If all four ε tiers (0.005–0.05) are negative, ε=0.10 requires a
   separate design document — it is not added incrementally.

Exception: if ε=0.05 produces a clear slow signal while ε≤0.02 does not,
a separate ε=0.10 probe may be warranted as a saturation check. That
decision is made after seeing the 0.05 result, in a new design document.

---

## 4. Arms

### 4.1 Per-ε Variant: 3 Arms

| Arm | Scheduler | Event Source | 9C | 9D | Purpose |
|-----|-----------|-------------|:--:|:--:|---------|
| closed_loop | Active | State feedback | ON | ON | Reference trajectory |
| exact_replay | Disabled | Replayed from closed | ON | ON | Mirror sanity, per ε |
| perturbed_replay | Disabled | Replayed from closed | ON | ON | Primary test, per ε |

### 4.2 Optional: no_event_control

| Arm | 9C | 9D | Purpose |
|-----|:--:|:--:|---------|
| no_event_control | ON | ON | Null baseline |

Included only if total runtime estimate allows. If omitted, the 10A.3
no_event baseline (captures=0, slow_l1=0.0) serves as reference.

### 4.3 Per-ε Replay Protocol

For each ε tier:

1. Run closed_loop with scheduler active → produce event log E_seed.
2. Run exact_replay: same seed, same initial state, replay E_seed.
   Assert: trace hash matches, fast_l1 matches, slow_l1 matches.
3. Run perturbed_replay: same seed, activations perturbed at t=0 by
   current ε, replay E_seed.
   Compare: slow_l1, capture_count, tag_mass vs closed_loop.

Each ε tier is self-contained — its exact_replay validates the mirror
for that specific perturbation magnitude.

---

## 5. Metrics

### 5.1 Primary (Per ε, Per Seed, Per Arm)

| Metric | Source | What It Measures |
|--------|--------|-----------------|
| slow_weight_l1 | `sum(abs(core._slow_weight_cache))` | Total slow structural mass |
| slow_weight_max_abs | `max(abs(core._slow_weight_cache))` | Saturation check |
| fast_weight_l1 | `sum(abs(core._weight_cache))` | Fast weight reference |
| capture_count | `len(core._consolidation_ledger)` | How many times capture fired |
| tag_mass_final | `sum(abs(core._tag_cache))` | Residual tags at end |
| n_tagged_connections | `sum(core._tag_cache > 0)` | How many connections received tags |
| saturation_frac | fraction of `|effective| ≥ 0.999` | Saturation ceiling check |
| max_abs_weight | `max(abs(core._weight_cache))` | Explosion check |
| nan_count | 0 required | Health |
| replay_hash_mismatch_count | 0 required | Replay fidelity |
| wall_time_s | — | Runtime tracking |

### 5.2 Perturbation Characterization (Per ε, Per Seed)

| Metric | Computation |
|--------|-------------|
| perturb_l1 | `sum(abs(actual_eps))` |
| perturb_l2 | `sqrt(sum(actual_eps²))` |
| perturb_max | `max(abs(actual_eps))` |
| act_div_at_warmup_end | L2 distance of activations (perturbed vs exact) at step 2000 |

### 5.3 Cross-Arm Deltas (Per ε, Per Seed)

| Delta | Computation |
|-------|-------------|
| closed_vs_exact_slow_l1 | `slow_l1(closed) - slow_l1(exact)` |
| closed_vs_perturbed_slow_l1 | `slow_l1(closed) - slow_l1(perturbed)` |
| exact_vs_perturbed_slow_l1 | `slow_l1(exact) - slow_l1(perturbed)` |
| closed_vs_perturbed_fast_l1 | `fast_l1(closed) - fast_l1(perturbed)` |
| amplification_ratio | `|exact_vs_perturbed_slow_l1| / |exact_vs_perturbed_fast_l1|` |
| capture_delta | `captures(closed) - captures(perturbed)` |
| tag_mass_delta | `tag_mass(closed) - tag_mass(perturbed)` |

### 5.4 Ladder-Wide Diagnostics (Across ε)

| Diagnostic | Computation |
|------------|-------------|
| ε vs slow Δ curve | Plot exact_vs_perturbed_slow_l1 vs ε |
| ε vs fast Δ curve | Plot exact_vs_perturbed_fast_l1 vs ε |
| ε vs amplification_ratio | Plot amplification_ratio vs ε |
| ε vs capture_delta | Plot capture_delta vs ε |
| monotonicity check | Is slow Δ monotonic in ε? |
| threshold identification | Lowest ε with |slow Δ| > 0 (if any) |

---

## 6. Success Criteria

### 6.1 Hard Protocol (Per ε Tier)

| # | Criterion | Threshold |
|---|-----------|-----------|
| P1 | No NaN | 0 |
| P2 | No explosion | max_abs_weight < 10.0 |
| P3 | Replay hash mismatch = 0 | Both replay arms |
| P4 | Event count match | exact = perturbed = closed |
| P5 | exact ≈ closed (mirror) | `|closed_vs_exact_slow_l1| / closed_slow_l1 < 0.01` |

All 5 must pass for a given ε tier to be valid. If any ε tier fails
P3 or P5, that tier is flagged and excluded from interpretation.

### 6.2 Soft — Diagnostic Outcomes

| Pattern | Interpretation |
|---------|---------------|
| All ε: slow Δ = 0 | 9D capture is insensitive to this perturbation class at ε ≤ 0.05. Abandon initial-activation perturbation as primary route. |
| slow Δ > 0 only at ε = 0.05 | Threshold effect. 9D becomes sensitive between 0.02 and 0.05. Classify, do not promote ε=0.05 as default. |
| slow Δ increases monotonically with ε | Sensitivity curve established. Report shape (linear, superlinear, saturating). No single ε is "the answer." |
| fast Δ increases but slow Δ = 0 at all ε | 9D capture gate (energy × trace_mass) filters out weight-level divergence. Capture mechanism is robust to this perturbation class. |
| One seed shows effect, other doesn't | Seed-dependent sensitivity. Report per-seed, do not average. |
| Saturation appears (saturation_frac > 0.5) | ε too large for valid interpretation. Flag, do not use that ε tier. |

---

## 7. Decision Rules (Locked Before Run)

1. **Exact replay MUST mirror closed_loop at every ε.** If any ε tier
   fails P5, the 9D pipeline has ε-dependent nondeterminism — debug
   before interpreting any result.

2. **Do NOT select a "best ε."** The ladder produces a curve, not a
   candidate. No ε value is promoted to default based on this ladder.

3. **Do NOT re-interpret 10A.3.** ε=0.02 negative stands. If ε=0.05
   shows signal, that does not make 10A.3 "almost positive."

4. **Do NOT tune 9D parameters.** capture_threshold, refractory,
   slow_weight_max, tag_tau stay at AnivaConfig defaults regardless
   of ladder outcome.

5. **If all ε negative:** the perturbation route via initial activation
   (Scheme E) is exhausted. Next step is a new design document — not a
   larger ε, not a different perturbation target.

6. **If threshold found (e.g., signal at 0.05 but not ≤0.02):** classify
   as "9D has a sensitivity threshold between 0.02 and 0.05 for this
   perturbation class." This is a characterization, not a recommendation.

7. **All results per-seed, per-ε.** No averaging across seeds or ε tiers
   for primary claims.

---

## 8. Interpretation Guardrails

### 8.1 If Fast Δ Increases with ε but Slow Δ Does Not

This is the most likely outcome given 10A.3. It means:

- Larger ε → larger activation divergence → larger fast-weight divergence.
- But the 9D capture gate (energy × trace_mass) aggregates over the full
  network state, and the perturbation's effect on these aggregates is
  washed out relative to event-driven dynamics.
- The 9D pipeline is structurally robust to initial-activation perturbations
  of this class.

This is a valid finding. It does not mean 9D is broken. It means state
context at the activation level is not the primary driver of capture
decisions — event timing is.

### 8.2 If Slow Δ Appears at Higher ε

This would mean:

- At some ε, the perturbation is large enough to shift aggregate state
  (energy, trace_mass) at capture decision points.
- The capture mechanism is sensitive to state context, but the threshold
  is above ε=0.02.
- This is a threshold characterization, not proof that "feedback context
  matters at natural scales."

ε=0.02 was chosen as a "small" perturbation. If the threshold is at 0.05,
the required perturbation is 2.5× larger — not a micro-perturbation.

### 8.3 If One Seed Diverges

Seed-dependent sensitivity. Report both seeds. This is common in small
networks (300 units) with stochastic event generation. It does not
invalidate the finding — it characterizes it.

---

## 9. Runtime Estimate

| Component | Per ε Tier (est.) | Notes |
|-----------|-------------------|-------|
| closed_loop | ~90s | 9C+9D, 12 events, 10–11 captures |
| exact_replay | ~120s | Same 9C+9D load |
| perturbed_replay | ~110s | Same 9C+9D load |
| no_event (optional) | ~80s | Only if runtime allows |
| **Per ε, per seed** | **~320s** (5.3 min) | Without no_event |
| **4 ε × 2 seeds** | **~43 min** | With no_event: ~53 min |

- 43–53 minutes exceeds the 15-minute local threshold.
- **Must run on ECS (Alibaba Cloud 4C8G).**
- Estimate-only run before full execution to confirm per-tier timing.

---

## 10. Output Artifacts

| Artifact | Path |
|----------|------|
| Event logs | `results/phase10A2B2_eps{epsilon}_{arm}_seed{seed}_events.csv` |
| Summary CSV | `results/phase10A2B2_summary.csv` |
| Summary JSON | `results/phase10A2B2_summary.json` |
| Smoke notes | `docs/phase10A2B2_epsilon_sensitivity_ladder_notes.md` |

---

## 11. Relationship to Prior Phases

| Phase | Relationship |
|-------|-------------|
| 10A.2B.1 | ε=0.02 fast-only served as baseline. ε=0.02 is re-run here with 9D ON for ladder consistency. |
| 10A.3 | ε=0.02 with 9D ON is the anchor point. This ladder extends ε in both directions (0.005, 0.01, 0.05). |
| 10A.2B decision | Pre-registered fallback: "if 10A.3 negative, return to ε ladder as diagnostic." This is that return. |
| 10A.4 | Not entered. 10A.4 requires a positive 10A.3 or a redesigned approach. |

---

## 12. What Happens After

### If ladder is fully negative (all ε: slow Δ = 0)

→ Abandon Scheme E (initial activation perturbation) as the primary
route to slow-structure divergence.
→ New design document: alternative perturbation class or divergent
warmup approach.

### If ladder shows threshold (signal at ε=0.05)

→ Characterize, do not promote.
→ Decision note: whether threshold characterization is sufficient to
warrant 10A.4, or whether a new perturbation class is needed.

### If ladder shows monotonic sensitivity

→ Report the curve.
→ The question becomes: is the sensitivity at biologically plausible
perturbation scales, or does it require unnaturally large ε?

---

## 13. Boundary

- 9C event-pair plasticity is ON.
- 9D consolidation is ON.
- Scheduler θ is frozen from 10A.0.
- Decision interval is frozen from 10A.1B.
- All 9D parameters are AnivaConfig defaults.
- ε ∈ {0.005, 0.01, 0.02, 0.05}. No ε=0.10 without separate design.
- Perturbation target, distribution, timing frozen from 10A.2B.1.
- This is a diagnostic ladder, not a tuning exercise.
- No ε value is promoted to default.
- 10A.3 negative stands unchanged.
- 10A.2B.1 hairline positive is not inflated.
- No digital-life / consciousness / personhood claim.
