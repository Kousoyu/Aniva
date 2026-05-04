# Phase 8B: Closed-Loop Environmental Coupling — Final Summary

**Date:** 2026-05-05
**Status:** 完成（Phase 8B 收束）

---

## 1. What Phase 8B set out to do

Phase 8A found that anomaly-style perturbations (position swaps, duration changes) during events could create seed-specific structural directionality. The question was: can this be turned into a closed-loop mechanism where internal state drives event modulation, creating a coupled environment-plasticity system?

Phase 8B was the systematic investigation of closed-loop coupling from the environment scheduler side.

---

## 2. Experiment lineage

| Phase | What | Steps | Seeds | Key question |
|-------|------|-------|-------|-------------|
| 8B (pilot) | Minimal closed-loop: lr_imbalance → L/R override | 20k | 42, 999 | Does state feedback exist? |
| 8B (full) | Same, 120k 4-seed cloud run | 120k | 42, 77, 888, 999 | Does effect accumulate? |
| 8B.1 | Coupling calibration: 4 configs (A/B/C/D) | 20k | 42, 999 | Density/duration: strengthen or dilute? |
| 8B.1A | Config A only 120k cloud run + matched_shuffle | 120k | 4 seeds | Does matched_shuffle control separate? |
| 8B.1B | Structural readout audit | 20k | 42, 999 | Is global wL1 masking subgraph signals? |
| 8B.2 | Gain bandwidth sweep (2.5/5.0/8.0) | 20k | 42, 999 | Does stronger coupling break cos=1.0? |
| 8B.3 | Duration coupling (label → duration) | 20k | 42, 999 | Does coupling target matter? |
| 8B.4 | State-triggered timing (remove fixed clock) | 20k | 42, 999 | Does timing itself break cos=1.0? |

---

## 3. Core result: cos=1.0 across all experiments

Every single arm pair in every single experiment produces delta vector cosine = 1.000000.

```
experiment   coupling target        event count   cos(cl,ms)   |cl-ms|_L1
---------------------------------------------------------------------------
8B.2 g=2.5   L/R label bias         99 (same)     1.000000     3.0-4.7e-05
8B.2 g=5.0   L/R label bias         99 (same)     1.000000     3.0-3.8e-05
8B.2 g=8.0   L/R label bias         99 (same)     1.000000     3.4-4.4e-05
8B.3 g=300   event duration         99 (same)     1.000000     3.2e-05
8B.4         event timing           6-113 (diff)  1.000000     2.3-4.7e-05
```

The |arm_a - arm_b|_L1 distance consistently falls in 2-5e-05 regardless of coupling target, strength, or event count. This is the characteristic perturbation scale from different environmental schedules — and it does NOT grow with stronger or different coupling.

---

## 4. The narrowing of hypotheses

### 8B → 8B.1: "Not enough force" → "Wrong lever"

The initial 8B pilot showed event-level overrides but no structural divergence. 8B.1 tested whether denser events (more coupling opportunities) would help — they didn't. Config A (sparse, no overlap) actually preserved state-timing specificity better.

### 8B.1 → 8B.2: "Wrong lever" → "Lever has a ceiling"

8B.2 swept gain from 2.5 to 8.0. Higher gain did NOT increase structural divergence — it DECREASED it (ΔwL1: 5.25e-6 → 1.55e-6). Sign flips disappeared at gain=8.0. The L/R label pathway is exhausted.

### 8B.2 → 8B.3: "Label doesn't work" → "Duration doesn't work either"

8B.3 switched coupling target from label to duration. With gain=300, closed_loop produced dur(L)=40 vs dur(R)=120 (3x asymmetry). Strong mechanical modulation, zero structural divergence. Event-property coupling as a category is exhausted.

### 8B.3 → 8B.4: "Timing is the lock" → "Wait, timing doesn't break it either"

8B.4 removed the fixed clock entirely: state-triggered events, poisson random events, circular-shifted events. Three completely different temporal schedules. Event counts ranged from 6 to 113. **All 12 arm pairs: cos=1.0.**

The "timing lock" hypothesis was wrong. The lock is not temporal — it's **spatial**.

---

## 5. The spatial lock model

The current rate-based Hebbian plasticity rule updates connection weights based on pre-post co-activation. Every stimulus event (L or R) activates the SAME spatial region:
- L stimulus at (-0.5, 0, 0) → activates left-region units
- R stimulus at (0.5, 0, 0) → activates right-region units

Whether events come every 200 steps, at random intervals, or triggered by state:
- The SAME set of units gets activated
- The SAME connections see co-activation
- The SAME weight change pattern emerges

**The delta vector direction is determined by the spatial co-activation footprint, which is invariant to event scheduling.**

Three independent event dimensions were tested:

| Dimension | Property modulated | Mechanical effect | Structural effect |
|-----------|-------------------|-------------------|-------------------|
| Label | Which side at each event time | L/R counts shift (±5 events) | cos=1.0 |
| Duration | How long each event lasts | 40 vs 120 (3x) | cos=1.0 |
| Timing | When events occur | 6 vs 113 events, 3 schedules | cos=1.0 |

All three produce ZERO plasticity direction divergence. This is not a parameter problem — it's a mechanism problem.

---

## 6. What Phase 8B proved (and disproved)

### Proved

1. **Closed-loop event modulation works mechanically.** The scheduler can read state, compute bias, and modify events. lr_imbalance is a usable state signal.

2. **Matched_shuffle is a valid control.** It preserves event counts and labels while destroying state-timing correlation. It properly isolates the coupling mechanism.

3. **Structural readout is sensitive.** Regional decomposition + delta vector comparison correctly detects zero effect. It doesn't produce false positives — cos=1.0 when there's genuinely no divergence, and the L1 distance stays in a narrow band.

4. **The environmental coupling pathway has a clear boundary.** The experiment scheduler can modulate events, but the plasticity system cannot translate temporal event structure into directional weight change differences.

### Disproved

1. ~~"Timing is the dominant plasticity driver."~~ The spatial co-activation pattern is the dominant driver.
2. ~~"Stronger coupling will eventually break through."~~ Higher gain DECREASES structural effect, not increases it.
3. ~~"Different coupling targets might work."~~ Three independent targets (label, duration, timing) all produce identical results.

---

## 7. The bottleneck: rate-based Hebbian plasticity

The current plasticity rule:

```
Δw ∝ pre_activation × post_activation
```

This has no temporal resolution. It only asks: "did pre and post fire together?" It does not ask: "in what order? at what relative timing? during what state window?"

This means:
- Two events 1000 steps apart → same weight update as two events 10 steps apart
- L-before-R → same as R-before-L (assuming equal activation)
- Event during high-energy state → same as event during low-energy state
- State-triggered events → same spatial footprint as random events

The scheduler can create rich temporal structure, but the plasticity rule collapses it all into a single "how much co-activation" scalar.

---

## 8. Cross-phase connection: Phase 7.5 → 8A → 8B

```
Phase 7.5: Topology determines "sweet spot" for structural divergence
Phase 8A:  Anomaly events (position swap, duration change) CAN create
          seed-specific directionality — but only when they change
          SPATIAL activation patterns (position swap)
Phase 8B:  Closed-loop coupling of event properties (label, duration,
          timing) WITHOUT spatial change → NO directionality
```

The unifying principle: **spatial activation pattern change is necessary and sufficient for plasticity direction divergence.** Phase 8A's position-swap anomaly changed which units got activated. Phase 8B's label/duration/timing modulation changed when/how long the same units got activated — and that's not enough.

---

## 9. Conclusion

> **Closed-loop scheduler works at the event-distribution level, but event label, duration, and state-triggered timing all fail to steer the structural plasticity trajectory under the current rate-based Hebbian rule. The bottleneck has moved from environment scheduling to temporal plasticity.**

Phase 8B completes the environmental coupling investigation. The scheduler layer is functional and well-characterized. The limiting factor is the plasticity rule's inability to encode temporal relationships.

The next logical step is Phase 9: giving plasticity temporal resolution — through eligibility traces, STDP-like rules, or state-gated plasticity modulation — so that the temporal structure the scheduler creates can actually register in the weight dynamics.
