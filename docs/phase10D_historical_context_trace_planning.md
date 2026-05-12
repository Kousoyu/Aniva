---
phase: 10D
title: Historical Context Trace
status: PLANNING
date: 2026-05-12
prerequisite: Phase 10C.2 CLEAN NEGATIVE
---

# Phase 10D — Historical Context Trace Planning

## Why We Are Here

Phase 10A–10C exhausted the "replay control" approach:

| Route | Test | Result |
|---|---|---|
| 10A (scalar) | slow_l1 differs across arms? | CLEAN NEGATIVE |
| 10C (per-connection) | capture diagnostics differ? | CLEAN NEGATIVE |

The conclusion from 10C.2 is structural, not parametric:

> The current consolidation pathway is **event-local**.
> `tag_cache` starts from zero at replay start.
> `event_trace` decays fast enough that warmup history is overwritten
> before the first capture fires.
> The system has no container that accumulates history across events.

Tweaking the gate formula or threshold will not fix this.
The input arrays themselves carry no history signal.

## Core Problem Statement

```
Current 9D only deposits "the tag at the moment of this event."
It does not preserve "what state history this individual lived through
before this event arrived."

Phase 10D introduces a slow-varying historical context trace:
a per-unit variable with a time constant much longer than event_trace,
capable of accumulating activation / energy / event influence
across the full run — including warmup.
```

## Proposed Mechanism: `historical_context_trace`

### What it is

A per-unit scalar `h[u]` that evolves continuously:

```
dh/dt = α · (x[u] - h[u])
```

where `x[u]` is a local signal (activation, energy, or a combination),
and `α` is a very small learning rate (τ_h >> τ_event_trace).

### Time constant target

- `event_trace` τ ≈ 100–500 steps (washes out in ~1000 steps)
- `historical_context_trace` τ_h ≈ 5000–20000 steps

At τ_h = 10000 steps, after 2000-step warmup the trace retains
~82% of warmup signal. After 7500 total steps it still carries
a weighted average of the full run history.

### What it tracks

Three candidate signals for `x[u]`:

| Option | Signal | Captures |
|---|---|---|
| A | activation `a[u]` | mean firing level over history |
| B | energy `e[u]` | metabolic load history |
| C | `a[u] · e[u]` | active-and-energized history |

Option A is simplest. Option C is most selective (only units that
were both active and energized leave a trace).

### How it enters consolidation

`h[u]` is **read-only** at capture time — it does not affect gate logic
or slow_weight transfer in Phase 10D.

It is added to the capture ledger as a diagnostic:

```
h_source = h[source_index]   # per-capture
h_target = h[target_index]
h_mean_at_capture = mean(h[source], h[target])
h_divergence_at_capture = |h_source - h_target|
```

This lets us answer: **does h[u] differ between closed_loop and
divergent_warmup_replay at capture time?**

If yes → h[u] is a viable history signal for future gate design.
If no → the signal choice or time constant needs adjustment.

## Experimental Design: Phase 10D.1 Smoke

### Structure

Same four-arm structure as 10A.2C / 10C.2:
- closed_loop
- exact_replay
- divergent_warmup_replay
- matched_warmup_control

### New outputs

Per-capture CSV adds:
- `h_source_mean` — mean h[u] over source units of tagged connections
- `h_target_mean` — mean h[u] over target units of tagged connections
- `h_weighted_mean` — tag-weighted mean of h[source] and h[target]
- `h_concentration` — HHI of h distribution over tagged connections
- `h_divergence_cl_vs_div` — computed post-hoc from arm comparison

### Success criterion

```
|h_weighted_mean(closed_loop) - h_weighted_mean(divergent_warmup_replay)|
> 0.01 · h_weighted_mean(closed_loop)
```

i.e., at least 1% relative difference in the history trace at capture time.

If this passes → h[u] carries warmup history into capture context.
This would be the first positive signal in Phase 10.

### Failure modes

| Failure | Diagnosis |
|---|---|
| h identical across arms | τ_h too short, or signal x[u] washes out |
| h nonzero but same | warmup divergence too small to leave trace |
| h differs but capture_count differs | gate is affected (not allowed in 10D.1) |

## Implementation Plan

### Phase 10D.1: Add `historical_context_trace` as read-only diagnostic

1. Add `historical_context_trace_enabled: bool = False` to `AnivaConfig`
2. Add `historical_context_tau: float = 10000.0` to `AnivaConfig`
3. Add `_h_trace: np.ndarray` to `LifeCore` (per-unit, initialized to 0)
4. Update `_h_trace` each step:
   ```python
   alpha = 1.0 / cfg.historical_context_tau
   self._h_trace += alpha * (self._activations - self._h_trace)
   ```
5. At capture time, add h-metrics to ledger (read-only, no gate change)
6. Write `exp10D1_historical_context_smoke.py` (10A.2C + h_trace)

### Phase 10D.2: Validate signal

Run smoke with seeds 42, 77.
Check whether h_weighted_mean differs between closed_loop and divergent.

### Phase 10D.3 (conditional): Gate candidate

If 10D.1 shows signal → design a gate that incorporates h[u].
If 10D.1 shows no signal → adjust τ_h or signal choice, re-run.

## What Phase 10D Does NOT Do

- Does not change the 9D gate formula
- Does not change slow_weight transfer
- Does not change capture signal
- Does not use h[u] to modify any existing behavior
- Does not require changing the experimental protocol

## Connection to Aniva Vision

The `historical_context_trace` is the first step toward:

> "An individual that has lived through different experiences
> should consolidate the same event differently."

Currently Aniva's consolidation is blind to history.
Phase 10D gives it a slow memory of where it has been —
not as explicit stored events, but as a continuous residue
of activation and energy history, like a thermal trace
left by the path the system walked.

This is closer to the biological notion of neuromodulatory state:
a slow background signal that biases how new experiences are encoded,
shaped by the cumulative weight of past experience.
