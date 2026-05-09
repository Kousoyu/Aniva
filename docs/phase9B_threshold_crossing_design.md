# Phase 9B: Threshold-Crossing Temporal Plasticity — Design

**Date:** 2026-05-06
**Status:** 设计文档（未实现）

---

## 1. Motivation

### 1.1 What Phase 9A proved

Phase 9A ran two EMA-based eligibility formulas through a complete 5-experiment validation chain:

| Experiment | Formula | Result |
|-----------|---------|--------|
| 9A smoke | activity-EMA | |L1| amplified 4-5x |
| 9A.1 | activity-EMA | cross-seed reproduced (3.3-5.9x) |
| 9A.2 | activity-EMA | global shift, not state-timing specific |
| 9A.3 | activity-EMA | cannot distinguish L→R from R→L order |
| 9A.4 | onset-EMA | zero signal, collapses to OFF baseline |

Both formulas fail for complementary reasons:

```
activity-EMA:  trace ≈ time-averaged activation
               → amplifies seed-intrinsic spatial bias
               → 4-5x |L1| but no order specificity

onset-EMA:     onset = max(Δact, 0) too sparse and too weak
               → eligibility ≈ 2.5e-05 vs Hebbian ≈ 0.09
               → drowned by 3-4 orders of magnitude
```

The root cause is not parameter tuning (β, τ, gap) — it is that **continuous activation dynamics + region-level pulses do not produce sharp enough temporal edges for EMA-based eligibility to detect order.**

### 1.2 What needs to change

The EMA approach asks: "who has been active recently, on average?"

The threshold-crossing approach asks: "who crossed the effective firing threshold, and when?"

By introducing a **discrete temporal event** (threshold crossing) into the continuous system, we create a sharp timestamp that EMA traces cannot provide.

---

## 2. Core Idea

### 2.1 Threshold crossing as a temporal event

Each unit has a `threshold` (initialized in [0.2, 0.4], same as the sigmoid soft-threshold used for synaptic output). When a unit's activation crosses this threshold from below:

```
crossing event = activation[t-1] < unit.threshold AND activation[t] >= unit.threshold
```

This is NOT a spike — it's a **continuous-system analogue**: the moment a unit becomes "effectively active."

Each unit tracks `last_crossing_time` (step count when the most recent crossing occurred).

### 2.2 Temporal eligibility from crossing time difference

For a connection source→target:

```
Δt = t_target_cross - t_source_cross
```

- If `0 < Δt < temporal_window`: source crossed before target → **causal order** → strengthen
- If `-temporal_window < Δt < 0`: target crossed before source → **anti-causal order** → weaken
- If `|Δt| >= temporal_window` or either unit has not crossed yet: no temporal term

The eligibility is applied as an **additive delta at the moment of target crossing** (not continuously at every step):

```
when target crosses:
    Δt = current_step - source.last_crossing_time
    if 0 < Δt < temporal_window:
        temporal_delta = +temporal_strength * f(Δt)
    elif -temporal_window < Δt < 0:
        temporal_delta = -temporal_strength * f(|Δt|)
```

### 2.3 Why this should work where EMA failed

| Property | activity-EMA | onset-EMA | threshold-crossing |
|----------|-------------|-----------|-------------------|
| Signal type | continuous | continuous (weak) | **discrete event** |
| Temporal resolution | ~200 steps (τ) | ~0 steps (too sparse) | **exact step** |
| Order detection | averaged away | too weak | **Δt with sign** |
| Robustness to gradual activation | low (smears) | low (drowns) | **high** (only crossing matters) |

Threshold crossing gives us what neither EMA could: a sharp, signed timestamp with sufficient signal strength.

---

## 3. Proposed Rule

### 3.1 Configuration

```python
# Phase 9B: threshold-crossing temporal plasticity
temporal_plasticity_enabled: bool = False          # unchanged
temporal_eligibility_mode: str = "activity"        # + "threshold_crossing"
temporal_trace_decay: float = 0.05                 # unchanged (used for trace if needed)
temporal_plasticity_rate: float = 0.5              # unchanged (or repurposed as crossing_strength)
temporal_eligibility_clip: float = 1.0             # unchanged

# New fields
temporal_crossing_window: int = 200                # max Δt for causal/anti-causal window
temporal_crossing_strength: float = 0.5            # weight of crossing term vs Hebbian
temporal_crossing_level_mode: str = "unit_threshold"  # "unit_threshold" | "fixed" | "percentile"
temporal_crossing_fixed_level: float = 0.3         # used if mode = "fixed"
temporal_crossing_refractory: int = 50             # min steps between crossings per unit
```

**Why refractory is required (not optional):** An 80-step region pulse can cause activation to oscillate around the threshold due to noise + recurrent synaptic feedback, producing 2-5 spurious crossings per pulse. Without refractory, these multiply crossing events generate contradictory Δt signals that cancel out. Refractory=50 steps is shorter than pulse_duration=80 but long enough to ensure only one crossing per pulse per unit. This is a minimum-viable component, not an optional feature.

### 3.2 State tracking

Each unit tracks:
- `previous_activation`: activation at step t-1 (to detect crossings)
- `last_crossing_time`: step count of most recent threshold crossing (-1 if never crossed)

Per connection, at each step:
- Hebbian term: computed as before (continuous, every step)
- Temporal term: computed **only when target unit crosses threshold**

### 3.3 Crossing detection

```python
def _detect_crossings(activations, prev_activations, thresholds,
                      last_crossing_time, current_step, refractory):
    """Return list of unit IDs that crossed threshold this step."""
    crossed = []
    for uid in range(n_units):
        # Only upward crossings: below → above threshold
        upward = (prev_activations[uid] < thresholds[uid]
                  and activations[uid] >= thresholds[uid])
        # Enforce refractory: must be ≥ refractory steps since last crossing
        not_refractory = (current_step - last_crossing_time[uid] >= refractory)
        if upward and not_refractory:
            crossed.append(uid)
    return crossed
```

**Crossing detection rules (Phase 9B.1 minimum version):**
- **Upward only**: Only `below-threshold → above-threshold` transitions are detected. Downward crossings (`above → below`) are explicitly ignored for 9B.1 — they could be added as a future extension, but the minimum version only asks "when did this unit become effectively active?"
- **Refractory-gated**: `current_step - last_crossing_time[uid] >= temporal_crossing_refractory` prevents multiple crossings within a single pulse due to activation oscillation around the threshold.
- **Initial state**: `last_crossing_time` initialized to -1 (or a large negative number), so the first crossing always passes the refractory check.

Alternative crossing level modes:
- `"unit_threshold"`: use each unit's own threshold (variable, initialized randomly)
- `"fixed"`: use a global fixed level (e.g., 0.3)
- `"percentile"`: use a percentile of each unit's recent activation history

Recommendation: start with `"unit_threshold"` — simplest, no new parameters, each unit's threshold already has physical meaning.

### 3.4 Temporal delta function

When target unit `tid` crosses at step `t`:

```python
for conn in connections_where_target_is[tid]:
    sid = conn.source_id
    t_source = last_crossing_time[sid]
    if t_source < 0:  # source never crossed
        continue
    dt = t - t_source
    if 0 < dt <= temporal_crossing_window:
        # causal: source before target → strengthen
        weight_factor = max(0.0, 1.0 - dt / temporal_crossing_window)  # linear decay
        temporal_delta = +temporal_crossing_strength * weight_factor * plasticity_rate
    elif -temporal_crossing_window <= dt < 0:
        # anti-causal: target before source → weaken
        weight_factor = max(0.0, 1.0 - abs(dt) / temporal_crossing_window)
        temporal_delta = -temporal_crossing_strength * weight_factor * plasticity_rate
    else:
        continue
    
    # Apply to weight (same sign convention as Hebbian)
    if conn.weight >= 0:
        conn.weight += temporal_delta
    else:
        conn.weight -= temporal_delta
```

### 3.5 Weight function f(Δt)

Options for the temporal kernel:

**Linear decay (simplest, recommended for first assay):**
```
f(Δt) = max(0, 1 - |Δt| / window)
```

**Exponential decay:**
```
f(Δt) = exp(-|Δt| / τ_crossing)
```

**Symmetric STDP-like:**
```
f(Δt) = A+ * exp(-Δt / τ+)  for Δt > 0
f(Δt) = -A- * exp(Δt / τ-)  for Δt < 0
```

Recommendation: linear decay for 9B.1. It has no extra parameters beyond `window`, and the qualitative behavior (stronger for closer crossings) matches the physical intuition.

---

## 4. Safety Gates

### 4.1 Default OFF

```
temporal_plasticity_enabled = False  # unchanged
temporal_eligibility_mode = "activity"  # unchanged default
```

All existing experiments and tests run identically. The new code path only activates when `temporal_plasticity_enabled=True` AND `temporal_eligibility_mode="threshold_crossing"`.

### 4.2 Preserved mechanisms

- Hebbian co-activation plasticity: **unchanged** (continuous, every step)
- Weight decay: **unchanged**
- Homeostasis: **unchanged**
- Energy gating: **unchanged**
- Synaptic output sigmoid: **unchanged**

The temporal term is purely additive, same as Phase 9A. Only the formula for `eligibility` changes.

### 4.3 Clipping and bounds

- `|temporal_delta|` clipped to `temporal_eligibility_clip * plasticity_rate`
- Weights remain clamped to [-1, 1]
- `last_crossing_time` initialized to -1 (not crossed) — prevents spurious Δt on first crossing

### 4.4 What this is NOT

- NOT a spiking neural network — activations remain continuous
- NOT event-driven simulation — simulation step remains uniform dt
- NOT a replacement for Hebbian plasticity — temporal term is additive
- NOT a reward/learning signal — purely local, pre-post timing
- NOT biologically detailed STDP — simplified to one crossing level per unit

---

## 5. First Assay: Phase 9B.1 Paired-Order

### 5.1 Design

Directly reuse the Phase 9A.3/9A.4 paired-order assay to enable direct comparison:

| Parameter | Value |
|-----------|-------|
| steps | 20,000 |
| seeds | 42, 77, 123, 999 |
| modes | OFF, activity, onset, threshold_crossing |
| arms | L_then_R, R_then_L, simultaneous, separated_control |
| crossing_window | 200 steps |
| crossing_strength | 0.5 |

### 5.2 Key metrics

**Structural metrics (same as 9A.3/9A.4):**

1. **L_then_R vs R_then_L delta vector L1** — primary: does threshold_crossing produce larger separation than activity/onset?
2. **L→R signed_mean asymmetry** — does L_then_R strengthen L→R; does R_then_L strengthen R→L?
3. **Simultaneous neutrality** — does simultaneous produce weaker directional signal?
4. **Separated control attenuation** — does large gap (300) reduce temporal effect?

**Crossing diagnostic metrics (new for 9B):**

5. **Crossing count per unit distribution**: min, median, max — is the crossing rate sufficient and not excessive?
6. **Crossing count by threshold quartile**: do high-threshold units cross at all? If Q4 (top 25% thresholds) crossing count < 10% of Q1 (bottom 25%), then `unit_threshold` as crossing level is biased toward low-threshold units.
7. **Fraction of steps with ≥1 crossing**: should be well above 0 but well below 1.0. If >50% of steps have crossings, the system reverts to near-continuous behavior.
8. **Mean inter-crossing interval**: should be larger than refractory (50) and shorter than pair_interval (600).
9. **Crossing count L-region vs R-region**: are crossings balanced across hemispheres? Imbalance would indicate the crossing level is systematically biased.
10. **Crossing balance L vs R**: `(L_count - R_count) / (L_count + R_count)` — should be near 0. Large imbalance = intrinsic spatial bias captured by crossing detection.

**These diagnostics distinguish three failure modes:**
- **Too sparse** (crossing/unit < 10 per 20k): signal as weak as onset-EMA, temporal delta too rare to accumulate.
- **Too dense** (crossing/unit > 1000 per 20k): every step crosses, threshold is too low, reverts to continuous behavior like activity-EMA.
- **Threshold-biased** (Q4/Q1 crossing ratio < 0.1): crossing events concentrated in low-threshold units, not representative of hemisphere-level temporal order.

### 5.3 Expected results

**If threshold-crossing works:**
```
OFF:                 cos ≈ 1.0, no asymmetry diff
activity:            cos ≈ 0.99999, |L1| ~2e-04, no asymmetry diff
onset:               cos ≈ 1.0, |L1| ~4e-05, no asymmetry diff
threshold_crossing:  cos < 0.9999, |L1| > activity, asymmetry diff > 1e-04
```

**If threshold-crossing also fails:**
- Crossing events too rare → not enough temporal signal
- Crossing events too frequent (every step) → reverts to continuous, same as activity-EMA
- Crossing level too high/low → no modulation by event order

---

## 6. Success Criteria

| Level | Criteria |
|-------|----------|
| Low | threshold_crossing mode stable, no explosion |
| Low | pytest passes, backward compatible |
| Medium | L_then_R vs R_then_L |L1| > activity mode |
| Medium | L_then_R vs R_then_L asymmetry diff > 1e-04 |
| Strong | L_then_R strengthens L→R subgraph; R_then_L strengthens R→L subgraph |
| Strong | simultaneous produces weaker directional signal than ordered arms |
| Gold | separated_control shows attenuated effect vs ordered arms |

**Failure modes to watch for:**
- Crossing count < 10 per unit per 20k steps → signal too sparse
- Crossing count > 1000 per unit per 20k steps → every step crosses, no temporal specificity
- All arms produce same directional asymmetry → crossing detects intrinsic bias, not event order

**Threshold quartile bias diagnostic:** If units in the top threshold quartile (Q4, threshold > 0.35) have < 10% of the crossing count of units in the bottom quartile (Q1, threshold < 0.25), then `unit_threshold` as crossing level is **biased toward low-threshold units**. The crossing events would be dominated by the easiest-to-activate population rather than providing a representative sample of hemisphere-level temporal order.

If this bias is detected in 9B.1, subsequent fixes in priority order:
1. **threshold + margin**: set crossing level to `unit.threshold + 0.05`, raising the bar slightly while preserving per-unit variation.
2. **Fixed global level**: use `temporal_crossing_fixed_level = 0.3` for all units — cleaner comparison but loses per-unit heterogeneity.
3. **Adaptive percentile**: use a rolling percentile of each unit's own activation history — most flexible but most parameters.

**Phase 9B.1 starts with `unit_threshold`** — the simplest option. The quartile diagnostic tells us whether it's viable or needs escalation. Do not pre-emptively switch to fixed/percentile before the diagnostic justifies it.

---

## 7. Implementation Plan

### 7.1 Files to modify

| File | Change |
|------|--------|
| `aniva/config.py` | + `temporal_crossing_window`, `temporal_crossing_strength`, `temporal_crossing_level_mode`, `temporal_crossing_fixed_level` |
| `aniva/life_core.py` | + `_previous_activations` (already added in 9A.4), `_last_crossing_time` array, crossing detection in step loop |
| `aniva/core/plasticity.py` | + threshold-crossing branch in temporal eligibility computation |

### 7.2 Files to create

| File | Role |
|------|------|
| `aniva/experiments/exp9B1_threshold_crossing_paired_order.py` | 4-mode paired-order assay |
| `docs/phase9B1_threshold_crossing_20k_notes.md` | Analysis |

### 7.3 Implementation order

1. Add config fields (default values that keep old behavior)
2. Add `_last_crossing_time` array to LifeCore, initialize to -1
3. After per-unit loop, detect crossings, update `last_crossing_time`
4. Add threshold-crossing branch to plasticity (guarded by mode check)
5. Run pytest (must pass 209/209)
6. Write 9B.1 experiment script
7. Run 20k, analyze, report

### 7.4 Key implementation detail: crossing detection timing

The crossing detection must happen AFTER activation is finalized for the current step (after steps 0-6 in LifeCore.step()), but BEFORE plasticity (step 7). The `last_crossing_time` for units that crossed THIS step should be updated AFTER plasticity has used the OLD `last_crossing_time` to compute Δt.

Order:
```
1. Detect crossings using (prev_act, current_act)
2. Compute plasticity:
   - Hebbian: as before (continuous)
   - Temporal: for each crossing target unit, compute Δt using OLD last_crossing_time
3. Update last_crossing_time for units that crossed this step
4. Update previous_activation = current_activation
```

This mirrors the 9A.4 ordering constraint (old trace → eligibility → update trace) with crossing times instead of traces.

**Same-step simultaneous crossing behavior:** If both L-region and R-region units cross threshold in the same step, the ordering above guarantees that neither side's `last_crossing_time` has been updated yet when computing Δt. Each crossing unit references the OTHER region's *previous* crossing time (from the last pulse cycle, typically ~600 steps ago), which is well outside the `temporal_crossing_window=200`. Therefore, **simultaneous same-step crossings produce no artificial causal temporal term between the crossing pair.** This is the correct behavior — simultaneous activation should NOT be interpreted as "L before R" or "R before L." No special-case handling is needed; the update ordering provides this guarantee automatically.

---

## 8. Design Tradeoffs

### 8.1 Why threshold-crossing over full STDP

Full STDP requires precise spike timing. Aniva has no spikes — activations are continuous. Threshold crossing is the minimal discrete event we can extract without redesigning the activation dynamics.

### 8.2 Why unit threshold over fixed level

Using each unit's own threshold means no new parameter. The threshold already has physical meaning (firing threshold for sigmoid output). Crossings occur at different levels for different units, creating natural heterogeneity.

Risk: units with very high thresholds may rarely cross, reducing signal. Mitigation: monitor crossing counts per unit in the first assay.

### 8.3 Why linear Δt decay over exponential

Linear decay has one parameter (window). Exponential has two (A+, τ+). The first assay should answer "does Δt-based eligibility work at all?" — not "what's the optimal temporal kernel shape?" Minimal parameters, maximal clarity.

### 8.4 Why apply at target crossing, not continuously

Applying temporal delta only at crossing events means the temporal term is event-sparse, like onset-EMA. The key difference: a crossing event is a BINARY, HIGH-MAGNITUDE signal, whereas onset is a continuous, TINY-MAGNITUDE signal. A unit crossing from 0.19 to 0.21 generates onset ≈ 0.02; a crossing event generates a full temporal delta.

---

## 9. What NOT to Do

- Do not add spike generators or change activation dynamics to spiking
- Do not replace Hebbian plasticity with STDP
- Do not add reward-modulated STDP
- Do not add dopamine/neuromodulator simulation
- Do not add multiple crossing levels per unit
- Do not change the Environment layer
- Do not introduce global reward/loss/error signals
- Do not run 120k before validating at 20k
- Do not add adaptive thresholds before baseline validation
- Do not tune β, τ, or window before first assay results

---

## 10. Open Questions

1. **Crossing frequency** *(empirical)*: How often do units cross threshold under region-pulse stimulation? If too rare (<1 per unit per 20k), the temporal signal will be as sparse as onset-EMA. If too frequent (near-continuous), it reverts to activity-EMA behavior. → **Answer: diagnostic output will measure this in 9B.1.**

2. **Crossing level mode** *(provisional decision)*: Start with `unit_threshold` for 9B.1. If threshold quartile diagnostic shows bias (Q4/Q1 ratio < 0.1), escalate to fixed level or adaptive percentile as described in Section 6. → **Decided: minimum version first, diagnostic-driven escalation.**

3. **Temporal window size** *(provisional decision)*: 200 steps for 9B.1. If crossing diagnostics show very short or very long inter-crossing intervals, adjust window in 9B.2. → **Decided: 200 for first assay.**

4. **Multiple crossings per pulse** *(decided)*: Enforce `temporal_crossing_refractory = 50` in 9B.1. This is a minimum-viable component, not an optional feature. → **Decided: refractory=50, see Section 3.1/3.3.**

These questions marked *(empirical)* can only be fully answered by running the first assay. The diagnostic output in Section 5.2 is designed to provide the data needed. Questions marked *(decided)* have been resolved in this design revision.

---

## 11. Summary

Phase 9B replaces EMA-based temporal eligibility with **threshold-crossing-based temporal eligibility**. The key insight:

> A discrete crossing event at a known time provides the sharp temporal signature that continuous EMA traces cannot. Δt between source and target crossings — with sign — is a direct measure of temporal order.

The design is minimal: one new detection mechanism (threshold crossing), one new state variable per unit (last_crossing_time), and one new temporal kernel (linear decay with window). Everything else — Hebbian term, homeostasis, energy, decay — remains unchanged.
