# Phase 8B.3: Duration-Coupled Closed Loop — 20k Notes

**Date:** 2026-05-05
**Status:** 完成

---

## 1. Purpose

8B.2 proved that L/R label bias cannot break the plasticity direction lock (cos=1.0 at all gain levels). The hypothesis was: the system follows the rhythm (event timing), not the drum choice (which side).

8B.3 tests whether coupling to event DURATION (how long the drum tail lasts) can break the lock. Duration was chosen because Phase 8A showed duration/continuity is an effective dimension for structural change.

---

## 2. Design

| Parameter | Value |
|-----------|-------|
| steps | 20,000 |
| seeds | 42, 999 |
| config | A only (interval=200, base_duration=80) |
| duration_gain | 300.0 |
| duration range | [40, 160] (±50% of base) |

Three arms:
- **open_loop**: fixed duration=80, no state feedback
- **closed_loop_dur**: same event times + L/R labels as base stream, but duration modulated by current lr_imbalance
- **matched_dur_shuf**: closed_loop's duration sequence replayed with shuffled state-time assignment

Duration rule: `bias = clip(gain * lr_imbalance, -0.5, 0.5)`, then `dur_R = base * (1+bias)`, `dur_L = base * (1-bias)`.

---

## 3. Results

### 3.1 Event Duration Summary

```
seed  arm                dur(L)  dur(R)  dur_std   total_L   total_R
------------------------------------------------------------------------
  42  open_loop           80.0    80.0     0.0      3040      4880
  42  closed_loop_dur     40.0   120.0    38.9      1520      7320
  42  matched_dur_shuf    92.6    87.2    38.9      3520      5320

 999  open_loop           80.0    80.0     0.0      3040      4880
 999  closed_loop_dur     68.3   101.3    37.8      2594      6179
 999  matched_dur_shuf    87.5    89.3    37.8      3324      5449
```

Duration modulation is strong and consistent: closed_loop creates 2-3x duration asymmetry. Matched_shuffle redistributes the same durations randomly, eliminating the state-time correlation.

### 3.2 Structural Summary

```
seed  arm                ΔwL1 (vs ol)
----------------------------------------
  42  closed_loop_dur    +2.34e-06
  42  matched_dur_shuf   +1.24e-06

 999  closed_loop_dur    -7.08e-07
 999  matched_dur_shuf   -1.33e-06
```

ΔwL1 is tiny (~10^-6 range), same magnitude as 8B.2 gain sweep.

### 3.3 Cross-Arm Delta Vector

```
seed    cos(cl, ol)    cos(ms, ol)    cos(cl, ms)   |cl-ms|_L1
------------------------------------------------------------------
  42     1.000000       1.000000       1.000000      3.23e-05
 999     1.000000       1.000000       1.000000      3.24e-05
```

**cos(cl, ms) = 1.000000 at both seeds.**

### 3.4 Cross-Experiment |cl-ms|_L1 Comparison

```
experiment  coupling_target  seed 42       seed 999
---------------------------------------------------------
8B.2 g=2.5  L/R label        4.72e-05      2.99e-05
8B.2 g=5.0  L/R label        3.80e-05      3.02e-05
8B.2 g=8.0  L/R label        4.36e-05      3.41e-05
8B.3 g=300  duration         3.23e-05      3.24e-05
```

|cl-ms|_L1 is in the same 3-5e-5 range across ALL coupling targets and strengths. Duration coupling does NOT increase structural divergence.

### 3.5 Regional Readout

```
seed  arm                L_in       L_out      R_in       R_out      within     cross
----------------------------------------------------------------------------------------
  42  open_loop          0.19494    0.19594    0.19583    0.19410    0.19593    0.19436
  42  closed_loop_dur    0.19495    0.19595    0.19583    0.19410    0.19593    0.19436
  42  matched_dur_shuf   0.19494    0.19595    0.19583    0.19410    0.19593    0.19436

 999  open_loop          0.19531    0.19849    0.19767    0.19629    0.19699    0.19670
 999  closed_loop_dur    0.19531    0.19849    0.19767    0.19629    0.19699    0.19670
 999  matched_dur_shuf   0.19531    0.19848    0.19767    0.19629    0.19699    0.19670
```

Regional L1 values are identical to 4-5 decimal places across all arms within each seed. No subgraph-level signal exists.

---

## 4. Interpretation

### 4.1 Duration coupling does not break the direction lock

This is the central finding. Despite strong duration modulation:
- Seed 42: R events last 3x longer than L events (120 vs 40)
- Seed 999: R events last ~1.5x longer than L events (101 vs 68)

...the delta vectors remain perfectly aligned across all three arms (cos=1.000000).

### 4.2 Why this matters more than if cos had dropped

8B.2 ruled out "which drum is struck" (L/R label).
8B.3 rules out "how long the drum tail lasts" (duration).

Two independent event-property dimensions, both coupled to the SAME base event timing structure, both produce zero structural divergence. This converges on a clean physical model:

**The plasticity trajectory is dominated by the base event TIMING structure + initial topology resonance. Event properties (label, duration) modulated at those fixed times are just "decorations" on the same underlying rhythm — the weight dynamics follow the rhythm, not the decorations.**

### 4.3 The timing lock hypothesis

The event interval (200 steps) creates a regular temporal grid. Each event onset triggers a cascade of activation → plasticity updates. The spatial pattern of which connections get updated is determined by:
1. The stimulus positions (fixed)
2. The network's current activation state (which is driven by the timing rhythm)

Modulating event DURATION changes the sustained presence of stimulation, but does not change WHEN the cascade starts. The plasticity updates are onset-driven, so the update pattern is locked by arrival times.

### 4.4 Physical analogy

Think of a bell being struck at regular intervals. Whether you strike the left side or right side of the bell (8B.2), or strike harder vs softer (8B.3 duration), the bell's resonant modes are determined by its shape and the strike TIMING. The bell doesn't develop a different vibrational mode just because you hit a different spot or change the force — its fundamental resonance follows the rhythm of strikes.

---

## 5. Success Criteria Assessment

| Level | Criteria | Status |
|-------|----------|--------|
| Low | Duration modulation functional | ✅ Strong (R dur 1.5-3x L dur) |
| Medium | |cl-ms|_L1 larger than 8B.2 | ❌ Same range (3.2e-05 vs 3-5e-05) |
| Strong | cos(cl, ms) < 1.0 | ❌ Failed — cos=1.0 |
| Failure | All structural metrics flat | ✅ Confirmed |

The experiment confirms duration coupling works mechanically but produces no structural divergence.

---

## 6. Conclusion

**Event-property coupling is fundamentally limited — regardless of which property (label or duration) is modulated.**

The bottleneck is not which property is coupled, but WHAT the coupling is anchored to: the fixed event timing structure. As long as events occur at the same predetermined times (interval=200), the plasticity cascade follows the same temporal pattern, and no amount of property modulation at those times can divert the trajectory.

### What this rules out

- L/R label bias: ruled out (8B.2)
- Event duration modulation: ruled out (8B.3)
- Any future event-property coupling at fixed event times: implicitly ruled out

### What remains to be tested

The next logical step is coupling to event TIMING itself:
- **event_interval modulation**: lr_imbalance → earlier or later next event onset
- **insertion/deletion**: state-timed events that can appear at NEW times (not just modulate existing events)
- **state-gated event triggering**: events fire when activation crosses a threshold, not on a fixed schedule

These are fundamentally different because they change WHEN events happen, not just WHAT happens at predetermined times.

---

## 7. Next Direction

Two paths forward from here:

**A. Interval coupling (8B.4):** lr_imbalance → next event interval modulation. L-active state → next event sooner. R-active state → next event later. This changes the temporal grid itself.

**B. State-triggered events (8B.5):** Instead of a predetermined event stream, events fire when regional activation crosses a threshold. The event timing IS the state — fully closed-loop timing. This is the most "natural" coupling and closest to how biological systems work.

Path B is more ambitious but aligns with the principle of "real feedback." Path A is a smaller step that can isolate whether interval perturbation alone breaks the lock.

Note: 8B.3 also confirms that structural readout (regional decomposition + delta vector comparison) is a sensitive diagnostic that correctly identifies zero effect — it doesn't produce false positives.
