# Phase 10F Step 3 — Support Subgraph Decomposition Design

**Date:** 2026-05-24
**Status:** Design only. No implementation. No runner change. No mechanism change.
**Blocked by:** 10F Step 2 verdict = trace_phi_support_identity_confirmed (commit 87af1bc)

---

## One-line framing

> Step 2 proved support identity: tag = dW = raw = trace[src] × phi[tgt].
> Step 3 asks where that support geometry concentrates, and why it splits by seed/event/subgraph.

Not "what defines support" — "which subgraphs make trace and phi meet or miss."

---

## Background

10F Step 2 confirmed all identities with 0 mismatches:

```text
raw_support == trace_src_positive AND phi_tgt_positive
raw_support == dW_support
dW_support == tag_support
```

Therefore:

```text
tag formation support = trace[src] × phi[tgt] support
```

Remaining questions are geometric, not definitional:

- Why does LL have h_tag_ratio > 1 in 4/4 seeds?
- Why does RR split strongly between seed123 and seed999?
- Why do R-events collapse in some seeds but not others?
- Why does h[u] weakly correlate with trace/phi overall?

Step 3 does not need to rerun simulation. It should use:

```text
results/phase10F2_trace_phi_support_events.csv
```

If the file is not local, pull it from ECS but do not commit it.

---

## Core question

Which subgraphs and event types explain trace×phi support geometry splits,
especially:

- LL 4/4 h_tag_ratio > 1
- RR seed123 high support vs seed999 near-zero support
- R-event collapse in seed77/123/999
- weak h correlation with trace/phi

---

## Proposed analyzer

Create later, not now:

```text
aniva/experiments/analyze10F3_support_subgraph_decomposition.py
```

Input:

```text
results/phase10F2_trace_phi_support_events.csv
```

Outputs:

```text
results/phase10F3_support_subgraph_decomposition_summary.csv
results/phase10F3_support_subgraph_decomposition_summary.json
```

---

## Grouping axes

Analyze at these granularities:

1. seed × arm × event_type × subgraph
2. seed × arm × event_type × src_region × tgt_region
3. seed × arm × subgraph
4. seed-family group:
   - family_A = seed42/77
   - family_B = seed123/999

Use closed_loop as the primary interpretation arm. exact_replay remains protocol
mirror. divergent_warmup_replay is informative for trace trajectory dependence.

---

## Metrics

Per group:

- n_connections
- trace_src_positive_rate
- phi_tgt_positive_rate
- support_rate
- trace_l1
- phi_l1
- raw_l1
- dW_l1
- tag_delta_l1
- support_over_trace_phi_expected
- trace_phi_overlap_index
- support_concentration_by_subgraph
- h_mean_supported
- h_mean_unsupported
- h_support_ratio
- corr_h_trace_src
- corr_h_phi_tgt
- corr_h_support
- LL_special_case_flag
- RR_seed_split_flag
- R_event_collapse_flag

Suggested derived metrics:

```text
support_expected_independent = trace_rate * phi_rate
support_over_trace_phi_expected = support_rate / support_expected_independent
trace_phi_overlap_index = support_rate / min(trace_rate, phi_rate)
```

Interpretation:

- `support_over_trace_phi_expected > 1`: trace and phi overlap more than random.
- `support_over_trace_phi_expected < 1`: trace and phi avoid each other.
- `trace_phi_overlap_index` near 1: smaller support set is almost fully contained in larger.
- `trace_phi_overlap_index` near 0: trace and phi rarely meet.

---

## Diagnostic 1 — LL special case

LL previously showed h_tag_ratio > 1 in 4/4 seeds.

For LL, compare across all seeds:

- trace_src_positive_rate
- phi_tgt_positive_rate
- support_rate
- overlap index
- h_mean_supported vs h_mean_unsupported
- corr_h_trace_src
- corr_h_phi_tgt
- corr_h_support

Question:

Is LL inversion caused by:

1. high trace support,
2. high phi support,
3. unusually high trace×phi overlap,
4. h being high in supported LL connections,
5. or unrelated h topology?

If LL support is fully explained by trace×phi while h is weakly related,
LL is a topology support special case, not an h mechanism.

---

## Diagnostic 2 — RR seed split

Known anchor:

| seed | subgraph | trace_rate | phi_rate | support_rate |
|---|---|---:|---:|---:|
| 123 | RR | 0.1209 | 0.0841 | 0.010216 |
| 999 | RR | 0.0609 | 0.0150 | 0.000819 |

Compare seed123 RR vs seed999 RR:

- trace_rate
- phi_rate
- support_rate
- support_over_trace_phi_expected
- trace_phi_overlap_index
- h_mean_supported / unsupported
- event_type split inside RR

Classify the split:

- trace-limited: seed999 trace_rate much lower
- phi-limited: seed999 phi_rate much lower
- overlap-limited: trace/phi rates similar but support lower
- mixed: trace and phi both lower

The current expectation is mixed trace+phi limitation for seed999 RR, with phi
especially low.

---

## Diagnostic 3 — R-event collapse

For each seed, compare L vs R:

- trace_rate
- phi_rate
- support_rate
- overlap index
- support concentration by subgraph

Classify:

- `phi_limited`: R phi_rate << L phi_rate
- `trace_limited`: R trace_rate << L trace_rate
- `overlap_limited`: trace/phi rates similar but support lower
- `not_collapsed`: R support comparable or higher than L

Expected from Step 2:

- seed42: R not collapsed; R support higher than L
- seed77: R roughly comparable to L
- seed123: R lower than L, both trace and phi lower
- seed999: R much lower than L, phi-limited

---

## Diagnostic 4 — h relationship

h[u] is only relevant if it predicts trace_src, phi_tgt, or support.

For each seed × event_type × subgraph:

- corr_h_trace_src
- corr_h_phi_tgt
- corr_h_support
- h_support_ratio = mean_h_supported / mean_h_unsupported

Rules:

- If corr_h_* remains weak across subgraphs, h is not upstream of 9C support.
- If some subgraphs show strong h→trace or h→phi relation, mark them as
  `candidate_h_indirect_support_path`, but do not propose a mechanism yet.

---

## Output schema

Summary CSV grouped by seed × arm × event_type × subgraph:

- seed
- arm
- event_type
- subgraph
- n_connections
- trace_src_positive_rate
- phi_tgt_positive_rate
- support_rate
- trace_l1
- phi_l1
- raw_l1
- dW_l1
- tag_delta_l1
- support_over_trace_phi_expected
- trace_phi_overlap_index
- support_concentration_by_subgraph
- h_mean_supported
- h_mean_unsupported
- h_support_ratio
- corr_h_trace_src
- corr_h_phi_tgt
- corr_h_support
- LL_special_case_flag
- RR_seed_split_flag
- R_event_collapse_flag
- support_decomposition_verdict

Cross-seed JSON:

- LL_summary
- RR_seed123_vs_999
- R_event_collapse_classification
- h_correlation_summary
- support_concentration_summary
- final_verdict

---

## Decision rules

| finding | verdict |
|---|---|
| RR split maps mostly to phi_tgt rate | RR_phi_limited_seed_split |
| RR split maps mostly to trace_src rate | RR_trace_limited_seed_split |
| trace/phi rates similar but support differs | RR_overlap_geometry_split |
| trace and phi both lower in low-support seed | RR_mixed_trace_phi_limited_seed_split |
| LL high h is fully explained by trace×phi support | LL_topology_support_special_case |
| h correlations remain weak | h_not_upstream_of_9C_support |
| subgraphs show strong h→trace or h→phi relation | candidate_h_indirect_support_path |
| R collapse maps to phi_tgt shortage | R_event_phi_limited |
| R collapse maps to trace_src shortage | R_event_trace_limited |
| R collapse maps to low overlap despite similar trace/phi | R_event_overlap_limited |

Final verdict should be a combined label, e.g.:

```text
trace_phi_support_geometry_explains_tag_formation__h_not_upstream
```

---

## Boundaries

- No 9C changes.
- No tag rule changes.
- No 9D changes.
- No h mechanism changes.
- No 10E.2.
- No mechanism proposal.
- No digital life / consciousness / personhood claim.

Step 3 is an offline decomposition of already captured trace×phi support.
