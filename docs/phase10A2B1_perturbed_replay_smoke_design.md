# Phase 10A.2B.1 — Perturbed Initial State Replay Smoke Design

> **定位：** Scheme E design freeze。只写设计，不实现。
> 在 10A.2B 的 5 个候选 scheme 中，Scheme E 是首选——同 seed + 同 topology
> + 同 event log，仅在 replay 初始 activation 上加一次小扰动。
> 目标是检测：state context 差异是否能被 9C fast plasticity 管线放大为
> 可测量的 fast weight 分叉。
>
> 不改 10A.2 结论。不调 θ。不开 9D。

---

## 1. Background

10A.2 证明：same seed + same initial state + same event log + deterministic
9C pipeline → closed_loop ≡ matched_replay (bit-identical fast weight)。

10A.2B.1 在这个结论上加一个最小变量：**初始 activation 的一次性微扰**。
拓扑不变、weights 不变、connections 不变、event log 完全不变。唯一区别：
replay arm 在 t=0 时，unit activations 被加了一个小 ε。

如果这个微小初始差异经过 2000 步 warmup 传播后，能在 9C fast weight 上留下
可测量的分叉，说明 fast layer 对 state context 敏感——10A.2 的 negative 是
镜子问题，不是机制问题。

如果即使有扰动仍然 closed ≈ perturbed_replay，说明 9C fast plasticity
在当前时间尺度/事件数量下几乎完全由 event log 决定，state context 不进入。

---

## 2. Frozen Parameters

### 2.1 Inherited from 10A.2 (Unchanged)

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
| event_pair_ledger_enabled | True | 10A.2 |
| Scheduler θ | w=5.0, b_none=+1.0, b_L/R=-1.5, b_sim=-3.0, τ=1.0 | 10A.0 |

### 2.2 Perturbation Parameters (FROZEN — New for 10A.2B.1)

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| perturbation_target | **unit activations only** | Not weights, not topology, not connections, not energy |
| perturbation_magnitude | **ε = 0.02** | 2× per-step noise_strength, applied once |
| perturbation_distribution | **uniform [-ε, +ε] per unit** | Zero-mean, no directional bias |
| perturbation_clip | **[0.0, 1.0]** after perturbation | Same as standard activation clamp |
| perturbation_timing | **t = 0, once, before first step** | Not continuous, not repeated |
| perturb_rng_seed_rule | **seed_env + 3000** | Independent of env (seed), sched (seed+1000), control (seed+2000) |
| perturbation_scope | **all units (N=300)** | Every unit gets independent draw |

### 2.3 What Is NOT Perturbed

- `_positions` — topology unchanged
- `_weight_cache` — initial weights unchanged
- `connections` — seed-identical
- `_event_trace` — starts at 0 in both arms (trace is accumulated, not initialized)
- `_energy` — untouched
- `_thresholds` — untouched
- `event log` — exact same events at exact same timestamps
- `noise seed` — same env_rng sequence in both arms

---

## 3. Arms

### 3.1 closed_loop

Identical to 10A.2 closed_loop. Scheduler active, generates event log.
This arm produces the reference event trace.

### 3.2 exact_replay

Identical to 10A.2 matched_open_loop_replay. Same seed, same initial state,
same event log. Scheduler disabled. Expected result: `closed_l1 == exact_l1`
(bit-identical). This arm **re-confirms the 10A.2 mirror result** within
the same run.

### 3.3 perturbed_replay

Same seed, same topology, same event log as closed_loop. Scheduler disabled.
At t=0, before first `core.step()`:

```python
perturb_rng = np.random.default_rng(seed + 3000)
core._activations += perturb_rng.uniform(-epsilon, +epsilon, size=n_units)
np.clip(core._activations, 0.0, 1.0, out=core._activations)
```

Then the simulation proceeds identically to exact_replay — events are
replayed at their logged timestamps with the same phi payloads.

This is the **primary test arm**. If `perturbed_l1 ≠ closed_l1`, the
9C pipeline has amplified a t=0 perturbation into a measurable fast
weight difference at t=7500.

### 3.4 no_event_control (Optional)

Same as 10A.2. No events, 9C trace decays only. Optional baseline —
can be skipped if runtime budget is tight.

---

## 4. Expected Trajectory

```
t=0    t=2000 (warmup end)     t=7500 (final)
│       │                        │
├─ closed_loop ──────────────────┤  fast_l1_closed
│       │                        │
├─ exact_replay ─────────────────┤  fast_l1_exact  (expected = fast_l1_closed)
│       │                        │
├─ perturbed_replay ─────────────┤  fast_l1_perturbed  (THE QUESTION)
│       ↑                        │
│   ε applied once               │
│   activations ±0.02            │
```

The perturbation at t=0 creates an initial activation difference.
Through 2000 warmup steps, this difference:
- Propagates through synaptic transmission (weighted connections)
- Interacts with per-step noise (noise_strength=0.01)
- May amplify (chaotic sensitivity) or dampen (homeostatic pull)

At t=2000 (first decision point), the perturbed state may differ from
the closed_loop state at the same t. When the first event arrives and
triggers `apply_event_pair_phi(trace, phi)`:
- `phi` is identical (same event, same payload hash)
- `trace` may differ if the pre-warmup state divergence affected unit
  activations, which feed back into trace accumulation

If trace differs → dW differs → fast weight diverges.

---

## 5. Metrics

### 5.1 Primary

| Metric | Computation |
|--------|-------------|
| closed_vs_exact_fast_l1_delta | `l1(closed) - l1(exact)` |
| closed_vs_perturbed_fast_l1_delta | `l1(closed) - l1(perturbed)` |
| exact_vs_perturbed_fast_l1_delta | `l1(exact) - l1(perturbed)` |
| perturb_norm | `||ε||` = sqrt(mean(ε²)) — actual perturbation applied |
| replay_exactness | hash_mismatch count (must be 0 for all replay arms) |

### 5.2 Secondary

| Metric | Computation |
|--------|-------------|
| per-region fast_l1 delta | L/R/M breakdown of perturbation effect |
| max_abs_weight | Explosion check |
| nan_count | Must be 0 |
| event_count per arm | Must match closed_loop |
| activation_divergence_at_warmup_end | L1 distance between closed and perturbed activations at t=2000 |
| trace_mass_at_first_event | trace L1 at first event arrival in perturbed vs exact |

---

## 6. Pass/Fail Criteria

### 6.1 Hard Protocol

| # | Criterion | Threshold |
|---|-----------|-----------|
| P1 | No NaN | 0 |
| P2 | No explosion | max_abs_weight < 10.0 |
| P3 | Replay exactness (both replay arms) | hash_mismatch = 0 |
| P4 | Event count match | exact = perturbed = closed |
| P5 | 9C ON, 9D OFF confirmed | assert |
| P6 | Perturbation applied exactly once | code review |

### 6.2 Scientific Signal

| Outcome | Interpretation |
|---------|---------------|
| exact = closed AND perturbed ≠ closed | **POSITIVE.** Fast layer amplifies state difference. Mirror confirmed, crack visible. Proceed to characterize. |
| exact = closed AND perturbed ≈ closed | **NEGATIVE.** Perturbation dampened out or 9C pipeline is event-log-dominant. Fast layer does not carry state-context signal at this perturbation magnitude. |
| exact ≠ closed | **PROTOCOL FAILURE.** Exact replay should be bit-identical. Re-run with debug. |
| perturbed diverges in one seed only | **PARTIAL.** Seed-dependent sensitivity. Report per-seed, don't average. |

### 6.3 Perturbation Magnitude Sanity

- If `activation_divergence_at_warmup_end` ≈ 0: perturbation dampened out
  completely during warmup. ε=0.02 may be too small for 2000-step warmup.
  Record, do not tune. If both seeds show this, Scheme A1 (noise warmup)
  may be needed.
- If `activation_divergence_at_warmup_end` is large (e.g., > 0.1 mean L1):
  perturbation amplified significantly. The system is sensitive to initial
  conditions — this is itself an interesting result.

---

## 7. Interpretation Rules (Locked Before Run)

1. **If exact = closed and perturbed ≠ closed:** 10A.2 negative was a
   mirror-design artifact. Fast layer CAN carry state-context signal.
   Scheme E becomes the primary replay control for 10A.3.

2. **If exact = closed and perturbed ≈ closed:** The 9C fast plasticity
   pipeline is event-log-dominant at this timescale. State context does
   not enter fast weight. This would redirect to:
   - Larger perturbation (10A.2B.1B, with ε = 0.05, as separate variant)
   - Divergent warmup (10A.2B.2, Scheme A1)
   - Or accept that fast layer is state-context-insensitive and move to
     10A.3 with redesigned expectations

3. **If exact ≠ closed:** Protocol bug. Do not interpret perturbed result.
   Debug and re-run.

4. **No post-hoc ε tuning.** If ε=0.02 is too small, that is reported as
   a finding, and a new variant (10A.2B.1B with ε=0.05) is registered
   separately. The original 10A.2B.1 with ε=0.02 is not overwritten.

---

## 8. Runtime Estimate

| Arm | Per-seed |
|-----|----------|
| closed_loop | ~1.5 min |
| exact_replay | ~1.5 min |
| perturbed_replay | ~1.5 min |
| no_event (optional) | ~1.5 min |

- 3 arms × 2 seeds ≈ **~9 min** (without no_event)
- 4 arms × 2 seeds ≈ **~12 min** (with no_event)
- Local allowed

---

## 9. Output Artifacts

| Artifact | Path |
|----------|------|
| Event logs | `results/phase10A2B1_{arm}_seed{seed}_events.csv` |
| Summary CSV | `results/phase10A2B1_summary.csv` |
| Summary JSON | `results/phase10A2B1_summary.json` |
| Smoke notes | `docs/phase10A2B1_perturbed_replay_smoke_notes.md` |

---

## 10. Relationship to 10A.2B Scheme Hierarchy

```
10A.2B redesign
  ├── Scheme E: perturbed initial state  ← 10A.2B.1 (THIS DOCUMENT)
  ├── Scheme A1: divergent warmup       ← 10A.2B.2 (if E fails)
  ├── Scheme B: yoked cross-seed        ← 10A.2B.3 (diagnostic)
  └── 10A.2B.4: choose primary for 10A.3
```

---

## 11. Boundary

- 10A.2 is a CLEAN NEGATIVE — not challenged, not overwritten.
- This is Scheme E smoke only — not a full validation.
- ε = 0.02 is frozen — no post-hoc tuning.
- Scheduler θ is frozen (10A.0).
- 9C ON, 9D OFF.
- No entry to 10A.3.
- No digital-life / consciousness / personhood claim.
