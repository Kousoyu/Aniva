# Phase 10A.2B — Next-Step Decision Note

> **定位：** decision only。不实现，不跑实验。
> 在 10A.2B.1（hairline positive）之后，决定下一步方向。
> 两条候选路线：ε sensitivity ladder vs. 10A.3 slow consolidation。
> 此文档锁定决策，防止事后"感觉哪个顺眼就走哪个"。

---

## 1. Current Evidence Chain

```
10A.0     design freeze + preregistration
10A.1     scheduler plumbing smoke — CAVEATED (seed77 none_rate=0.27)
10A.1B    calibration variant (interval=250) — CLEAN PASS, becomes default
10A.2     closed-loop + 9C fast plasticity — CLEAN NEGATIVE
          (exact matched replay ≡ closed, bit-identical)
10A.2B    matched replay control redesign — 5 candidate schemes
10A.2B.1  Scheme E: perturbed initial state replay (ε=0.02) — HAIRLINE POSITIVE
          (exact replay mirror reproduced, perturbed ≠ closed, effect ~4×10⁻⁷)
```

---

## 2. 10A.2B.1 Key Results

| Metric | Seed 42 | Seed 77 |
|--------|---------|---------|
| closed_vs_exact | 0.0 | 0.0 |
| closed_vs_perturbed | +0.00080134 | −0.00046194 |
| effect / total fast L1 | ~4.3×10⁻⁷ | ~2.5×10⁻⁷ |
| Exact replay mirror | REPRODUCED | REPRODUCED |
| Perturbed replay crack | DETECTED | DETECTED |

**Verdict:** Hairline positive — the mirror has a measurable crack, but
the crack is 4 orders of magnitude smaller than the fast weight scale.
The 9C pipeline is strongly event-log-dominant.

---

## 3. Two Candidate Routes

### Route A: 10A.2B.2 — Epsilon Sensitivity Variant

**What:** Run a fixed ladder of ε values to see whether fast-weight
divergence scales monotonically with initial perturbation magnitude.

| Variant | ε |
|---------|-----|
| 10A.2B.1 | 0.02 (done) |
| 10A.2B.2A | 0.01 |
| 10A.2B.2B | 0.05 |

**Question:** Does `Δ(closed-perturbed)` scale with ε, and if so, is the
relationship linear, thresholded, or saturating?

**Advantages:**
- Characterizes the system's sensitivity to initial conditions.
- If ε=0.05 produces a meaningfully larger Δ, it informs 10A.3 design.
- If even ε=0.05 produces negligible Δ, fast layer is definitively
  event-log-dominant — strong negative with internal replication.

**Risks:**
- Looks like "tuning the crack larger" — bad optics.
- If ε=0.05 produces a conveniently large Δ, there's temptation to use
  that as the 10A.3 baseline, which is post-hoc selection.
- The ladder values (0.01, 0.02, 0.05) were not preregistered before
  seeing the 10A.2B.1 result — partial post-hoc.
- Could delay 10A.3 indefinitely while "characterizing the crack."

**Mitigations:**
- Must preregister the full ladder before running any variant.
- Must commit to using ε=0.02 for 10A.3 regardless of ε=0.05 result.
- The ladder is diagnostic only, not a selection tool.

### Route B: 10A.3 Slow Consolidation Design with Redesigned Replay

**What:** Proceed to design 10A.3, which opens 9D consolidation for the
first time in the Phase 10 pipeline. Use the Scheme E perturbed replay
(ε=0.02) as the redesigned replay control.

**Arms (draft):**

| Arm | 9C | 9D | Event Source |
|-----|:--:|:--:|-------------|
| closed_loop | ON | ON | Scheduler from state |
| exact_replay | ON | ON | Mirror sanity check |
| perturbed_replay | ON | ON | Scheme E, ε=0.02 |
| no_event_control | ON | ON | Null baseline |

**Question:** Does 9D slow consolidation amplify, preserve, or ignore the
hairline fast-weight divergence between perturbed and exact replay?

**Advantages:**
- Directly addresses Phase 10's core question: does closed-loop event
  history deposit into slow structure?
- The hairline fast-weight crack is already established — the question
  is whether slow consolidation acts as an amplifier.
- Aligns with the Phase 10 layered design (10A.1 plumbing → 10A.2 fast
  → 10A.3 slow).
- ε=0.02 stays frozen — no suspicion of post-hoc tuning.
- If 10A.3 is negative, ε sensitivity can still be done afterward as
  diagnostic.

**Risks:**
- If the fast-weight divergence is too small, slow consolidation may
  not amplify it — 10A.3 may also be negative or ambiguous.
- Opens two variables at once (redesigned replay + 9D), though the
  replay redesign is now well-characterized.
- If 10A.3 is negative, we won't know whether ε is too small or the
  mechanism genuinely doesn't carry feedback context to slow structure.

**Mitigations:**
- exact_replay arm provides mirror sanity check within 10A.3.
- If 10A.3 is negative, return to 10A.2B.2 epsilon sensitivity as a
  diagnostic — NOT as a way to "find an ε that works."
- The decision to return to Route A is preregistered here.

---

## 4. Recommendation

### Recommendation: Route B — 10A.3 Design First

**Do not run epsilon sensitivity now.**

Reasons:

1. **Phase 10's core question is about slow structure, not fast trace.**
   The fast layer was always a stepping stone. 10A.2B.1 has answered the
   fast-layer question: the mirror crack exists but is microscopic. The
   natural next question is whether the "bone layer" (9D) preserves or
   amplifies it.

2. **ε tuning is a slippery slope.** Once we start a sensitivity ladder,
   it's hard to avoid the temptation to use the "best-looking" ε for
   10A.3. Pre-committing to ε=0.02 for 10A.3 removes this temptation.

3. **If 10A.3 is negative, the ε ladder is still available.** Running
   the ladder afterward as a diagnostic (not as a selection tool) is
   cleaner — the question becomes "why didn't the hairline crack
   propagate?" rather than "which ε makes it propagate?"

4. **Two-variable risk is manageable.** The perturbed replay is now
   well-characterized (mirror reproduced, crack detected, scale known).
   Adding 9D is the only truly new variable in 10A.3.

### Fallback Rule (Preregistered Here)

If 10A.3 slow consolidation shows:
- **No amplification** (slow structure Δ ≈ fast structure Δ, still ~10⁻⁷):
  Return to 10A.2B.2 epsilon sensitivity as diagnostic. The question is
  whether a larger initial perturbation creates a larger fast-weight crack
  that slow consolidation could plausibly detect.

- **Amplification** (slow structure Δ > fast structure Δ):
  The system is working as hypothesized — state context propagates through
  fast traces into slow structure. Proceed to 10A.4 formal validation.

- **Negative in one seed only:**
  Seed-dependent effect. Report per-seed, do not average. If one seed
  shows amplification and the other doesn't, that's a finding — not a
  failure.

---

## 5. What NOT to Do

- Do NOT run ε=0.05 and then use that result to choose ε for 10A.3.
- Do NOT reinterpret 10A.2B.1 as strong positive to justify skipping
  further controls.
- Do NOT open 10A.3 implementation before design freeze.
- Do NOT run an informal ε scan to "see what looks good."
- Do NOT drop exact_replay from 10A.3 — it's the mirror sanity check.

---

## 6. Decision

```
Next step: Phase 10A.3 slow consolidation design.
Replay control: Scheme E perturbed replay (ε=0.02, frozen from 10A.2B.1).
Epsilon sensitivity: deferred to after 10A.3, only if 10A.3 is negative.
```

This decision is locked in this commit. If circumstances change, a new
decision note is written — this one is not edited retroactively.

---

## 7. Boundary

- 10A.2 is a CLEAN NEGATIVE — not re-litigated.
- 10A.2B.1 is a HAIRLINE POSITIVE — not inflated.
- ε=0.02 is frozen.
- 10A.3 design is the next step — implementation only after design freeze.
- No digital-life / consciousness / personhood claim.
