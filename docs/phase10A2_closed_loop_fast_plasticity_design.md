# Phase 10A.2 — Closed-Loop Fast Plasticity Design

> **定位：** design only。不实现，不跑实验。
> Phase 10A.2 第一次打开 9C fast event-pair plasticity。
> 目标是验证闭环事件历史能否在 fast weight 上留下可区分的水痕。
> **这不是问"骨头会不会记住"（9D 已经回答了）。**
> 这是在问：**"由世界状态反馈生成的历史，是否在快速痕迹层就与随机/回放不同。**
>
> 9D consolidation OFF。Slow structure 不在本阶段范围。

---

## 1. Background

### 1.1 Where We Are

```
10A.0: design freeze + preregistration
10A.1: scheduler plumbing smoke (caveated, 1/2 soft pass)
10A.1B: calibration variant (clean pass, decision_interval=250)
10A.2: ← THIS DOCUMENT — first time 9C ON
```

10A.1B established that the parameterized stochastic scheduler works at
adequate measurement resolution (22 decision points). The same plumbing
config becomes 10A.2's event-generation layer.

### 1.2 From 9D to 10A.2 — Different Questions

| Aspect | Phase 9D | Phase 10A.2 |
|--------|----------|-------------|
| Event source | Designer-specified fixed schedule | State-feedback scheduler |
| Key question | Can event order deposit into slow structure? | Can closed-loop events change fast weight trajectory? |
| Plasticity layer | 9C dW → tag → capture → slow_weight | 9C dW only (trace + fast weight) |
| Consolidation | ON (tag, capture, slow_weight write) | OFF |
| Key control | simultaneous, no_event | + matched replay, random control |
| What's measured | corrected_slow_DI | fast_weight_l1, closed vs replay/random delta |

9D proved: "fixed schedule events can be deposited as structure."

10A.2 asks: "do events from world feedback leave a different fast weight
signature than identical events replayed without that feedback context?"

### 1.3 Why Fast Weight Before Slow Structure

The 9C event-pair plasticity pipeline has two layers:

1. **Fast weights** (`_weight_cache`): Modified immediately on event arrival
   via `apply_event_pair_phi(phi)`. Trace accumulates, gate opens, dW injected.
   This is the "ink" — the transient synaptic change.

2. **Slow weights** (`_slow_weight_cache`): 9D consolidation captures dW over
   time via tag accumulation → capture trigger. This is the "scar" — the
   enduring structural record.

10A.2 only opens layer 1. If closed-loop events can't even produce a
distinguishable fast weight pattern, there's no point opening layer 2.
If they can, 10A.3 opens layer 2 and tests whether the difference
persists into slow structure.

---

## 2. Research Question

> Does a state-feedback (closed-loop) event history produce a fast weight
> trajectory that differs from:
> (a) matched open-loop replay of the same events, and
> (b) random events with similar frequency / timing / type distribution?

**Sub-questions:**

1. Does closed_loop fast_weight differ from no_event baseline?
2. Does closed_loop differ from matched replay (same events, no feedback)?
3. Does closed_loop differ from random control (same expected event count,
   uniform random timing/type)?
4. Are the effects consistent across both seeds (42, 77)?

---

## 3. Frozen Parameters

### 3.1 Inherited from 10A.1B

| Parameter | Value | Source |
|-----------|-------|--------|
| seeds | 42, 77 | 10A.0 |
| unit_count | 300 | 10A.0 |
| total_steps | 7500 | 10A.0 |
| warmup | 2000 | 10A.0 |
| decision_interval | 250 | **10A.1B** |
| pulse_duration | 80 | 10A.0 |
| 9D consolidation | OFF | 10A.0 |

### 3.2 Scheduler θ (Frozen, from 10A.0)

| Parameter | Value |
|-----------|-------|
| w | 5.0 |
| b_none | +1.0 |
| b_L | -1.5 |
| b_R | -1.5 |
| b_sim | -3.0 |
| τ | 1.0 |

### 3.3 9C Event-Pair Plasticity (ON)

| Parameter | Value | Source |
|-----------|-------|--------|
| event_pair_plasticity_enabled | **True** | **NEW for 10A.2** |
| event_pair_trace_tau | 1000.0 | AnivaConfig default |
| event_pair_target_update_l1 | 1e-4 | AnivaConfig default |
| event_pair_gate_mode | "soft_trace_gate" | AnivaConfig default |
| event_pair_trace_gate_ref | 3e-2 | AnivaConfig default |
| event_pair_gate_power | 1.0 | AnivaConfig default |

These are the default 9C parameters established in Phase 9C and used
throughout Phase 9D. They are NOT tuned in 10A.2.

### 3.4 Scheduler Inputs (Unchanged)

```
Allowed:
  activity_L, activity_R

Disallowed:
  arm_label, event_count, event_history, weights, tags, connections,
  future observations, post-hoc metrics
```

### 3.5 RNG Separation (Unchanged)

```
seed_env   = seed          # LifeCore init, environment noise
seed_sched = seed + 1000   # Scheduler RNG
```

For random_uniform_control: a separate `control_rng = seed + 2000` is used
for timing/type randomization, independent of both scheduler and env RNG.

---

## 4. Arms

### 4.1 closed_loop

The primary arm. Scheduler is active, generates events from state feedback.
Events are applied both as environment stimuli AND as 9C event-pair plasticity
triggers.

```
for step in range(total_steps):
    influences = env.compute_influences(core.units, step)
    core.step(env_influences=influences if influences else None)

    if step in decision_points:
        act_l, act_r = compute_region_activity(core)
        result = scheduler.propose(act_l, act_r)
        log_decision(result)

        if result.chosen != "none":
            phi = phi_cache[result.chosen]  # or phi_sim for simultaneous
            env.add_event(StimulusEvent(
                stimulus=STIM_MAP[result.chosen],
                start_step=step,
                duration_steps=pulse_dur
            ))
            core.apply_event_pair_phi(phi)  # ← 9C plasticity trigger

    # No consolidation step — 9D is OFF
```

### 4.2 matched_open_loop_replay

Reads the closed_loop event log. At each logged timestamp, injects the
exact same event with the exact same phi payload. The scheduler is
**completely disabled** — no state read, no re-sampling, no re-decision.

The only difference from closed_loop: the system state at the moment
of event arrival may differ, because the replay trajectory has no
feedback loop conditioning it.

```
# Load closed_loop event log
trace = load_event_trace(closed_loop_log)
replay_idx = 0

for step in range(total_steps):
    influences = env.compute_influences(core.units, step)
    core.step(env_influences=influences if influences else None)

    # Replay: fire events at logged timestamps
    while replay_idx < len(trace) and trace[replay_idx].t == step:
        event = trace[replay_idx]
        phi = load_phi(event.chosen)
        assert hash(phi) == event.payload_hash  # HARD: must match

        env.add_event(StimulusEvent(
            stimulus=STIM_MAP[event.chosen],
            start_step=step,
            duration_steps=pulse_dur
        ))
        core.apply_event_pair_phi(phi)

        replay_idx += 1

# HARD check: replay_idx must consume ALL events
assert replay_idx == len(trace)
```

### 4.3 random_uniform_control

Generates events with the same expected count as the closed_loop arm
(computed per seed), but with uniform random timing and type selection.

**Procedure:**
1. Run closed_loop first (or use existing 10A.1B closed_loop log).
2. Extract `N = len(closed_loop_events)` for that seed.
3. Generate N events:
   - Timing: N random integers from `range(warmup, total_steps)`, no replacement
   - Type: L/R with equal probability (skip none and simultaneous for simplicity)
4. Apply events at generated timestamps.
5. No scheduler, no state read, no feedback.

This arm tests whether the event count alone (with random timing and type)
can explain the closed_loop fast weight effect.

### 4.4 no_event_control

Zero events for the full 7500 steps. The 9C trace still decays (it decays
every step regardless), but no event ever triggers `apply_event_pair_phi`.

This is the null baseline: what does the fast weight look like with no
external perturbation at all?

---

## 5. Event Log Schema (Extended from 10A.1)

The event log schema from 10A.1 is preserved. One additional field for 10A.2:

| Field | Type | Added In | Description |
|-------|------|----------|-------------|
| trace_mass_before | float | 10A.2 | `sum(abs(trace))` before phi accumulation |
| phi_mass | float | 10A.2 | `sum(abs(phi))` of applied phi |
| dW_l1 | float | 10A.2 | L1 norm of actual dW applied (from ledger) |
| gate_value | float | 10A.2 | Gate value at time of update |
| fast_weight_snapshot_l1 | float | 10A.2 | L1 norm of `_weight_cache` at decision time |

These fields are diagnostic only, not used for pass/fail gating.

---

## 6. Metrics

### 6.1 Primary Metrics (Per Seed)

| Metric | Computation | What It Measures |
|--------|-------------|-----------------|
| fast_weight_l1_total | `sum(abs(weight_cache))` at final step | Total fast weight magnitude |
| fast_weight_l1_vs_no_event | `l1(closed) - l1(no_event)` | Effect of any events at all |
| closed_vs_replay_fast_l1 | `l1(closed) - l1(replay)` | Effect of feedback context |
| closed_vs_random_fast_l1 | `l1(closed) - l1(random)` | Effect beyond random events |
| replay_exactness | hash_mismatch_count, event_count_diff, timestamp_diff | Replay fidelity |
| event_count | number of non-none decisions | Event volume |
| event_distribution | {L, R, sim} counts | Event type balance |
| nan_count | count of NaN activations | Health |
| max_abs_weight | max(abs(weight_cache)) | Explosion detection |

### 6.2 Secondary Metrics (Reported, Not Gated)

| Metric | Computation |
|--------|-------------|
| fast_weight_per_region | L1 of weights with source in L / R / M region |
| fast_weight_DI | Directional index, if L/R asymmetry is measurable |
| inter_seed_event_divergence | Difference in event patterns between seeds 42 and 77 |
| trace_mass_trajectory | Trace L1 over time for each arm |
| gate_open_fraction | Fraction of events where gate > 0.5 |
| dW_l1_distribution | Distribution of dW magnitudes across events |

### 6.3 Cross-Arm Comparisons

| Comparison | Interpretation |
|------------|---------------|
| closed > no_event | Events change fast weight (sanity check) |
| closed ≠ replay | Feedback context matters — same events at wrong state produce different plasticity |
| closed ≠ random | Not just event count — timing/type from state matters |
| seed42 ≠ seed77 | Seed-specific dynamics produce different fast weight outcomes |

---

## 7. Success Criteria (Pilot — 2 Seeds)

### 7.1 Hard Protocol (HARD — Any FAIL Invalidates 10A.2 for That Seed)

| # | Criterion | Threshold | Detection |
|---|-----------|-----------|-----------|
| P1 | No crash, no NaN | 0 | Auto |
| P2 | No weight explosion | max_abs_weight < 10.0 | Auto |
| P3 | Replay exactness | hash_mismatch = 0, event_count_diff = 0, timestamp_diff = 0 | Auto |
| P4 | Event log schema complete | All required fields present | Validation |
| P5 | 9C ON, 9D OFF confirmed | assert cfg.event_pair_plasticity_enabled; assert not cfg.consolidation_enabled | Assert |
| P6 | Scheduler denylist not violated | No arm_label, no event_count, no weight access | Code review |
| P7 | Replay player does not read state | No scheduler import in replay; no obs read | Code review |
| P8 | Random control does not use closed_loop state | Timing/type from RNG, not from state | Code review |

### 7.2 Soft — Protocol-Style (SOFT — Reported, Not Gated)

| # | Criterion | Threshold |
|---|-----------|-----------|
| S1 | Events change fast weight | `l1(closed_loop) - l1(no_event)` measurably > 0 |
| S2 | Scheduler does not degenerate | none_rate per seed in [0.30, 0.90] |
| S3 | Event type diversity | ≥ 2 non-none types per seed |
| S4 | Both seeds complete | No exclusion |

### 7.3 Soft — Scientific Signal (SOFT — Reported, Not Overclaimed)

| # | Criterion | Threshold |
|---|-----------|-----------|
| F1 | Closed vs replay difference exists | `l1(closed) - l1(replay)` is non-trivial |
| F2 | Closed vs random difference exists | `l1(closed) - l1(random)` is non-trivial |
| F3 | Per-region differences are interpretable | Qualitative |
| F4 | Seed consistency | Direction of closed-replay delta same sign in both seeds |

### 7.4 What 10A.2 Success Does NOT Mean

- Does NOT mean slow structure was deposited (that's 10A.3).
- Does NOT mean the effect is large or functionally significant.
- Does NOT mean digital life / consciousness / personhood.
- Does NOT mean the scheduler is optimal or adaptive.
- Does NOT mean the effect survives 4-seed formal validation (that's 10A.4).

10A.2 success means: **"Fast weight trajectory carries a measurable signature
of whether events were generated from state feedback vs. replayed without that
feedback. The signature is not trivially explained by event count or random
timing."**

---

## 8. Failure Modes and Interpretation

| Failure | Interpretation |
|---------|---------------|
| Replay hash mismatch | Replay implementation bug; fix before re-running |
| NaN / weight explosion | 9C plasticity interacts badly with scheduler pipeline; debug |
| closed ≈ no_event | 9C plasticity not engaging (gate closed, trace too low); check event phi mass and trace_mass |
| closed ≈ replay | Feedback context doesn't matter for fast weight — events have same effect regardless of state at arrival time |
| closed ≈ random | Event timing/type from state feedback no different from random — scheduler not capturing meaningful state information |
| All effects vanish | Either 9C plasticity is too weak, or scheduler events aren't differentiated enough by state |
| Scheduler degenerates again | Despite interval=250, some interaction with 9C causes state collapse; needs diagnosis |
| Seed inconsistency | One seed shows effect, other doesn't — may be real seed-dependent dynamics, not necessarily a bug |

---

## 9. Anti-Cheat (Compiled-Time + Runtime + Audit)

### 9.1 Compile-Time (Static)

- [ ] Scheduler function signature does not include `arm_label`
- [ ] Scheduler does not import `plasticity_consolidation`, `plasticity_event_pair`
- [ ] Scheduler does not access `_slow_weight_cache`, `_tag_cache`, `_weight_cache`
- [ ] Scheduler does not access `connections`
- [ ] Replay player does not import `Scheduler`
- [ ] Random control generator does not import `Scheduler`

### 9.2 Runtime (Dynamic)

- [ ] Scheduler has no internal event counter (no memory of past decisions)
- [ ] Event generation uses only `obs` + `sched_rng`
- [ ] Replay player does not read state (no `compute_region_activity`, no `core._activations`)
- [ ] Replay player does not re-sample (uses logged `chosen_event` directly)
- [ ] Random control timing/type generated from `control_rng` only, no state read
- [ ] All arms use identical `AnivaConfig` (except arm-specific flags)
- [ ] All arms use same initial `LifeCore` seed

### 9.3 Post-Hoc (Audit)

- [ ] Primary metrics computed by offline script, not in step loop
- [ ] All config params logged as SHA256
- [ ] All RNG seeds logged
- [ ] Replay trace_hash logged and verified
- [ ] No parameter tuning between seeds
- [ ] No parameter tuning between arms
- [ ] No post-hoc adjustment of scheduler θ
- [ ] Failed seeds reported, not silently excluded

---

## 10. Runtime Estimate

| Arm | Per-Seed Estimate | Notes |
|-----|-------------------|-------|
| closed_loop | ~3 min | 9C trace decay every step + event updates |
| matched_open_loop_replay | ~3 min | Same 9C load, no scheduler overhead |
| random_uniform_control | ~2 min | Same 9C load, no scheduler |
| no_event_control | ~2 min | Trace decay only, no event updates |

- 2 seeds × 4 arms ≈ ~20 min local total
- Under 10 min with sequential execution per seed
- Local allowed for pilot; if > 15 min per seed, move to ECS

---

## 11. Output Artifacts

| Artifact | Path |
|----------|------|
| Event logs (per arm, per seed) | `results/phase10A2_{arm}_seed{seed}_events.csv` |
| Fast weight snapshots | `results/phase10A2_{arm}_seed{seed}_fast_weight.csv` |
| Run summaries | `results/phase10A2_{arm}_seed{seed}_summary.json` |
| Aggregate comparison | `results/phase10A2_aggregate.json` |
| Smoke notes | `docs/phase10A2_fast_plasticity_smoke_notes.md` |
| Trace hash verification | `results/phase10A2_trace_hashes.csv` |

---

## 12. Relationship to 10A.0 Preregistration

10A.2 maps to the preregistered criteria:

| Prereg Criterion | 10A.2 Implementation |
|------------------|---------------------|
| P1–P4 | Same protocol layer as 10A.1 |
| F1: fast_weight differs from no_event | closed_loop vs no_event_control |
| F2: difference not explainable by event count alone | closed_loop vs random_uniform_control |

The preregistered matched replay control is the key innovation — it
isolates the feedback context as the only variable between arms.

---

## 13. Boundary

- 9C event-pair fast plasticity is ON.
- 9D consolidation is OFF.
- No slow weight measurement or claim.
- No structural plasticity claim beyond fast weight.
- No digital-life / consciousness / personhood claim.
- Scheduler θ is frozen from 10A.0.
- Decision interval is frozen from 10A.1B.
- This is a 2-seed pilot. Formal 4-seed validation is in 10A.4.
- 10A.0 preregistration is NOT modified.
- 10A.1 / 10A.1B results are NOT overwritten.
