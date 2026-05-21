# Phase 10F — Event-Pair Plasticity Support Geometry Design

**Date:** 2026-05-21
**Status:** Design only. No implementation. No runner change. No mechanism change.
**Blocked by:** 10E.1D verdict = tautological_dW_predictor (commit 84da374)

---

## One-line framing

> 10E showed that tag_presence ⟺ abs(dW) > 0, which is definitional.
> 10F asks: what determines the support of nonzero dW in 9C?

Not "who predicts tag" — "why does the plasticity fire here and not there."

---

## Background

From reading `aniva/core/plasticity_event_pair.py`:

```python
raw[i] = trace[src_i] * phi[tgt_i]
raw_l1 = sum(abs(raw))
scale = target_l1 * gate / raw_l1   # if raw_l1 > 0 and gate > 0
dW[i] = raw[i] * scale
```

Therefore:

```
dW[i] != 0  ⟺  trace[src_i] != 0  AND  phi[tgt_i] != 0
```

The support of nonzero dW is exactly the set of connections where both
source trace and target phi are nonzero. This is the upstream gate.

From `produce_tags`:
```python
tag_cache += abs(dW)
```

So `tag_presence[i] = 1` iff `trace[src_i] != 0 AND phi[tgt_i] != 0`.

The 10E diagnostic chain correctly identified that h[u] and phi_conn are
not independent predictors. The real question is now:

1. **Trace geometry**: which source units have nonzero trace at event time?
2. **Phi geometry**: which target units receive nonzero phi from L/R stimulus?
3. **Intersection**: which connections have both?

---

## Core question

What determines the support of nonzero event-pair dW in 9C, and does this
support geometry explain the seed/event-type/subgraph patterns seen in 10E.1B–1D?

---

## Diagnostic targets

### 1. Support identity verification

For each event in the 10E.1B events CSV, verify:

```
dW_support[i] = (abs(event_pair_dW[i]) > eps)
trace_src_positive[i] = (trace[src_i] > eps)   # not in CSV — must be inferred
phi_tgt_positive[i] = (phi_conn[i] > eps)       # phi_conn is in CSV
```

**Note:** `trace[src_i]` at event time is not stored in the 10E.1B events CSV.
It must be re-derived or inferred. Two options:

**Option A (offline inference):** `dW_support[i] = 1` iff `phi_conn[i] > eps`.
Since `raw[i] = trace[src_i] * phi[tgt_i]`, and if trace is nonzero for all
active sources, then `dW_support ≈ phi_tgt_positive`. This can be tested
against the existing CSV.

**Option B (new runner):** Instrument the runner to capture `trace[src_i]`
at event time alongside the existing fields. This requires a new runner pass
but no mechanism change.

Start with Option A (offline). If phi_tgt_positive explains dW_support
completely, Option B is not needed.

### 2. Phi support geometry

For each seed × event_type × subgraph:
- `phi_tgt_positive_rate`: fraction of connections where `phi_conn > eps`
- `phi_mass_by_region`: total phi mass in L / M / R regions
- `phi_tgt_mean_by_subgraph`: mean phi[tgt] per subgraph

Key question: does R-event phi support differ from L-event phi support in
a way that explains the R-event null in 10E.1B/1C?

From the 10E.1C phi_mass data:
- seed999 R-events: phi_mass=2839 vs L-events: phi_mass=14424
- seed77 R-events: phi_mass=8086 vs L-events: phi_mass=14657

R-events have lower phi mass in most seeds. This may directly explain
the R-event null: fewer connections have nonzero phi[tgt] under R stimulus.

### 3. Trace geometry (requires new runner pass)

`trace[src_i]` at event time is the event-pair trace accumulated since the
last event. It decays exponentially between events.

Key questions:
- Which source units have nonzero trace at event time?
- Does trace source distribution differ between seeds 42/77 and 123/999?
- Does trace source distribution differ between L and R events?

If trace is nonzero for all units (because events are frequent enough that
trace never fully decays), then `dW_support ≈ phi_tgt_positive` and
Option A is sufficient.

If trace is sparse (some sources have near-zero trace), then trace geometry
is a second gate on top of phi geometry.

### 4. h[u] relationship to trace and phi

h[u] is a slow EMA of activation (τ=10000). Trace is a fast EMA of activation
(τ=event_pair_trace_tau, much shorter). They are related but not identical.

Check:
- `corr(h[src], trace[src])` at event time
- `corr(h[tgt], phi[tgt])` at event time

If h[src] correlates with trace[src]: h is a slow proxy for trace, and the
10E novelty signal was a lagged version of trace geometry.
If h does not correlate with trace: h is not upstream of dW support.

### 5. Seed topology: why do 123/999 differ from 42/77?

The seed determines the initial network topology (connection pattern, weights,
unit positions). This affects:
- Which units are in L/M/R regions
- Which connections exist (src_region × tgt_region distribution)
- Initial weight distribution

Check whether seed123/999 have different:
- L/R region unit counts
- LL/RR/RL/LR connection counts
- phi mass distribution under L/R stimulus (depends on unit positions)

If seed123/999 have more R-region units receiving L-stimulus phi, the
phi geometry is different and explains the inversion.

---

## Output schema

### Offline (Option A) — from existing 10E.1B events CSV

Summary CSV grouped by: seed × arm × event_type × subgraph

Fields:
- n_connections
- phi_tgt_positive_rate (phi_conn > eps)
- phi_tgt_mean
- phi_tgt_mean_tagged
- phi_tgt_mean_untagged
- phi_tag_ratio (mean_phi_tagged / mean_phi_untagged)
- dW_support_rate (abs(event_pair_dW) > eps)
- phi_vs_dW_support_match_rate
- tag_vs_dW_support_match_rate
- phi_mass_total
- dW_l1_total
- tag_delta_l1_total
- support_geometry_verdict

### New runner pass (Option B) — if needed

Additional fields per connection per event:
- trace_src (event-pair trace at source unit, before phi addition)
- trace_src_positive (trace_src > eps)
- raw_ij (trace_src * phi_tgt)
- raw_positive (abs(raw_ij) > eps)
- raw_vs_dW_match (raw_positive == dW_support)

---

## Decision rules

| finding | verdict | next step |
|---|---|---|
| phi_tgt_positive_rate explains dW_support_rate (match > 0.99) | phi_geometry_root | R-event null is phi coverage; seed split is phi mass distribution |
| phi_tgt_positive_rate does not explain dW_support (mismatch > 0.01) | trace_geometry_needed | Run Option B to capture trace[src] |
| R-event phi_mass < L-event phi_mass in ≥3/4 seeds | R_event_phi_coverage_deficit | R stimulus covers fewer connections; R-event null is structural |
| seed123/999 phi_mass distribution differs from seed42/77 | seed_phi_geometry_split | Seed topology determines phi coverage; inversion is phi-driven |
| h[src] correlates with trace[src] (r > 0.5) | h_is_trace_proxy | h[u] is a slow version of trace; 10E novelty was lagged trace signal |
| h does not correlate with trace | h_not_upstream | h descriptor is not upstream of 9C support; redesign needed |

---

## Implementation plan

**Step 1 (offline, no new runner):**
Implement `analyze10F_support_geometry.py` reading 10E.1B events CSV.
Verify phi_tgt_positive_rate vs dW_support_rate match.
Compute phi mass by event_type and subgraph.
Check whether R-event phi coverage explains R-event null.

**Step 2 (new runner pass, if needed):**
Add `trace_src` capture to the runner (read-only, no mechanism change).
Re-run 4 seeds to get trace geometry.
Check trace × phi intersection vs dW support.

**Step 3 (h-trace correlation):**
Compute corr(h[src], trace[src]) at event time.
Determine whether h is a slow proxy for trace.

---

## Boundaries

- No mechanism changes.
- No tag rule changes.
- No event_pair_plasticity changes.
- No consolidation changes.
- No τ tuning.
- No h[u] redesign.
- No novelty gate.
- No capture redesign.
- No claim of digital life / consciousness / personhood.
- 10F is diagnostic; it produces a verdict about the support geometry,
  not a mechanism proposal.
