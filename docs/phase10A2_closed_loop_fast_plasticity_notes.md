# Phase 10A.2 — Closed-Loop Fast Plasticity Notes

> **定位：** 首次打开 9C event-pair fast plasticity。
> 9D consolidation OFF。
> 2-seed pilot。No slow structure claim。
> No digital-life / consciousness / personhood claim。

---

## 1. Summary

**Phase 10A.2 completed as 2-seed pilot.**

- Hard protocol: **2/2 PASS**
- Replay exactness: **0 mismatch, EXACT**
- Scientific signal: **CLEAN NEGATIVE**

Closed_loop and matched_open_loop_replay produced **bit-identical** fast
weights for both seeds. This is not a crash. It is not a bug. It is a
valid result that reveals a design property of the matched replay control.

---

## 2. Frozen Parameters

| Parameter | Value | Source |
|-----------|-------|--------|
| seeds | 42, 77 | 10A.0 |
| unit_count | 300 | 10A.0 |
| total_steps | 7500 | 10A.0 |
| warmup | 2000 | 10A.0 |
| decision_interval | 250 | 10A.1B |
| pulse_duration | 80 | 10A.0 |
| 9C event-pair plasticity | ON | 10A.2 |
| 9D consolidation | OFF | 10A.0 |
| Scheduler θ | w=5.0, b_none=+1.0, b_L/R=-1.5, b_sim=-3.0, τ=1.0 | 10A.0 |

---

## 3. Results

### 3.1 Per-Seed Fast Weight L1

| Arm | Seed 42 | Seed 77 |
|-----|---------|---------|
| closed_loop | 1848.58977647 | 1870.30457022 |
| matched_open_loop_replay | 1848.58977647 | 1870.30457022 |
| random_uniform_control | 1848.59304113 | 1870.31142244 |
| no_event_control | 1848.60198842 | 1870.30680629 |

### 3.2 Cross-Arm Deltas

| Delta | Seed 42 | Seed 77 |
|-------|---------|---------|
| closed − replay | **0.0** | **0.0** |
| closed − random | −0.00326466 | −0.00685222 |
| closed − no_event | −0.01221195 | −0.00223607 |

### 3.3 Scheduler & Event Distribution

| Metric | Seed 42 | Seed 77 |
|--------|---------|---------|
| decisions | 22 | 22 |
| events | 12 | 11 |
| none_rate | 0.45 | 0.50 |
| event types | 2 (L/R) | 2 (L/R) |
| simultaneous | 0 | 0 |

### 3.4 Protocol Checks

| Check | Seed 42 | Seed 77 |
|-------|:---:|:---:|
| No NaN | ✅ | ✅ |
| No explosion (max_abs_w < 10) | ✅ (0.829) | ✅ (0.829) |
| Replay hash_mismatch = 0 | ✅ | ✅ |
| Event count match | ✅ (12/12) | ✅ (11/11) |
| Timestamp match | ✅ | ✅ |
| 9C ON, 9D OFF | ✅ | ✅ |
| Scheduler denylist | ✅ | ✅ |

---

## 4. Interpretation

### 4.1 Bit-Identical closed vs replay

The closed_loop and matched_open_loop_replay arms produced **exactly the
same fast weight** — identical to 8 decimal places — for both seeds.

This is the expected outcome of the current matched replay design.
Under these conditions:

- **Same seed** → same initial unit positions, connections, weights.
- **Same event log** → same events at same timestamps with same phi.
- **Deterministic dynamics** → `LifeCore.step()` is deterministic given
  same inputs.
- **State-agnostic 9C plasticity** → `apply_event_pair_phi(trace, phi)`
  only depends on trace and phi, not on unit activations or other state.

When all four hold, the replay trajectory is *guaranteed* to be identical
to the closed_loop trajectory. The feedback loop (state → event) only
determines *which* events are chosen. Once the events are recorded and
replayed exactly, the feedback context is erased.

**The matched replay control became a mirror, not a fork.**

### 4.2 Why This Is Not a Bug

The code is correct. The replay is exact. The result is deterministic.

The issue is in the *control design*, not the implementation. A matched
replay that shares the same seed, same initial state, and same event log
does not create a different feedback context — it creates the same
trajectory deterministically.

### 4.3 Implications

- **This does NOT mean "feedback context doesn't matter."** It means
  this particular control design cannot *detect* whether it matters,
  because it removes the feedback contrast entirely.
- **Do NOT proceed directly to 10A.3 with this same replay design.**
  If 10A.3 also uses same-seed exact replay, 9D consolidation will
  also produce identical results for the same reason.
- **Next step: 10A.2B matched replay control redesign.** The replay
  must introduce genuine feedback-context divergence — e.g., replay
  onto a different seed, replay after divergent warmup, stale-state
  replay, or delayed/permuted replay.

### 4.4 Tiny random / no_event deltas

The random_uniform and no_event arms differ from closed_loop by
~0.0006% of the total fast weight L1. At scale ~1848, a delta of
0.003–0.012 is essentially zero.

The no_event arm has *slightly higher* fast weight L1 than the event
arms — events marginally *reduce* total fast weight magnitude rather
than increasing it. This makes sense: event-triggered dW updates can
both increase and decrease individual weights (trace × phi can be
positive or negative), and the clipping to [-1, 1] after each update
can slightly reduce L1.

---

## 5. Policy

- 10A.2 is a **CLEAN NEGATIVE / design-revealing negative**.
- This result is valid and important — it shows the exact replay
  control degenerates to deterministic equivalence under same seed.
- Do NOT rewrite the result as "feedback doesn't matter."
- Do NOT enter 10A.3 with the same replay design.
- Next step: **10A.2B matched replay control redesign.**

---

## 6. Boundary

- 9C event-pair plasticity was ON.
- 9D consolidation was OFF.
- No slow weight measurement or claim.
- No structural plasticity claim beyond fast weight.
- No digital-life / consciousness / personhood claim.
- 10A.0 preregistration is NOT modified.
- 10A.1 / 10A.1B results are NOT overwritten.
