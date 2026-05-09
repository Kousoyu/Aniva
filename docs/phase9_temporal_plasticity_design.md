# Phase 9: Temporal Plasticity — Design Note

**Date:** 2026-05-05
**Status:** 设计阶段（未实现）

---

## 1. Motivation

Phase 8B proved that the current rate-based Hebbian plasticity cannot translate temporal event structure into directional weight change differences. Three independent event dimensions (label, duration, timing) were tested — all produce cos=1.0 between arms.

The root cause: `Δw ∝ pre_activation × post_activation` has zero temporal resolution. It collapses "who fired together, when, in what order, during what state" into a single scalar: "how much did they co-activate."

Phase 9 addresses this by adding temporal sensitivity to the plasticity rule.

---

## 2. What Phase 9 is NOT

- NOT adding spiking neurons
- NOT adding reward signals or reinforcement learning
- NOT adding goals, agents, choices, or emotions
- NOT adding LLM-based or cognitive modules
- NOT claiming consciousness or awareness

Phase 9 is strictly: **giving local plasticity rules the ability to encode temporal order and state-window information.**

---

## 3. Three candidate approaches

### 3A. Eligibility Trace (推荐 Phase 9A)

Add a short-term memory trace to each connection that captures the relative timing of pre- and post-synaptic activity.

**Mechanism:**

Each unit maintains two decaying traces:
- `trace_fast`: fast decay (τ ~ 20-50 steps), captures recent activity
- `trace_slow`: slow decay (τ ~ 200-500 steps), captures sustained activity

For each connection (pre → post), an eligibility signal is computed:

```
eligibility = trace_fast_pre(t) × activation_post(t)
            - activation_pre(t) × trace_fast_post(t)
```

When `eligibility > 0`: pre was active BEFORE post (causal order) → LTP-like
When `eligibility < 0`: post was active BEFORE pre (acausal order) → LTD-like

The plasticity update becomes:

```
Δw = η × [α × co_activation  +  β × eligibility]
```

Where α controls the rate-based component and β controls the timing-sensitive component.

**Why this fits Aniva:**

- Does not require discrete spikes — works with continuous activation
- Traces already exist in the system (`trace` field on units)
- Minimal architectural change: add eligibility to connection update
- Can be run as a parallel readout without replacing the main plasticity rule
- The `trace_fast` decay rate directly controls the temporal resolution

**Key parameters to sweep:**
- `τ_fast`: 20, 50, 100 steps
- `β / α` ratio: 0.1, 0.5, 1.0 (how much weight to give timing vs co-activation)
- Whether eligibility is symmetric (both pre→post and post→pre) or asymmetric

**Expected test:**
Re-run 8B.4's state-triggered timing experiment with eligibility trace enabled. If eligibility works:
- closed_loop_triggered should show different delta vector direction from matched_time_shuffle
- cos(cl, ms) should drop below 1.0
- |cl-ms|_L1 should increase beyond the 2-5e-05 baseline

### 3B. Continuous STDP-like Rule

Instead of separate traces, directly use activation derivatives to detect "threshold crossing" events and apply asymmetric weight updates.

**Mechanism:**

Define a "crossing event" as activation crossing a threshold (e.g., 0.5) with positive derivative:

```
pre_event(t) = activation_pre(t) > θ  AND  activation_pre(t-1) ≤ θ
post_event(t) = activation_post(t) > θ  AND  activation_post(t-1) ≤ θ
```

Within a temporal window (e.g., ±50 steps):
- pre_event before post_event → potentiate
- post_event before pre_event → depress
- Magnitude decays with |Δt|

```
Δw = Σ A⁺ × exp(-|Δt|/τ⁺)  for pre-before-post
   - Σ A⁻ × exp(-|Δt|/τ⁻)  for post-before-pre
```

**Advantages:**
- Closer to biological STDP
- Naturally handles sparse events
- Asymmetric by construction

**Disadvantages:**
- Requires threshold crossing detection (adds state)
- Harder to tune (A⁺, A⁻, τ⁺, τ⁻, θ, window)
- May produce instability with continuous activation (frequent crossings)
- Less natural for non-spiking units

**When to consider:** If eligibility trace (3A) shows partial separation but not enough, a sharper timing rule may be needed.

### 3C. State-Gated Plasticity Modulation

Instead of changing the weight update DIRECTION, change WHEN plasticity is active.

**Mechanism:**

A global or local "plasticity gate" opens/closes based on state variables:

```
plasticity_gate = f(lr_imbalance, energy_stress, activation_entropy)
```

When gate is open: plasticity rate is higher, or homeostatic pressure is lower.
When gate is closed: normal dynamics.

This doesn't change the direction of weight updates, but changes their MAGNITUDE based on when events occur relative to the state window.

**Advantages:**
- Very simple, minimal code change
- Directly builds on Phase 8B's state signals

**Disadvantages:**
- Does NOT solve the directional invariance problem
- Same spatial co-activation pattern → same direction, just different magnitude
- Would likely produce cos=1.0 again (just different |L1|)
- Risk of becoming a hand-coded "important moment" detector

**When to consider:** As a supplementary mechanism to 3A or 3B, not as the primary approach. A gating mechanism on top of eligibility traces could create "state-window-gated eligibility" — which is closer to the Alicization "event at critical state window" concept.

---

## 4. Recommended path: 3A → 3B (if needed) → 3C (supplementary)

```
Phase 9A: Eligibility trace
  - Add trace_fast / trace_slow to units
  - Add eligibility term to plasticity update
  - Sweep τ_fast and β/α ratio
  - Re-run 8B.4 state-triggered timing test
  - Success: cos(cl, ms) < 1.0

Phase 9B: STDP-like refinement (if 9A insufficient)
  - Replace eligibility traces with threshold-crossing detection
  - Sharper temporal resolution
  - More parameter tuning

Phase 9C: State-gated modulation (supplementary)
  - Layer plasticity gate on top of 9A/9B
  - Specific state windows → enhanced plasticity
  - Only if 9A/9B already produce directional divergence
```

---

## 5. Phase 9A detailed design

### 5.1 New fields

Each unit gets:
```python
trace_fast: float  # fast decay, τ ~ 20-50
trace_slow: float  # slow decay, τ ~ 200-500 (optional for 9A)
```

Each connection optionally gets:
```python
eligibility: float  # accumulated timing signal
```

### 5.2 Trace update (per step, per unit)

```python
trace_fast = (1 - 1/τ_fast) * trace_fast + activation
trace_slow = (1 - 1/τ_slow) * trace_slow + activation  # optional
```

### 5.3 Eligibility computation (per connection, per step)

```python
eligibility_raw = trace_fast_pre * activation_post - activation_pre * trace_fast_post
eligibility = ema(eligibility_raw, τ_eligibility)
```

The eligibility accumulates the causal-asymmetric signal. EMA smooths it to avoid step-by-step noise.

### 5.4 Plasticity update (modified from current)

Current:
```python
Δw = η * (pre_act * post_act - homeostatic_pressure)
```

With eligibility:
```python
hebbian = pre_act * post_act
timing  = β * eligibility  # signed: positive for pre-before-post
Δw = η * (α * hebbian + timing - homeostatic_pressure)
```

Where:
- `α = 1.0` (keep current rate-based component)
- `β = [0.1, 0.5, 1.0]` (timing sensitivity sweep)
- `η = current learning rate`

### 5.5 Experiment: Phase 9A smoke test

Re-use 8B.4's experiment structure exactly:
- 4 arms: open_loop_poisson, closed_loop_triggered, matched_time_shuffle, circular_shift
- 20k steps, seeds 42 + 999
- Same trigger parameters

**New CLI parameter:** `--eligibility-beta` (default 0.5)

**Comparison:** Run WITH and WITHOUT eligibility, compare:
- cos(cl, ms) — does it drop?
- |cl-ms|_L1 — does it increase beyond 5e-05?
- Regional readout — do subgraph patterns separate?

### 5.6 Parameter sweep (if 20k smoke shows signal)

| Parameter | Range | Notes |
|-----------|-------|-------|
| τ_fast | 20, 50, 100 | Temporal resolution of trace |
| β | 0.1, 0.5, 1.0, 2.0 | Timing vs co-activation weight |
| τ_eligibility | 50, 100, 200 | Smoothing of eligibility signal |

### 5.7 Success criteria

| Level | Criteria |
|-------|----------|
| Low | cos(cl, ms) < 0.9999 (first drop from 1.0 in all Phase 8) |
| Medium | cos(cl, ms) < 0.99 |
| Strong | Regional readout shows subgraph-level divergence (e.g., cross_region_l1 differs between arms) |
| Gold | State-triggered events produce systematically different weight patterns from time-shuffled events |

---

## 6. Design principles

### 6.1 Don't break what works

The current rate-based Hebbian + homeostasis produces stable, non-dead dynamics. The eligibility term should be ADDITIVE, not a replacement. Start with β small (0.1) and observe.

### 6.2 Keep it local

Eligibility is computed per-connection from local information only (pre activation, post activation, pre trace, post trace). No global state needed.

### 6.3 No hand-coded "important moments"

The eligibility trace is a passive physical mechanism, not a detector. It doesn't "know" what's important. It simply records temporal order. Whether that order matters for structure is an emergent property.

### 6.4 Observable, not assumed

The experiment design (same as 8B.4) allows direct comparison of with-eligibility vs without-eligibility. We don't assume eligibility helps — we test it.

---

## 7. Relation to Phase 7 and Phase 8

```
Phase 7.5: Topology sets the sweet spot for structural divergence
Phase 8A:  Spatial activation pattern change → divergence possible
Phase 8B:  Temporal modulation without spatial change → NO divergence
Phase 9:   Can temporal plasticity rules translate temporal modulation
           into spatial (directional) divergence?
```

Phase 9 is the bridge between "temporal structure exists in the environment" (proven in 8B) and "temporal structure creates structural change" (hypothesis to test).

---

## 8. Open questions

1. **Will eligibility traces break the stable dynamics?** The rate-based rule + homeostasis has been carefully calibrated. Adding a signed eligibility term could destabilize if β is too large.

2. **Is τ_fast=20-100 the right timescale?** The event interval in Config A is 200 steps. If τ_fast is too short, the trace decays before the next relevant event. If too long, it loses temporal specificity.

3. **Does eligibility need to be connection-specific?** Or can it be unit-level (pre_trace, post_trace) with the connection just reading the two unit traces?

4. **What happens to L1 distance distribution?** Phase 8B established the 2-5e-05 baseline for |arm_a - arm_b|_L1. A working eligibility mechanism should push this above the baseline.

5. **Does this interact with homeostasis?** Homeostasis pulls weights toward a target. If eligibility creates systematic asymmetry, homeostasis may counteract it. This interaction needs observation.

---

## 9. What NOT to add (yet)

These are legitimate plasticity mechanisms, but they introduce complexity that would obscure the temporal sensitivity question:

- **Metaplasticity** (plasticity of plasticity rate): interesting but premature
- **Synaptic scaling**: already have homeostasis, adding scaling would conflate
- **Structural plasticity** (new connection formation): Phase 10+
- **Neuromodulatory diffusion**: requires spatial field infrastructure
- **Multi-timescale consolidation**: requires sleep/wake cycles or separate phases
- **Tag-and-capture**: requires protein synthesis analogue, too complex for now

Phase 9 should answer ONE question: can temporal plasticity rules break the spatial co-activation lock? Everything else is Phase 10+.
