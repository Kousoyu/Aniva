# Phase 10A.2B — Matched Replay Control Redesign

> **定位：** design only。不实现，不跑实验。
> 10A.2 暴露了 matched replay 在 same seed + same initial state + exact
> event log 下退化为确定性等价。10A.2B 不是否定 10A.2，而是重新设计 replay
> control 使其拥有真正的 feedback-context contrast。
>
> 不改 10A.2 结论。不调 θ。不开 9D。

---

## 1. Background

### 1.1 What 10A.2 Established

| Finding | Detail |
|---------|--------|
| Hard protocol | 2/2 PASS |
| Replay exactness | 0 hash mismatch, EXACT |
| closed vs replay fast weight | **bit-identical** for both seeds |
| Scientific signal | CLEAN NEGATIVE |

The matched replay was technically perfect — every event timestamp, type,
and payload hash matched. But perfect replay under same seed + same initial
state + deterministic dynamics *guarantees* identical trajectories.

### 1.2 Root Cause

The 9C event-pair plasticity pipeline is purely state-agnostic at the
moment of event arrival:

```
dW = f(trace, phi; θ_9C)
```

Where:
- `trace` = accumulated phi over time (identical per-step for same event history)
- `phi` = spatial activation vector of current event (identical per payload hash)
- `θ_9C` = frozen plasticity parameters

When all three inputs are identical, `dW` is deterministic — bit identical.

The feedback loop `state → scheduler → event → env` only determines *which*
events are chosen. Once the event log is recorded and replayed exactly,
the feedback context is erased from the 9C pipeline.

### 1.3 What This Does NOT Mean

- Does NOT mean "feedback context doesn't matter."
- Does NOT mean "closed-loop = open-loop always."
- Does NOT mean we should skip to 10A.3 with the same replay design.

It means: **the current replay control cannot *detect* feedback-context
effects, because it removes the feedback contrast entirely.**

### 1.4 The Mirror Problem

A control that shares seed, initial state, and event log with the
experimental arm is a *mirror*, not a *fork*. It reflects back the
same trajectory. To see whether the feedback context matters, we
need the replay to diverge from the closed-loop trajectory while
still being attributable to the same event history.

---

## 2. Design Goal

Redefine the matched replay control so that:

1. **Event log comparability is preserved** — the same events (type,
   timing, phi) are applied.
2. **Internal state trajectory diverges** — the system state at the
   moment of each event arrival is *not* the same as in closed_loop.
3. **The divergence is attributable** — we know *why* the state
   differs, and it is not an unmeasured confound.
4. **The contrast is measured** — we can quantify whether different
   state context at event arrival produces different 9C plasticity
   outcomes.

---

## 3. Candidate Control Schemes

### 3.1 Scheme A: Divergent Warmup Replay

```
Closed_loop:
  t=0 ─────── warmup (2000) ─────── events (t=2000..7500)

Replay:
  t=0 ─── perturbed warmup (2000) ─── replay SAME events (t=2000..7500)
              ↑ different noise seed / different initial activity
```

**Mechanism:** The replay arm uses the same unit topology (same seed for
positions/connections) but a different noise seed during warmup. By t=2000,
the system state has diverged from closed_loop. The same events are then
replayed onto this different state.

**Advantages:**
- Same topology — no seed confound
- State divergence is natural (noise-driven) rather than artificial
- Warmup divergence can be calibrated (how much noise difference?)

**Risks:**
- Noise-seed difference may produce negligible state divergence
- Warmup divergence itself introduces a confound: is it the feedback context
  or the warmup history that matters?
- Need a "matched warmup control" to isolate warmup effect from replay effect

**Variants:**
- A1: Different noise seed during warmup only
- A2: Perturbed initial activations at t=0 (same noise thereafter)
- A3: Different initial activity distribution (e.g., seed L-biased vs R-biased)

### 3.2 Scheme B: Yoked Replay to Different Seed

```
seed42 closed_loop events → replayed onto seed77 topology
seed77 closed_loop events → replayed onto seed42 topology
```

**Mechanism:** The event log from one seed's closed_loop run is injected
into the other seed's initial body. Same events, completely different
topology and initial state.

**Advantages:**
- Maximum state divergence — guaranteed
- No artificial perturbation needed

**Risks:**
- Topology confound is *very* strong — seed77 has different unit positions,
  connections, and initial weights than seed42
- Any fast weight difference could be entirely due to topology, not feedback
  context
- Cannot isolate "feedback context" from "different brain"
- Suitable as **diagnostic**, not as primary criterion

### 3.3 Scheme C: Stale-State / Delayed Replay

```
Closed_loop:
  obs(t) → scheduler → event(t) → state(t+1)

Replay:
  recorded event(t) → applied at t+Δ
  OR
  scheduler reads obs(t-Δ) instead of obs(t)
```

**Mechanism:** Introduce a temporal offset between the state that *would*
have triggered an event and the state that *receives* it in replay. The
event log is the same, but the timing is shifted.

**Advantages:**
- Directly tests state-event coupling
- Same topology, same seed

**Risks:**
- Changes the temporal structure of events (IEI distribution)
- Δ must be preregistered — can't tune to maximize effect
- "Same event log" property is weakened (timestamps differ)

**Variants:**
- C1: Fixed delay Δ applied to all events
- C2: Permuted event order (same events, shuffled timing within warmup..total_steps)

### 3.4 Scheme D: Matched Distribution Random Control

```
Closed_loop:
  events at t₁, t₂, ... with types τ₁, τ₂, ... (from scheduler)

Random control:
  same N events
  timing: uniform random from [warmup, total_steps), no replacement
  types: matched to closed_loop distribution (e.g., same L/R ratio)
```

**Mechanism:** Preserve event count and type distribution, but destroy
the temporal coupling between state and event. This already exists as
10A.2's `random_uniform_control` arm.

**Advantages:**
- Already implemented
- Tests whether event timing/order matters beyond count/type distribution

**Risks:**
- 10A.2 random_uniform already showed ~zero difference from closed_loop
- Not a "feedback context" test — it removes all structure, not just feedback
- If random ≈ closed, it means ordering doesn't matter for fast weight,
  not that feedback doesn't matter

### 3.5 Scheme E: Same Event Log + Perturbed Initial State

```
Closed_loop:
  init_state_0 → warmup → events

Replay:
  init_state_0 + ε → warmup → replay SAME events
         ↑
    small perturbation to activations/energy at t=0
```

**Mechanism:** Same seed (same topology), same event log, same noise seed,
but initial per-unit activations are perturbed by a small ε. The perturbation
propagates through warmup, creating a different (but topologically identical)
state at event onset times.

**Advantages:**
- Closest to "different person with same brain receiving same events"
- Topology identical — no seed confound
- Perturbation magnitude is preregisterable
- Most directly tests "does state context matter for plasticity?"

**Risks:**
- Perturbation may dampen out during warmup (2000 steps is long)
- If ε is too small → no divergence → same as 10A.2
- If ε is too large → essentially a different seed → confound
- ε magnitude must be preregistered based on known activation scales (~0.01–0.05)

---

## 4. Recommended Priority

### Primary: Scheme E — Same Event Log + Perturbed Initial State

Best scoped: isolates "different state context" with minimal confounds.
Same topology, same event log, same noise — only initial activations differ.

**Preregistration requirement:** ε magnitude, perturbation pattern (uniform
per-unit? region-biased?), and whether perturbation is applied to activations,
energy, or both.

### Secondary: Scheme A1 — Different Noise Seed During Warmup

If Scheme E shows no divergence (perturbation dampened out), Scheme A1
tests whether sustained noise-path divergence during warmup creates
detectable state difference at event times.

### Diagnostic: Scheme B — Yoked Cross-Seed

Useful for bounding: if cross-seed replay shows *large* divergence, it
confirms the 9C pipeline *can* produce different fast weights from the
same events — just not when state is identical. If cross-seed also shows
zero divergence, the 9C pipeline is fundamentally event-log-determined.

### NOT recommended as primary: Scheme C (Delayed Replay), Scheme D (Random)

- C changes temporal structure, weakening "same event log" property
- D is already covered by 10A.2 random_uniform (≈ zero delta)

---

## 5. Proposed 10A.2B Layered Plan

```
10A.2B.0: this design document
10A.2B.1: Scheme E smoke — perturbed initial state replay (2 seeds)
10A.2B.2: Scheme A1 smoke — divergent warmup replay (2 seeds)
10A.2B.3: Scheme B diagnostic — yoked cross-seed replay (2 seeds, 2 cross pairs)
10A.2B.4: choose primary control for 10A.3 based on 10A.2B.{1,2,3} results
```

Each sub-phase is a separate commit, separate run, no post-hoc tuning.

---

## 6. Success / Failure Logic

| Outcome | Interpretation |
|---------|---------------|
| Scheme E (perturbed) shows divergence | State context at event arrival affects 9C plasticity. Fast layer *does* carry feedback-context signal. Proceed to 10A.2C to characterize. |
| Scheme E still identical, but Scheme A1 (noise warmup) diverges | Perturbation magnitude or dampening issue. Noise-path divergence over 2000 steps is needed. Scheme A1 becomes primary. |
| Both E and A1 identical, but Scheme B (cross-seed) diverges | Fast weight divergence exists but only from topology+state compound, not from state context alone. Cannot attribute to feedback. Need stronger perturbation or different approach. |
| All schemes identical | 9C fast weight is fundamentally event-log-determined at this timescale/event-count. The "watermark" layer may not carry feedback-context information. This is a valid scientific result — it would mean feedback context effects (if they exist) must be sought in slow consolidation (9D) or longer timescales. |

---

## 7. Anti-Cheat

- All schemes: scheduler disabled in replay arms
- All schemes: no state read by replay player
- All schemes: event log recorded from closed_loop, not generated in replay
- Scheme E: ε preregistered, not tuned per seed
- Scheme A1: noise seed difference preregistered
- Scheme B: cross-seed pairing preregistered (42→77 and 77→42)
- No post-hoc selection of "best" scheme based on results
- All schemes reported, not just the one that shows divergence

---

## 8. Boundary

- 10A.2 is a CLEAN NEGATIVE — not a failure, not overwritten.
- 10A.2B is a control redesign, not a parameter tuning exercise.
- Scheduler θ is frozen (10A.0).
- Decision interval is frozen (10A.1B, interval=250).
- 9C event-pair plasticity remains ON.
- 9D consolidation remains OFF.
- No entry to 10A.3 before a redesigned replay control is validated.
- No digital-life / consciousness / personhood claim.
