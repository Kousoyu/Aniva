# Phase 10F Step 3 — Support Subgraph Decomposition Notes

**Date:** 2026-05-24
**Status:** trace_phi_support_geometry_explains_tag_formation__h_not_upstream
**Analyzer commit:** f5ee873
**Results:** results/phase10F3_support_subgraph_decomposition_summary.csv, results/phase10F3_support_subgraph_decomposition_summary.json

---

## 1. Positioning

10F Step 3 was an offline analyzer.

- Input: `results/phase10F2_trace_phi_support_events.csv` on ECS
- No simulation rerun
- No 9C change
- No 9D change
- No tag rule change
- No h[u] change

Step 3 uses the Step 2 event-level capture to decompose the already-confirmed
support identity by seed, event type, and subgraph.

---

## 2. Result headline

**overall_root_verdict:**

```text
trace_phi_support_geometry_explains_tag_formation__h_not_upstream
```

**support_identity_status_from_step2:**

```text
trace_phi_support_identity_confirmed
```

**whether_10E2_allowed:**

```text
false
```

Interpretation:

```text
tag formation support = dW support = raw support = trace[src] × phi[tgt] support
```

Step 3 shows that the distribution of this support is a geometry problem:
subgraph, event type, and seed topology determine where trace and phi meet.

---

## 3. LL special case

**ll_special_case_confirmed:** `True`

LL is a topology/support special case. Its earlier h_tag_ratio anomaly can be
explained as downstream of support geometry rather than requiring a new h[u]
mechanism.

This does not justify an h gate or tag rule change. LL should be treated as a
subgraph topology case in future diagnostics.

---

## 4. RR seed split

**rr_seed_split_type:** `RR_phi_limited_seed_split`

The RR seed split mainly comes from the phi_tgt side, not h[u]. The anchor case:

| seed | subgraph | trace_rate | phi_rate | support_rate |
|---|---|---:|---:|---:|
| 123 | RR | 0.1209 | 0.0841 | 0.010216 |
| 999 | RR | 0.0609 | 0.0150 | 0.000819 |

seed123 RR has enough trace and phi overlap to produce high support. seed999 RR
has much weaker phi_tgt coverage and near-zero support. This is a local
trace×phi intersection split, not a global seed-level h effect.

---

## 5. R-event collapse

R-event collapse is not a uniform R stimulus coverage shortage.

seed42/77 and seed123/999 show different L/R phi/support patterns. Therefore
the more accurate interpretation is:

```text
R-event collapse = seed-dependent trace×phi intersection geometry
```

Do not reduce it to "R phi is always low." It is local to seed/event/subgraph
geometry.

---

## 6. h relationship

**h_upstream_status:** `h_not_upstream_of_9C_support`

Across Step 3, h correlations with trace_src, phi_tgt, and support remain weak.
Current h[u] is not a direct upstream variable for 9C support.

Therefore:

- Do not enter h-gate design.
- Do not modify tag rule.
- Do not proceed to 10E.2.
- Do not claim h[u] is the causal source of tag formation support.

---

## 7. Final decision

The Phase 10E/10F support-path diagnostic chain is closed.

What is now established:

1. 10E.1B: global novelty rule failed four-seed validation.
2. 10E.1C/1D: h[u] and phi proxies were insufficient independent predictors.
3. 10F Step 1: phi_conn proxy was too dense and could not explain dW support.
4. 10F Step 2: true support identity was confirmed exactly.
5. 10F Step 3: support distribution is explained by trace×phi geometry, not h[u] upstream causation.

Do not proceed to 10E.2.
Do not modify 9C, 9D, tag rule, or h[u].

If continuing later, the next artifact should be a high-level synthesis / route
decision note, not mechanism implementation.
