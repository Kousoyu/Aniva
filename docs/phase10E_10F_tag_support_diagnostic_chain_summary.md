# Phase 10E/10F — Tag Support Diagnostic Chain Summary

**Date:** 2026-05-24
**Status:** diagnostic_branch_closed
**Latest results commit:** 21def7a

---

## One-line summary

10E asked whether historical context h[u] predicts tag formation. 10F showed
that tag formation support is determined by 9C `trace[src] × phi[tgt]` support
geometry, and current h[u] is not a direct upstream driver.

---

## What this document is

This is the closing summary for the Phase 10E → 10F tag-support diagnostic
branch.

It is not:

- a mechanism design
- 10E.2
- 10G
- a proposal to modify 9C
- a proposal to modify 9D
- a proposal to modify the tag rule
- a proposal to modify h[u]

---

## Evidence chain

### 10E.1 — two-seed weak positive preliminary

Question: does historical context h[u] predict tag formation?

Result:

- 2-seed weak positive preliminary
- novelty_factor appeared weakly predictive
- protocol clean after exact-replay tag hash hardening
- effect was small and seed/event-type unstable

Interpretation:

The signal was not strong enough for mechanism design. It justified four-seed
validation, not 10E.2.

---

### 10E.1B — four-seed validation

Result:

- four-seed validation failed
- verdict: `unstable_event_type_confound`
- seed42/77: weak pass / borderline pass
- seed123/999: severe inverse
- R-events unstable/null in multiple seeds
- protocol remained clean

Interpretation:

Global novelty_factor did not validate. The failure was not a protocol problem;
it was a real seed/event-type split.

---

### 10E.1C — event-type / topology diagnostic

Result:

- offline event-type/topology diagnostic
- verdict: `null_for_current_h_descriptor`
- global novelty descriptor was insufficient
- split was local/subgraph/event-type-dependent, not global
- LL / RR geometry began to emerge as key structure

Interpretation:

The problem was not simply "history has no effect." The correct conclusion was
that current global h[u]/novelty_factor was the wrong descriptor for tag
formation support.

---

### 10E.1D — subgraph / phi diagnostic

Result:

- subgraph/phi diagnostic
- `abs_dW` predictor gave AUC=1.0
- this was reinterpreted as tautological, not discovery

Why:

```text
tag_cache += abs(dW)
tag_presence == 1 iff abs(dW) > 0
```

Interpretation:

Predicting tag from dW is circular. The question moved upstream from tag
formation to event-pair dW support.

---

### 10F Step 1 — support geometry proxy audit

Result:

- proxy phi audit
- `tag_dW_match_rate = 1.0`
- `phi_proxy_dW_match_rate = 0.00569`
- `phi_proxy_positive_rate = 1.0`
- verdict: `proxy_phi_support_insufficient`

Interpretation:

`phi_conn` in the earlier CSV was a dense proxy, not true `phi[tgt]` support.
It could not explain sparse dW support. Step 2 was required to capture true
`trace[src]` and true `phi[tgt]`.

---

### 10F Step 2 — trace/phi support capture

Result:

- captured true `trace[src]`, true `phi[tgt]`, raw, dW, and tag_delta
- final_verdict: `trace_phi_support_identity_confirmed`
- `raw_vs_trace_phi_mismatch_count = 0`
- `raw_vs_dW_mismatch_count = 0`
- `dW_vs_tag_mismatch_count = 0`

Support identity:

```text
tag_support = dW_support = raw_support = trace[src] × phi[tgt] support
```

Interpretation:

The identity question closed. Tag formation support is exactly the support of
the 9C event-pair raw eligibility product.

---

### 10F Step 3 — support subgraph decomposition

Result:

- support subgraph decomposition
- overall_root_verdict:

```text
trace_phi_support_geometry_explains_tag_formation__h_not_upstream
```

- `ll_special_case_confirmed = True`
- `rr_seed_split_type = RR_phi_limited_seed_split`
- `h_upstream_status = h_not_upstream_of_9C_support`
- `whether_10E2_allowed = false`

Interpretation:

The remaining structure is geometry:

- LL is a topology/support special case.
- RR seed split is primarily phi-limited.
- R-event collapse is seed-dependent trace×phi intersection geometry, not a
  universal R-stimulus coverage shortage.
- Current h[u] is not a direct upstream driver of 9C support.

---

## Final interpretation

The original 10E question was valid, but the target had to move upstream.

The diagnostic chain found three downstream traps:

1. `slow_delta` is downstream of tag_cache.
2. `tag_presence` is downstream of `abs(dW)`.
3. `dW_support` is downstream of `trace[src] × phi[tgt]`.

Therefore the true support-level explanation lives in 9C trace/phi geometry.

Current h[u] stores history, but in this chain it does not directly determine
9C support. It is not a sufficient upstream descriptor for tag formation.

Do not wire current h[u] into the tag rule or capture gate based on this
chain.

---

## What is closed

The following routes are closed by the current evidence:

- No 10E.2 mechanism design from current evidence.
- No novelty_factor tag rule.
- No h-gate.
- No tag-rule modification.
- No 9C modification.
- No 9D modification.
- No claim of digital life / consciousness / personhood.

This branch validates a diagnostic chain, not a new mechanism.

---

## What remains open

Open questions for future diagnostics:

- Could a different historical descriptor influence trace or phi indirectly?
- Could event-gated history, not background h[u], correlate with trace geometry?
- Could future work study topology-conditioned trace/phi formation?
- Could LL / RR special cases inform future topology-aware diagnostics?

These are future diagnostics, not immediate mechanism changes.

---

## Recommended next step

Stop this diagnostic branch here.

Do not enter 10E.2.

The next immediate action should be a project-level route decision, such as:

1. Phase 10 route synthesis,
2. Phase 11 planning,
3. or merge / PR cleanup if this branch is ready.

---

## Boundaries

This summary does not validate digital life.

This summary does not validate consciousness or personhood.

This summary validates a mechanistic diagnostic chain:

```text
tag support is trace×phi support geometry,
not direct h[u] history gating.
```
