# Phase 10F Step 2 — Trace/Phi Support Capture Design

**Date:** 2026-05-21
**Status:** Design only. No implementation. No runner change. No mechanism change.
**Blocked by:** 10F Step 1 verdict = proxy_phi_support_insufficient (commit 7948650)

---

## One-line framing

> Step 1 excluded the dense `phi_conn` proxy.
> Step 2 captures the true 9C support factors: `trace[src]` and `phi[tgt]`.

Not "does phi_conn predict support" — "does trace[src] × phi[tgt] exactly define support."

---

## Background

10F Step 1 read the existing 10E.1B event-level CSV and found:

- `tag_dW_match_rate = 1.0`
- `phi_proxy_dW_match_rate = 0.00569`
- `phi_proxy_false_positive_rate = 0.99431`
- `phi_proxy_false_negative_rate = 0.0`
- `phi_proxy_positive_rate = 1.0`
- `exact_phi_tgt_available = False`
- `trace_src_available = False`

Interpretation:

- tag support equals dW support, as expected from `tag_cache += abs(dW)`
- recorded `phi_conn` is too dense to explain sparse dW support
- existing CSV does not contain true `phi[tgt]` or `trace[src]`
- Step 2 must capture the real 9C support terms

9C formula from `aniva/core/plasticity_event_pair.py`:

```python
raw[i] = trace[src_i] * phi[tgt_i]
dW[i] = raw[i] * scale
```

Target identity:

```text
dW_support == (trace[src] != 0 AND phi[tgt] != 0)
```

---

## Goal

Design a read-only instrumentation runner that captures, for each event-pair
update, the true support factors:

- `trace_src`
- `phi_tgt`
- `raw = trace_src * phi_tgt`
- `dW`
- `tag_delta`

No mechanisms are changed. The runner snapshots and recomputes diagnostics
around the existing 9C update.

---

## Recommended runner

Create later, not now:

```text
aniva/experiments/exp10F2_trace_phi_support_capture.py
```

This design does not implement it yet.

---

## Fixed protocol

Reuse 10E.1B parameters:

- seeds: 42, 77, 123, 999
- total_steps = 7500
- warmup_end = 2000
- decision_interval = 250
- historical_context_enabled = True
- historical_context_tau = 10000.0
- historical_context_clip = True
- warmup weights frozen
- 9C/9D enabled after warmup, disabled during warmup
- exact replay mirror retained if applicable

Arms:

1. closed_loop
2. exact_replay
3. divergent_warmup_replay

---

## Capture point

Immediately before `core.apply_event_pair_phi(phi)`:

```python
trace_pre = core._event_trace.copy()
h_pre = core._historical_context_trace.copy()
tag_pre = core._tag_cache.copy()
w_pre = core._weight_cache.copy()
```

Then call the unmodified mechanism:

```python
core.apply_event_pair_phi(phi)
```

Immediately after:

```python
w_after = core._weight_cache.copy()
tag_after = core._tag_cache.copy()
dW = w_after - w_pre
tag_delta = tag_after - tag_pre
```

For each connection i:

```python
src = source_indices[i]
tgt = target_indices[i]
trace_src = trace_pre[src]
phi_tgt = phi[tgt]
raw = trace_src * phi_tgt
```

This captures the exact inputs to 9C without modifying 9C.

---

## Event-level output schema

Output:

```text
results/phase10F2_trace_phi_support_events.csv
```

Fields:

- seed
- arm
- event_index
- event_step
- event_type
- connection_id
- src
- tgt
- src_region
- tgt_region
- subgraph
- trace_src
- phi_tgt
- raw
- event_pair_dW
- tag_before
- tag_after
- tag_delta
- trace_src_positive
- phi_tgt_positive
- raw_support
- dW_support
- tag_support
- h_src
- h_tgt
- h_conn
- baseline_weight_abs

---

## Summary output schema

Outputs:

```text
results/phase10F2_trace_phi_support_summary.csv
results/phase10F2_trace_phi_support_summary.json
```

Summary grouped by:

- seed
- arm
- event_type
- subgraph

Fields:

- n_connections
- trace_src_positive_rate
- phi_tgt_positive_rate
- raw_support_rate
- dW_support_rate
- tag_support_rate
- raw_vs_trace_phi_mismatch_count
- raw_vs_dW_mismatch_count
- dW_vs_tag_mismatch_count
- trace_src_l1
- phi_tgt_l1
- raw_l1
- dW_l1
- tag_delta_l1
- raw_l1_to_dW_l1_scale
- corr_h_trace_src
- corr_h_phi_tgt
- support_geometry_verdict

Cross-seed JSON fields:

- all_raw_vs_trace_phi_mismatch_count
- all_raw_vs_dW_mismatch_count
- all_dW_vs_tag_mismatch_count
- by_seed_trace_src_positive_rate
- by_seed_phi_tgt_positive_rate
- by_event_type_phi_tgt_positive_rate
- R_event_phi_tgt_rate_vs_L
- seed123_999_trace_distribution_vs_42_77
- seed123_999_phi_distribution_vs_42_77
- final_verdict

---

## Identity checks

### 1. Raw support identity

```text
raw_support == (trace_src_positive AND phi_tgt_positive)
```

Expected: exact match.

If this fails, inspect the diagnostic recomputation or numerical threshold.

### 2. Raw support vs dW support

```text
raw_support == dW_support
```

Expected: exact match unless gate=0, raw_l1=0, clipping, or thresholding changes support.

If mismatch exists:
- inspect gate
- inspect raw_l1
- inspect scaling
- inspect clipping
- inspect eps threshold

### 3. dW support vs tag support

```text
dW_support == tag_support
```

Expected: exact match because `produce_tags(tag_cache, dW)` accumulates `abs(dW)`.

If mismatch exists:
- inspect tag accumulation
- inspect tag decay timing
- inspect event capture point

### 4. Scale consistency

For each event:

```text
dW_l1 / raw_l1 == target_l1 * gate / raw_l1
```

At summary level:

```text
dW_l1 ≈ target_l1 * gate
```

This verifies that support-preserving scaling is working as expected.

---

## Decision rules

| condition | verdict | next step |
|---|---|---|
| all three identities hold | trace_phi_support_identity_confirmed | analyze support geometry by trace/phi distribution |
| raw_support != trace×phi | raw_computation_or_threshold_issue | inspect diagnostic recomputation / eps |
| raw_support == trace×phi but dW_support differs | scaling_gate_or_clipping_support_change | inspect 9C gate, scale, clip, raw_l1 |
| dW_support != tag_support | tag_accumulation_mismatch | inspect 9D produce_tags / capture timing |
| identities hold and R-event null maps to phi_tgt support | event_phi_geometry_root | explain R collapse via stimulus support geometry |
| identities hold and seed123/999 split maps to trace_src support | seed_trace_geometry_root | explain seed split via trace geometry |
| h strongly correlates with trace_src | h_may_be_slow_trace_proxy | h[u] may be a slow proxy, not direct cause |
| h does not correlate with trace_src or phi_tgt | h_not_upstream_of_9C_support | current h descriptor is not upstream of support |

---

## Interpretation rules

Do not claim phi dominance from `phi_tgt` alone. 9C support is an intersection:

```text
trace[src] AND phi[tgt]
```

If phi_tgt support is broad but trace_src is sparse, trace geometry is the gate.
If trace_src support is broad but phi_tgt is sparse, phi geometry is the gate.
If both are sparse, support is true intersection geometry.

---

## Boundaries

- No mechanism changes.
- No 9C formula changes.
- No tag rule changes.
- No 9D changes.
- No h[u] changes.
- No 10E.2.
- No mechanism proposal.
- No digital life / consciousness / personhood claim.

This is a diagnostic capture design only.
