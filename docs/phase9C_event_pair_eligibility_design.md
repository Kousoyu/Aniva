# Phase 9C — Event-Pair Eligibility Trace (Design)

> Phase 9C shifts from detecting activity events to binding event relationships.

## 1. Evidence Chain (9A → 9B.2)

### Phase 9A — EMA-based eligibility (sealed)

| Sub-phase | Result |
|-----------|--------|
| 9A smoke | Temporal signal exists (4-5x L1 amplification vs OFF) |
| 9A.1 | Effect is systematic across 4 seeds (3.3-5.9x) |
| 9A.2 | Amplification is global plasticity shift, not state-timed feedback specificity |
| 9A.3 | Activity-EMA cannot distinguish L→R from R→L order |
| 9A.4 | Onset-EMA produces zero signal (back to OFF baseline) |

**Conclusion:** EMA is the wrong tool. Activity-EMA is too broad (amplifies spatial bias, not temporal order). Onset-EMA is too weak (signal collapses to OFF baseline).

### Phase 9B.1 — Threshold-crossing (sealed, clean negative)

- Crossing detection mechanically sound: 13-18 crossings/unit, 18-23% steps
- But `|asym_diff|` stays at OFF baseline (1e-6 to 5e-6) across 4 seeds
- Root cause: time-scale mismatch — mean inter-crossing interval (~1100-1500 steps) vs 80-step paired-pulse gap

### Phase 9B.2 — Time-scale matching (sealed, negative pilot trend)

- 2-seed pilot, gaps 80/500/1000/1500, num_pairs=5
- `xing/unit` grew 3x (2.7→7.8 seed42, 3.1→8.9 seed999)
- `|asym_diff|` stayed flat at OFF baseline at ALL gap values
- Time-scale matching did NOT rescue threshold-crossing eligibility

### Why threshold-crossing time-scale matching didn't work

The crossing mechanism knows THAT a unit underwent a state change, but does not know WHICH event preceded it. It detects footsteps but cannot tell who entered the room first.

The core missing piece: **event-relationship binding.**

## 2. Core Hypothesis

Order-specific structural plasticity requires the system to retain a transient trace of "what just happened," so that when the next event arrives, the prior-event × current-event relationship can be deposited into structure.

This is NOT about:
- How active a unit is
- How wide the eligibility window is
- How many crossings per unit

This IS about:
- Whether the system can bind L-before-R vs R-before-L into directionally distinct eligibility signals.

## 3. Mechanism Sketch

### 3.1 Event-pair trace

```
For each event source X (L, R):
    When X fires at time t:
        X_trace[t] ← 1.0           # full activation
    X_trace decays continuously:
        d(X_trace)/dt = -X_trace / τ_trace      # τ_trace ≈ paired-pulse gap range
```

### 3.2 Eligibility gate

When event Y fires at time t':

```
eligibility_{X→Y} = X_trace[t'] · Y_current[t']
```

- If X_trace is still warm when Y fires → eligibility is non-zero
- If trace has decayed to near-zero → eligibility is ~zero
- The product is order-specific: `L_trace · R_current` ≠ `R_trace · L_current`

### 3.3 Plasticity routing

```
When L fires first, then R fires within trace window:
    ΔW_{L→R} ← β · eligibility_{L→R}   # strengthen L→R direction

When R fires first, then L fires within trace window:
    ΔW_{R→L} ← β · eligibility_{R→L}   # strengthen R→L direction
```

The plasticity update is applied at the moment the SECOND event fires — the binding happens at the pair, not at each individual event.

### 3.4 Trace decay as the single tuning knob

τ_trace is the only critical parameter for 9C.1. It defines the temporal binding window:

- Too short: trace decays before paired event arrives → no binding
- Too long: trace persists across unrelated events → noise, not order
- Just right: trace overlaps with the paired-pulse gap → order-specific binding

9C inherits 9B.2's clean paired-pulse scheduling (dynamic pair_interval, verified 16/16 OK),
but the first smoke uses τ_trace as the single knob — NOT gap. Gap is fixed in 9C.1
(e.g., gap=500). A gap × τ_trace interaction pilot is deferred to 9C.2 and only runs
if 9C.1 shows a directional trend.

## 4. Boundary: Not Hard-Coded Order

### 4.1 Forbidden: label-based order rules

```
# NEVER:
if order == L_then_R:
    increase W_{L→R}

# NEVER:
if current_event == "R" and prior_event == "L":
    update L_to_R_direction
```

These are writing the answer into the code. The system must not be told which event came first
by string label or enumerated order constant.

### 4.2 Forbidden: last_event string field

```
# NEVER:
memory["last_event"] = "L"   # string label — cheating
```

The trace must be a **spatial / region activation vector**, not a string field.
The system does not store "L happened." It stores: a decaying activation pattern
over the region that was perturbed by the last world event.

### 4.3 Allowed: spatial trace × current event

```
prior_event_trace ← spatial activation pattern that decays continuously
current_event_gate ← spatial pattern of the currently arriving event
eligibility = prior_trace · current_gate   # dot product of spatial patterns
```

The mechanism does not know "L_then_R is the answer." It only knows that some
region was perturbed recently, another region is being perturbed now, and the
temporal adjacency gives the pair a plasticity gate.

### 4.4 Event trace is not long-term memory

The event-pair trace is a **short-lived eligibility window** — it exists only to gate
plasticity at the moment of the second event. It is NOT:

- A memory field (`last_event_type`, `event_history`)
- A narrative tag (`"L arrived before R"`)
- A persistent record

Long-term memory in Aniva must still be deposited as structural change (connection
weights, topology shifts), not as stored strings or lookup tables. The trace decays;
the structure persists.

### 4.5 The world decides the order, not the code

If the world consistently presents L-then-R, structure naturally tilts L→R.
If the world presents R-then-L, structure tilts R→L.
If the world presents simultaneous events, both traces fire together and no
asymmetric bias emerges.

The order signal is an emergent consequence of world-event timing interacting
with decaying spatial traces — not a programmer-injected preference.

## 5. Comparison with Previous Mechanisms

| Mechanism | What it tracks | Why it failed |
|-----------|---------------|---------------|
| Activity EMA | Mean activity level | Too broad — amplifies spatial bias |
| Onset EMA | Event onset magnitude | Too weak — signal collapses |
| Threshold crossing | Unit state transitions | No event-relationship binding |
| **Event-pair trace** | **Prior event × current event** | **To be tested** |

## 6. Experiment Design

### 6.1 9C.1 — Fixed-gap, τ_trace sweep (single knob)

```
Gap: fixed at 500 (representative mid-range value)
τ_trace ∈ {80, 200, 500, 1000, 1500}
```

Only ONE knob: τ_trace. Gap is NOT swept in 9C.1.

This avoids the interaction ambiguity that would arise from co-varying gap and τ_trace
simultaneously. The question is clean: can a decaying prior-event trace, whose window
width is controlled by τ_trace, produce order-specific eligibility?

### 6.2 9C.2 — gap × τ_trace interaction pilot (deferred)

Only if 9C.1 shows a directional trend:

```
gap ∈ {80, 500, 1000, 1500}
τ_trace ∈ {80, 200, 500, 1000, 1500}
```

This is a matrix experiment testing alignment between paired-pulse gap and trace window.
Do NOT run 9C.2 before 9C.1 produces a signal.

### 6.3 Arms (inherited from 9B)

- `L_then_R`: L pulse, gap, R pulse
- `R_then_L`: R pulse, gap, L pulse
- `simultaneous`: L and R at same time
- `separated_control`: L and R far apart (beyond trace window)

Each arm runs under OFF, activity, and event_pair modes.

### 6.4 Metrics

- `asym_diff = |L_to_R_l1 - R_to_L_l1|` — the primary directional signal
- Per-arm signed plasticity: `L_to_R_signed_mean`, `R_to_L_signed_mean`
- Trace diagnostics: `mean_trace_at_pair_time`, `trace_overlap_ratio`
- OFF baseline comparison: event_pair `|asym_diff|` must exceed OFF `|asym_diff|` by > 3×

### 6.5 Progression

```
9C.0 — design note only (this document)
9C.1 — single-seed smoke (seed=42, num_pairs=5)
        Fixed gap=500, sweep τ_trace ∈ {80, 200, 500, 1000, 1500}
        Verify: trace mechanism works, plumbing correct, no crashes
9C.2 — two-seed pilot (seeds=42,999)
        ONLY if 9C.1 shows directional trend
        gap × τ_trace interaction matrix
9C.3 — four-seed validation
        ONLY if 9C.2 pilot shows directional signal
        4 seeds × full sweep, formal result
```

## 7. Success Criteria

- **Directional separation:** `L_then_R` arm preferentially shifts plasticity toward
  L→R subgraph; `R_then_L` arm preferentially shifts toward R→L subgraph.
  The two arms must produce DIFFERENT directional signatures — not just both
  showing the same increase.
- **OFF baseline exceeded:** event_pair `|asym_diff|` must exceed OFF `|asym_diff|`
  by > 3× for at least one τ_trace value.
- **No false signal from simultaneity:** `simultaneous` arm does NOT produce
  strong directional signal (both traces fire together, no asymmetry).
- **Trace window matters:** `separated_control` (gap >> τ_trace) produces weaker
  directional signal than paired arms — proving the trace window is the gate.
- **Cross-seed consistency:** trend is consistent across at least 2 seeds in pilot.
- **Not just global shift:** if `L_then_R` and `R_then_L` both show the same
  magnitude increase, this is failure, not success — the signal must be ORDERED.

## 8. Failure Criteria

- **Global shift only:** `L_then_R` and `R_then_L` both show amplification but no
  directional separation — `|asym_diff|` grows in both arms equally. This is NOT
  order-specific plasticity; it is a global excitability increase (like 9A.2).
- **No directional signal:** `|asym_diff|` stays at OFF baseline despite trace
  mechanism functioning (like 9B.2) — trace is warm but doesn't route plasticity.
- **Seed-specific artifact:** directional signal appears in one seed but not
  another — mechanism is not reliable.
- **No paired vs separated separation:** `separated_control` produces similar
  signal to paired arms — trace window is not the discriminating factor.
- **Trace window irrelevant:** all τ_trace values produce the same result —
  the mechanism is not actually gating on temporal proximity.

## 9. Principles

- Single knob: τ_trace. Do not co-vary multiple parameters.
- No hard-coded order knowledge. The system must not be told "L was first."
- No LLM, reward, agent, goal, emotion, personality, language interface.
- Substrate-level temporal plasticity only.
- Negative results are documented and sealed, not discarded.
- Do not run 4-seed validation until pilot shows directional trend.

## 10. Next Steps

1. Review this design — refine mechanism sketch, confirm single-knob choice
2. Write `aniva/experiments/exp9C1_event_pair_smoke.py`
3. Run single-seed smoke locally (num_pairs=3, fast check)
4. If smoke passes: 2-seed pilot on cloud
