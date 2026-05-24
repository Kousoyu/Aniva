# Phase 10 Public Release and Next Route Decision

**Date:** 2026-05-24  
**Status:** public_release_route_decision  
**Public tag:** `v0.0.1-public`  
**Repository:** `Kousoyu/Aniva`

---

## 1. Positioning

This document records the first public release route decision after Aniva became public.

It is not:

- a new experiment design
- a mechanism proposal
- a Phase 11 implementation plan
- a claim of consciousness
- a claim of personhood
- a claim that digital life has been achieved

It is a route-control document.

The goal is to state what Phase 10 has actually established, what it has ruled out, and what the next safe research direction should be.

---

## 2. Public release status

Aniva is now public as an early research prototype.

The current public release snapshot is:

```text
v0.0.1-public
```

The repository now includes:

- updated `README.md`
- MIT `LICENSE`
- `docs/README.md`
- `SECURITY.md`
- `CONTRIBUTING.md`
- Phase 10E/10F diagnostic chain summary
- CI-backed pytest workflow
- public boundary statements

The current public boundary is explicit:

```text
Aniva does not claim to validate consciousness, personhood, or that digital life has been achieved.
```

---

## 3. What Phase 10 established

Phase 10 began with a large question:

```text
Can world-generated / closed-loop event history shape a digital individual,
rather than merely executing designer-specified event schedules?
```

The answer is not complete yet.

But Phase 10 did establish several important constraints.

---

### 3.1 Closed-loop scheduling works as plumbing

Phase 10A showed that a state-dependent scheduler can generate event histories without directly writing structure.

This mattered because the project needed to move beyond fixed, designer-scripted event sequences.

However, early replay controls also showed that exact replay under identical state is deterministic mirror behavior, not a meaningful contrast.

This forced stricter control design.

---

### 3.2 Fast plasticity can react, but replay controls must be real contrasts

Phase 10A.2 showed that matched replay under same seed, same initial state, and same event log becomes equivalent to closed loop.

This was not a failure of the system.

It was a failure of the contrast.

The mirror was too perfect.

The later perturbed replay and divergent warmup routes tested whether small state-context differences could produce meaningful structural differences.

Those tests produced weak or negative results.

---

### 3.3 Slow consolidation did not amplify the observed state-context differences

Phase 10A.3 and subsequent diagnostic routes showed that the current slow consolidation mechanism did not amplify the small fast-weight differences into robust slow-structure differences.

This closed the immediate route:

```text
small h/context perturbation → fast crack → slow structural amplification
```

under the tested mechanisms.

---

### 3.4 Historical context trace h[u] exists, but is not enough

Phase 10D introduced a historical context trace:

```text
h[u]
```

It can store warmup history.

This was a positive plumbing result.

But later diagnostics showed that current h[u] is not a sufficient direct upstream driver for tag formation or 9C support.

In other words:

```text
h[u] stores history,
but current h[u] does not directly decide where event-pair support appears.
```

That distinction matters.

History exists in the system, but this particular descriptor is not yet the right control variable for the plasticity support path.

---

### 3.5 Tag formation support is trace×phi geometry

The Phase 10E/10F diagnostic branch closed a major uncertainty.

The final support-level conclusion is:

```text
tag support = dW support = raw support = trace[src] × phi[tgt] support
```

This means tag formation support is explained by 9C event-pair trace/phi support geometry.

The current h[u] trace is not the direct upstream cause of that support.

The strongest current public result is therefore:

```text
Tag formation support is trace[src] × phi[tgt] support geometry,
not direct h[u] history gating.
```

---

## 4. Routes closed by Phase 10

The following routes should not be continued without new evidence.

---

### 4.1 No direct novelty-factor tag rule

The global novelty idea:

```text
novelty_factor = 1 - h_norm
```

did not validate across seeds.

It showed weak preliminary signal, then failed 4-seed validation.

Seed 123 and seed 999 even showed inverse behavior.

Closed route:

```text
global novelty_factor → tag formation rule
```

---

### 4.2 No direct h-gate for capture

Current evidence does not support wiring h[u] directly into the tag rule or capture gate.

Closed route:

```text
current h[u] → direct capture gate
```

---

### 4.3 No 10E.2 mechanism design from current evidence

The Phase 10E branch explicitly blocked 10E.2 after 10E.1B / 10E.1C / 10E.1D / 10F.

Closed route:

```text
10E.1 weak positive → immediate mechanism design
```

The weak positive did not survive stricter validation.

---

### 4.4 No claim of digital life / consciousness / personhood

Phase 10 is mechanistic diagnostics.

It does not validate:

- digital life
- consciousness
- personhood
- subjective experience
- identity continuity

This boundary remains closed.

---

## 5. What remains open

Phase 10 did not end the Aniva route.

It narrowed the route.

The following questions remain open.

---

### 5.1 Can a different historical descriptor influence trace/phi geometry?

Current h[u] is not a direct upstream driver of 9C support.

But a different descriptor might still matter.

Possible future descriptors:

- event-gated history
- region-specific history
- subgraph-conditioned history
- trace-aligned history
- surprise-weighted history
- topology-aware history

The key difference:

```text
Do not ask whether history predicts tag after the fact.
Ask whether history shapes trace/phi formation before support appears.
```

---

### 5.2 Can world history shape trace formation?

10F moved the upstream target to:

```text
trace[src] × phi[tgt]
```

Future work may ask:

```text
Can prior world history shape trace[src] itself?
```

This is more promising than trying to force h[u] into tag formation downstream.

---

### 5.3 Can event response geometry become history-sensitive?

Another possible route:

```text
world history → event response geometry → phi[tgt] distribution → support geometry
```

This would treat phi not as a fixed response, but as something that may become shaped by previous structure and state.

---

### 5.4 Can closed-loop world events create long-range historical differences?

Phase 10 mostly stayed near controlled diagnostic setups.

A future route may need richer closed-loop world dynamics:

- recurring events
- agent-environment feedback
- resource gradients
- region-specific histories
- multi-event conflicts
- longer developmental windows

But this should come after a route decision, not as a blind expansion.

---

## 6. Recommended next route

The immediate next step should not be another small mechanism patch.

The recommended next step is:

```text
Phase 10 route synthesis → Phase 11 planning
```

Phase 11 should be planned from the evidence chain, not from excitement.

A good Phase 11 question would be:

```text
How can world history shape the formation of trace/phi support geometry itself?
```

Not:

```text
How do we force h[u] into the tag rule?
```

---

## 7. Candidate Phase 11 directions

### Option A — Trace-formation history route

Core question:

```text
Can historical context shape event-pair trace formation before dW support appears?
```

This route follows the true upstream path discovered by 10F.

Pros:

- directly connected to 10F evidence
- avoids downstream circularity
- mechanistically clean

Risk:

- may require deeper refactor of trace dynamics
- harder than adding a gate

---

### Option B — Event-response geometry route

Core question:

```text
Can world-shaped state alter phi[tgt] response geometry?
```

This treats event response as the history-sensitive surface.

Pros:

- may connect naturally to closed-loop environment
- can explain seed/event/subgraph asymmetry

Risk:

- may be hard to separate from topology effects

---

### Option C — Richer closed-loop world route

Core question:

```text
Can a simple world generate histories that reshape individuals over longer time scales?
```

This would move Aniva closer to the Digital Life Substrate vision.

Pros:

- closer to the long-term goal
- more meaningful than isolated event probes

Risk:

- too many variables
- high chance of interpretability collapse if done too early

---

### Option D — Phase 10 synthesis / paper-style report first

Core question:

```text
Can the current Phase 5–10 evidence chain be written as a coherent technical report?
```

Pros:

- strengthens public credibility
- clarifies what is actually proven
- helps future collaborators understand the route

Risk:

- does not advance experiments immediately

---

## 8. Recommended decision

The recommended next move is:

```text
Do Phase 10 synthesis first.
Then design Phase 11.
```

Reason:

Phase 10 generated many results and route closures.

Before adding mechanisms, the project needs a clean public-facing synthesis of:

- what was tested
- what passed
- what failed
- what was ruled out
- what remains open
- why Phase 11 should target trace/phi formation rather than h-gating

This is more valuable than rushing into another experiment.

---

## 9. Immediate action list

Recommended next documents:

1. `docs/phase10_route_synthesis.md`
2. `docs/phase11_candidate_routes.md`
3. `docs/phase11A_trace_formation_history_planning.md` only after route synthesis

Do not implement Phase 11 before those documents exist.

---

## 10. Final boundary

The public release is a milestone.

It is not a finish line.

The current strongest statement is:

```text
Aniva has a growing mechanistic evidence chain for history-dependent structural dynamics,
but it has not validated digital life, consciousness, or personhood.
```

The current strongest technical conclusion is:

```text
Tag formation support is trace[src] × phi[tgt] support geometry,
not direct h[u] history gating.
```

The next scientific question is:

```text
Can world history shape trace/phi support geometry itself?
```
