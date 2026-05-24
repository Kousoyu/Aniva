# Phase 10A.2B.2 — Scheme E Exhaustion & Next Control Decision

> **定位：** decision only。不实现，不跑实验。
> Scheme E（initial activation perturbation）已诊断性穷尽。
> 本决策封存此路线，选定下一控制方案方向。
> No digital-life / consciousness / personhood claim。

---

## 1. Current Evidence Chain

```
10A.2     closed-loop + 9C — CLEAN NEGATIVE (mirror discovered)
10A.2B    replay control redesign — Scheme E selected over 4 alternatives
10A.2B.1  perturbed ε=0.02, 9C ON, 9D OFF — HAIRLINE POSITIVE
          (fast Δ ~4×10⁻⁷, mirror reproduced)
10A.2B    decision note — Route B: 10A.3 with ε=0.02 frozen
10A.3     9C+9D ON, ε=0.02 — CLEAN NEGATIVE
          (hard 2/2 PASS, mirror confirmed, amplification_ratio=0.0)
10A.2B.2  ε ladder [0.005, 0.01, 0.02, 0.05], 9C+9D ON
          — FAST DIVERGENCE BUT NO SLOW SIGNAL
```

---

## 2. 10A.2B.2 Key Conclusions

### 2.1 Protocol

| | Seed 42 | Seed 77 |
|--|:---:|:---:|
| Hard protocol | 4/4 PASS | 4/4 PASS |
| Mirror (exact≡closed) | ✅ all ε | ✅ all ε |
| Event count match | ✅ all ε | ✅ all ε |
| No NaN | ✅ | ✅ |
| No explosion | ✅ | ✅ |

### 2.2 Diagnostic Results

| ε | slow Δ (42) | slow Δ (77) | fast Δ (42) | fast Δ (77) | amp_ratio |
|---|:---:|:---:|:---:|:---:|:---:|
| 0.005 | 0.0 | 0.0 | 0.003 | 0.010 | 0.0 |
| 0.01 | 0.0 | 0.0 | 0.006 | 0.009 | 0.0 |
| 0.02 | 0.0 | 0.0 | 0.001 | 0.010 | 0.0 |
| 0.05 | 0.0 | 0.0 | 0.006 | 0.002 | 0.0 |

- slow_weight_l1: **bit-identical** across closed/exact/perturbed at every ε
- capture_count: **identical** across all arms and ε (seed42: 10, seed77: 11)
- tag_mass_final: **identical** across all arms and ε
- saturation_frac: **0.0** everywhere
- amplification_ratio: **0.0** everywhere

### 2.3 Diagnostic Verdict

**Scheme E (initial activation perturbation) is diagnostically exhausted.**

Fast-weight divergence exists and is measurable, but does not propagate
into the 9D tag → capture → slow_weight pipeline. The 9D capture gate
(energy × trace_mass) is insensitive to this class of state-context
perturbation at ε ≤ 0.05.

---

## 3. What Is Explicitly Prohibited

1. **Do NOT add ε=0.10.** ε=0.05 already applies ~3.2–3.8 L1 units of
   perturbation — more than 10× the hairline crack at ε=0.005. Larger ε
   would be scrambling, not perturbing.

2. **Do NOT tune 9D capture parameters.** capture_threshold, refractory,
   slow_weight_max, tag_tau stay at AnivaConfig defaults. Tuning them now
   would be post-hoc response to negative results.

3. **Do NOT select ε=0.05 as a default.** The ladder was diagnostic, not
   selective. No ε value is promoted.

4. **Do NOT enter 10A.4.** 10A.4 requires a positive or threshold-positive
   10A.3-class result. We have neither.

5. **Do NOT reframe this negative as positive.** "FAST DIVERGENCE BUT NO
   SLOW SIGNAL" is the honest verdict. No linguistic inflation.

6. **No digital-life / consciousness / personhood claim.**

---

## 4. Why Scheme E Failed to Reach Slow Structure

The perturbation was correctly designed and correctly executed:

- t=0 activation perturbation → propagates through 2000 warmup steps
- Activity divergence at warmup end is measurable
- Fast-weight divergence at run end is measurable
- Mirror sanity is confirmed at every ε

But the gap between fast-weight divergence and 9D capture is structural:

1. **Capture is gated by aggregate network state** (mean energy × trace
   mass), not by individual connection weight differences. A t=0
   activation perturbation, even at ε=0.05, does not shift these
   aggregates enough at capture decision points.

2. **Event arrivals dominate the tag pool.** Each event drives a large
   dW → large tag production. The perturbation's contribution to dW
   (via altered activations → altered Hebbian plasticity background)
   is orders of magnitude smaller than event-driven dW.

3. **Refractory coarseness.** Max possible captures at 7500 steps with
   refractory=500 is ~15. Actual captures are 10–11, near the ceiling.
   The schedule leaves little room for state-context to shift capture
   timing.

This is not a failure of execution. It is a valid finding about the
architecture: **brief initial-state perturbations, however precisely
applied, do not cross the 9D capture threshold under current defaults.**

---

## 5. Next Control Route Candidates

### Route A: Divergent Warmup Replay (Recommended)

**Concept:** Instead of perturbing t=0 activations, let the replay arm
experience a different warmup prehistory period — same seed, same
topology, same initial weights, but the first N steps (pre-event-log)
unfold differently due to a different warmup stimulus schedule or a
different seed_sched offset during warmup. After warmup, both arms
replay the identical event log.

**Mechanism:**
```
warmup phase (0 → 2000): divergent experience
  ├── arm A (reference):  standard warmup or specific warmup sequence
  └── arm B (divergent):  different warmup stimulus or no-stimulus warmup

event replay phase (2000 → 7500): identical event log
  ├── both arms receive the same events at the same steps
  └── but their pre-event state contexts (activations, traces,
      weight_cache) are different because warmup diverged
```

**Advantages:**
- No ε parameter — removes the "tuning the crack" optics entirely.
- Same seed, same topology, same event log — controls hold.
- Produces a more structural state-context difference (not a single
  t=0 perturbation, but a 2000-step divergent history).
- Aligns with the project's core principle: history leaves traces.
- If successful, the amplification is from genuine historical
  divergence, not from a synthetic perturbation magnitude.

**Risks:**
- Warmup itself becomes a confound — need a matched warmup control.
- If warmup stimuli are too strong, they could produce differences
  that are just "different training," not "different context."
- The divergent warmup design space is large — needs careful freezing.

### Route B: Yoked Cross-Seed Diagnostic

**Concept:** Generate event log from seed42, replay it on seed77 (and
vice versa). The topology and weight differences between seeds create
large, structural state-context divergence.

**Advantages:**
- Maximal difference — guaranteed to produce signal.
- Useful as a positive control: "does the 9D pipeline *ever* produce
  slow divergence under replay?"

**Risks:**
- Topology confound is so strong that it proves nothing about
  feedback context — it only proves that different networks react
  differently to the same events (trivially true).
- Cannot be a primary result — only a diagnostic sanity check.
- The question Phase 10 asks is whether feedback context within a
  *single network instance* creates structural divergence. Cross-seed
  bypasses this question.

### Route C: State-Dependent Capture Redesign

**Concept:** Redesign the 9D capture signal to be sensitive to
local/regional state context, not just global energy × trace_mass.

**Advantages:**
- Addresses the root cause: the current capture gate aggregates
  away the state-context differences we're trying to detect.
- Could make future perturbation classes detectable.

**Risks:**
- Enters mechanism redesign — breaks continuity with Phase 9D and
  all Phase 10 results to date.
- Cannot be mixed with 10A series — requires a new phase.
- Large design space, hard to constrain.

### Route D: Yoked Event-Shuffled Replay (Not Recommended)

**Concept:** Shuffle event order while preserving event type distribution.
This was discussed in 10A.2B as Scheme D and ranked below E.

**Verdict:** Rejected. Event order is the primary signal in Phase 10.
Shuffling destroys the very thing we're studying.

---

## 6. Recommendation

### Recommendation: Route A — Divergent Warmup Replay

Route A is the natural successor to Scheme E:

1. **It preserves the Phase 10 architecture.** Same θ, same 9C, same 9D,
   same seeds. Only the *prehistory* of the replay arm changes.

2. **It directly asks the Phase 10 question from a new angle.** Scheme E
   asked "does a t=0 perturbation matter?" Route A asks "does a different
   pre-event-log history matter?" — closer to the spirit of "history
   leaves traces."

3. **It removes the ε tuning optics problem entirely.** No numerical
   perturbation parameter to sweep. The divergence comes from the
   network's own dynamics under different warmup conditions.

4. **It stays within the same-seed / same-topology / same-event-log
   control framework.** The only thing that differs is the warmup
   prehistory — which is precisely the variable we want to isolate.

### Rationale Against Other Routes

- **Route B** is kept as a possible future diagnostic if Route A also
  fails, but it cannot be a primary result.
- **Route C** is a different phase — it should not be mixed with 10A.
- **Route D** was already rejected in 10A.2B.

---

## 7. Decision

```
10A.2B.2: Scheme E (initial activation perturbation) —
          diagnostically exhausted. This route is closed.

Next step: 10A.2C divergent warmup replay design.
           Not implemented in this commit.
           This is a design document, not a runner, not an experiment.

Phase 10 evidence chain continues:
  10A.1 → 10A.2 → 10A.2B → 10A.2B.1 → 10A.2B.2 → 10A.2C (next)
```

---

## 8. What Happens Next

1. **This decision note** is committed and pushed — Scheme E is formally
   closed.

2. **A separate design document** (`docs/phase10A2C_divergent_warmup_replay_design.md`)
   specifies:
   - Warmup divergence method (stimulus schedule, no-stimulus, or
     different scheduler seed during warmup)
   - Matched warmup control design
   - Arms, metrics, success criteria
   - Frozen parameters inherited from 10A series

3. **No ε ladder follow-up.** No ε=0.10. No 9D parameter sweep.

4. **10A.4 is not entered** until a positive or threshold-positive
   result is obtained from a redesigned control.

---

## 9. Boundary

- Scheme E is closed. Do not re-open.
- ε ∈ {0.005, 0.01, 0.02, 0.05} results are final.
- No 9D parameter tuning.
- No new ε values.
- No 10A.4.
- No digital-life / consciousness / personhood claim.
- 10A.2C design is the next step — but in a separate commit.
