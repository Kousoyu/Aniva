# Phase 10 — Route Synthesis

**Date:** 2026-05-24  
**Status:** synthesis  
**Scope:** Phase 10 closed-loop event history, historical context, and tag-support diagnostics  
**Public baseline:** `v0.0.1-public`

---

## 1. Positioning

This document synthesizes Phase 10.

It is not:

- a new experiment design
- a mechanism proposal
- a Phase 11 implementation plan
- a claim of consciousness
- a claim of personhood
- a claim that digital life has been achieved

It is a map.

Phase 10 generated many branches, controls, negative results, and route closures.  
The goal of this document is to make the evidence chain readable as one coherent route.

---

## 2. The original Phase 10 question

Phase 9D established that ordered event history can sediment into slow structural change through the tag / capture / slow-weight pipeline.

Phase 10 asked the next question:

```text
Can world-generated or closed-loop event history shape a digital individual,
rather than merely executing designer-specified event schedules?
```

More concretely:

```text
Can state → event → plasticity → structure become a closed route,
where the system's own state influences the history it receives,
and that history later changes the system?
```

Phase 10 did not fully answer this long-term question.

But it narrowed the path sharply.

---

## 3. Phase 10 route overview

The route can be summarized as:

```text
10A: closed-loop event scheduler and replay controls
10C: state-context-sensitive capture diagnostics
10D: historical context trace h[u]
10E: does h[u] predict tag formation?
10F: what actually determines tag support?
```

The final answer of this branch is:

```text
Tag formation support is trace[src] × phi[tgt] support geometry,
not direct h[u] history gating.
```

This is not the end of Aniva.

It is the end of one diagnostic route.

---

## 4. Phase 10A — closed-loop event history plumbing

### 4.1 Goal

Phase 10A tested whether Aniva could move from fixed event schedules toward state-dependent event generation.

The target was not intelligence.

The target was plumbing:

```text
state → scheduler → event history
```

The scheduler was required to be non-cheating:

- it should not read arm labels
- it should not directly write structure
- it should only influence the system through generated events

---

### 4.2 10A.1 — scheduler plumbing smoke

The first scheduler smoke showed that the scheduler could produce event histories.

However, the initial decision interval produced a caveat: one seed was too event-heavy under the soft criterion.

This was not treated as a bug.

It was treated as calibration information.

---

### 4.3 10A.1B — scheduler calibration

10A.1B reduced the decision interval.

This improved sampling resolution and produced a clean pass.

The important lesson:

```text
scheduler diagnostics are sensitive to decision-point granularity.
```

The scheduler was usable as Phase 10 plumbing.

---

### 4.4 10A.2 — fast plasticity with matched replay

10A.2 opened fast event-pair plasticity.

It compared:

- closed loop
- matched open-loop replay
- random control
- no-event control

The key discovery was a control-design lesson:

```text
same seed + same initial state + same event log = deterministic mirror
```

Matched replay under identical state did not create a meaningful feedback-context contrast.

This was a clean negative.

Not because the system failed.

Because the mirror was too perfect.

---

### 4.5 10A.2B / 10A.2C — trying to create real replay contrast

The route then tested ways to make replay non-identical:

- initial activation perturbation
- divergent warmup replay
- exact replay as sanity mirror
- matched warmup control

These produced weak or negative results.

The system could store small differences in some traces, but those differences did not become robust structure under the tested route.

---

### 4.6 10A.3 — slow consolidation

10A.3 opened both:

```text
9C fast event-pair plasticity
9D slow consolidation
```

The question was:

```text
Can 9D amplify a small state-context crack into slow structure?
```

The result was clean negative.

The crack did not become a structural canyon.

Closed route:

```text
small state-context perturbation → fast crack → slow structural amplification
```

under the tested configuration.

---

## 5. Phase 10C — capture gate diagnostics

### 5.1 Why 10C existed

After 10A.3, the obvious suspicion was:

```text
Maybe the capture gate cannot see state context.
```

So 10C inspected the capture mechanism.

The capture gate used highly compressed signals such as global energy / trace mass.

This raised a concern:

```text
local state-context differences may disappear when compressed into scalar gate signals.
```

---

### 5.2 10C.1 / 10C.2 — instrumentation and diagnostics

10C added read-only diagnostics.

It did not change the gate.

The goal was to ask whether context-sensitive quantities were visible at capture time.

The result was again negative.

Most diagnostics showed little or no difference between closed and replay arms.

The interpretation:

```text
current capture diagnostics cannot see the warmup history difference.
```

This did not prove history is irrelevant.

It showed that current capture observables were not the correct route.

---

## 6. Phase 10D — historical context trace h[u]

### 6.1 Why h[u] was introduced

10C showed that event-local traces were too short or too overwritten to preserve warmup context.

So Phase 10D introduced a slow per-unit historical context trace:

```text
h[u]
```

Its purpose was simple:

```text
store longer-timescale activation history
```

---

### 6.2 10D.1 / 10D.2 — h[u] plumbing

The h trace worked.

It stored warmup history.

It survived into later windows.

It did not disturb the existing mechanisms when used as read-only instrumentation.

This was a positive plumbing result:

```text
h[u] can carry historical context.
```

---

### 6.3 10D.3 / 10D.4 — h alignment diagnostics

The next question was:

```text
Does h[u] align with where slow structural change is deposited?
```

Early candidate diagnostics suggested possible novelty-like relationships.

But later audits showed circularity.

Signals that appeared to predict slow delta often depended on tag itself.

The route had to move upstream.

Important closure:

```text
slow_delta is downstream of tag_cache.
```

So using slow_delta as the target for historical-context candidate diagnostics is dangerous.

---

## 7. Phase 10E — tag formation historical-context diagnostics

### 7.1 The new target

10E changed the question.

Instead of asking whether h[u] predicts slow deposition, it asked:

```text
Does h[u] predict where tags form?
```

This was more upstream than slow weights.

The candidate idea was:

```text
low historical activity → higher novelty → more likely to be tagged
```

---

### 7.2 10E.1 — weak positive preliminary

The first 2-seed diagnostic produced a weak positive.

Novelty factor appeared mildly predictive.

But the effect was small.

It was not mechanism-ready.

Correct interpretation:

```text
promising weak preliminary, not proof.
```

---

### 7.3 10E.1B — four-seed validation

The 4-seed validation failed.

Results split:

```text
seed42/77: weak or borderline pass
seed123/999: severe inverse
```

R-events also showed unstable / null behavior in multiple seeds.

This closed the global novelty route.

Closed route:

```text
global novelty_factor → universal tag formation predictor
```

---

### 7.4 10E.1C — event-type and topology diagnostic

10E.1C showed that the failure was not simply global.

The split was local:

- event-type dependent
- subgraph dependent
- seed-topology dependent

The verdict:

```text
null_for_current_h_descriptor
```

Meaning:

```text
current global h[u] / novelty_factor is insufficient as a descriptor.
```

Not:

```text
history is impossible.
```

---

### 7.5 10E.1D — subgraph / phi diagnostic

10E.1D tested whether phi / surprise / subgraph structure explained tag formation better.

The strongest predictor was `abs_dW`.

But that was immediately recognized as tautological:

```text
tag_cache += abs(dW)
tag_presence == 1 iff abs(dW) > 0
```

So the question moved one step upstream again.

New target:

```text
What determines event-pair dW support?
```

---

## 8. Phase 10F — event-pair support geometry

### 8.1 Why 10F existed

10F existed because 10E showed:

```text
tag_presence is downstream of abs(dW)
```

So the true upstream target was not tag.

It was:

```text
dW support
```

---

### 8.2 10F Step 1 — proxy phi audit

Step 1 used existing 10E.1B event-level CSV.

It confirmed:

```text
tag_support == dW_support
```

But it also showed that recorded `phi_conn` was only a dense proxy.

It could not explain sparse dW support.

Result:

```text
proxy_phi_support_insufficient
```

This forced true instrumentation.

---

### 8.3 10F Step 2 — true trace / phi capture

Step 2 captured the actual quantities:

```text
trace[src]
phi[tgt]
raw = trace[src] × phi[tgt]
dW
tag_delta
```

The identity checks all passed:

```text
raw_support == trace_src_positive AND phi_tgt_positive
raw_support == dW_support
dW_support == tag_support
```

Therefore:

```text
tag_support = dW_support = raw_support = trace[src] × phi[tgt] support
```

This closed the support identity question.

---

### 8.4 10F Step 3 — support subgraph decomposition

Step 3 asked where trace and phi meet.

The final verdict:

```text
trace_phi_support_geometry_explains_tag_formation__h_not_upstream
```

Key conclusions:

- LL is a topology/support special case.
- RR seed split is primarily phi-limited.
- R-event collapse is seed-dependent trace×phi intersection geometry.
- Current h[u] is not a direct upstream driver of 9C support.

This closed the Phase 10E/10F diagnostic branch.

---

## 9. What Phase 10 proved

Phase 10 proved or strongly established the following.

---

### 9.1 Closed-loop event generation is viable plumbing

A state-dependent scheduler can generate event histories without directly writing structure.

This is necessary for future world-coupled experiments.

---

### 9.2 Exact replay must be treated as a mirror, not a contrast

If seed, initial state, and event log are identical, replay is deterministic mirror behavior.

Future controls must create real context contrast.

---

### 9.3 h[u] can store historical context

The h trace can carry warmup history.

This is a useful tool.

But storage alone is not causal influence.

---

### 9.4 Current h[u] is not upstream of 9C support

The h trace does not directly determine event-pair support.

It should not be wired into tag rule or capture gate based on current evidence.

---

### 9.5 Tag support is trace×phi geometry

The strongest technical conclusion:

```text
tag support is trace[src] × phi[tgt] support geometry
```

This is Phase 10's cleanest mechanistic result.

---

## 10. What Phase 10 ruled out

The following routes are closed unless new evidence appears.

---

### 10.1 Direct novelty-factor tag rule

Closed:

```text
global novelty_factor = 1 - h_norm → tag formation
```

Reason:

- weak preliminary signal
- failed 4-seed validation
- seed123/999 inverse
- event-type instability

---

### 10.2 Direct h-gate

Closed:

```text
current h[u] → direct tag or capture gate
```

Reason:

h[u] is not upstream of trace/phi support.

---

### 10.3 Immediate 10E.2 mechanism design

Closed:

```text
10E weak positive → mechanism design
```

Reason:

the weak positive did not validate.

---

### 10.4 Treating slow_delta as target for h candidates

Closed:

```text
h candidate → slow_delta
```

Reason:

slow_delta is downstream of tag_cache and can create circular interpretations.

---

### 10.5 Treating tag_presence as independent target after dW is available

Closed:

```text
abs_dW → tag_presence predictor
```

Reason:

tag_presence is defined by abs(dW).

---

## 11. What Phase 10 did not prove

Phase 10 did not prove:

- digital life
- consciousness
- personhood
- subjective experience
- identity continuity
- selfhood
- agency in the strong sense
- world-grown individuals

Phase 10 is mechanistic groundwork.

The public boundary remains:

```text
No consciousness claim.
No personhood claim.
No claim that digital life has been achieved.
```

---

## 12. Scientific interpretation

Phase 10 shows that Aniva is not yet at the level of world-grown digital individuals.

But it has moved from vague aspiration to mechanistic constraint.

The most important conceptual shift is:

```text
Do not ask whether history predicts downstream structure after the fact.
Ask whether history shapes the formation of upstream support geometry.
```

The route moved upstream step by step:

```text
slow_delta
  ← tag_cache
  ← abs(dW)
  ← trace[src] × phi[tgt]
```

This is valuable.

It prevents the project from mistaking downstream shadows for causes.

---

## 13. Recommended next step

Do not implement Phase 11 yet.

The recommended sequence is:

```text
Phase 10 route synthesis
→ Phase 11 candidate routes
→ Phase 11A planning
→ implementation only after design freeze
```

This document is the first step.

The next document should be:

```text
docs/phase11_candidate_routes.md
```

---

## 14. Phase 11 seed question

The best current Phase 11 seed question is:

```text
Can world history shape trace/phi support geometry itself?
```

Not:

```text
Can we force h[u] into tag formation?
```

A good Phase 11 should target the upstream support-forming process.

---

## 15. Candidate Phase 11 route families

### 15.1 Trace-formation history route

Question:

```text
Can prior history shape trace[src] formation before event-pair support appears?
```

Why it follows Phase 10:

10F showed that trace is one half of the support product.

If history can shape trace, then history may shape future tag support without artificial gates.

---

### 15.2 Event-response geometry route

Question:

```text
Can prior world history shape phi[tgt] response geometry?
```

Why it follows Phase 10:

10F showed that phi is the other half of the support product.

If phi geometry becomes history-sensitive, support geometry can become history-sensitive.

---

### 15.3 Topology-conditioned history route

Question:

```text
Can history act differently across LL / RR / LR / RL subgraphs?
```

Why it follows Phase 10:

10F showed that support geometry is subgraph-dependent.

A global descriptor is too blunt.

---

### 15.4 Richer closed-loop world route

Question:

```text
Can a simple world generate histories that reshape trace/phi geometry over longer developmental windows?
```

Why it follows Phase 10:

The long-term Digital Life Substrate goal needs world-generated history.

Risk:

This route can become too complex too quickly.

It should not be first unless diagnostics are strong enough.

---

## 16. Recommended Phase 11 direction

The recommended Phase 11 direction is:

```text
Trace/phi formation history
```

Specifically:

```text
Phase 11A — Trace Formation Under Historical Context
```

This route is closest to the 10F evidence.

It asks whether history can affect the support-forming process before dW and tag exist.

It avoids downstream circularity.

---

## 17. Immediate action list

Recommended next files:

1. `docs/phase11_candidate_routes.md`
2. `docs/phase11A_trace_formation_history_planning.md`
3. `docs/phase11A0_design_freeze.md`

Do not write implementation before these exist.

---

## 18. Final synthesis

Phase 10 did not find a shortcut from h[u] to structural memory.

It found the next doorway.

The doorway is:

```text
trace[src] × phi[tgt]
```

If Aniva is to become a system whose individuals are shaped by world history, the next route should ask how world history changes the geometry of trace and phi formation.

That is the road Phase 10 leaves behind.
