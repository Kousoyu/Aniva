# Phase 10F Step 2 — Trace/Phi Support Capture Notes

**Date:** 2026-05-24
**Status:** trace_phi_support_identity_confirmed
**Runner commit:** d7e7c29
**Results:** results/phase10F2_trace_phi_support_summary.csv, results/phase10F2_trace_phi_support_summary.json

---

## 1. Positioning

10F Step 2 was a read-only instrumentation rerun.

Captured true 9C support inputs at event-pair update time:

- `trace_src = trace_pre[src]`
- `phi_tgt = phi[tgt]`
- `raw = trace_src * phi_tgt`
- `dW = weight_after - weight_before`
- `tag_delta = tag_after - tag_before`

No mechanism was changed:

- No 9C formula change
- No 9D change
- No tag rule change
- No h[u] change

---

## 2. Identity result

**Final verdict:** `trace_phi_support_identity_confirmed`

Global mismatch counts:

| identity check | mismatch count |
|---|---:|
| raw_support == trace_src_positive AND phi_tgt_positive | 0 |
| raw_support == dW_support | 0 |
| dW_support == tag_support | 0 |

All three identities hold exactly.

Therefore:

```text
tag_support = dW_support = raw_support = trace[src] × phi[tgt] support
```

This closes the identity question. Tag formation support is exactly the support
of the 9C event-pair raw eligibility product.

---

## 3. L/R result

R-event collapse is not explained by uniform R phi_tgt coverage shortage.

Closed_loop event-type rates:

| seed | event | trace_src_positive_rate | phi_tgt_positive_rate | support_rate |
|---|---|---:|---:|---:|
| 42 | L | 0.0767 | 0.0352 | 0.00242 |
| 42 | R | 0.0825 | 0.0591 | 0.00587 |
| 77 | L | 0.1182 | 0.0528 | 0.00805 |
| 77 | R | 0.0988 | 0.0725 | 0.00749 |
| 123 | L | 0.1136 | 0.0794 | 0.00810 |
| 123 | R | 0.0959 | 0.0564 | 0.00517 |
| 999 | L | 0.0825 | 0.0611 | 0.00475 |
| 999 | R | 0.0815 | 0.0363 | 0.00223 |

seed42/77 have higher R phi_tgt support than L. seed123/999 have lower R
phi_tgt support than L. Therefore R-event collapse is seed-dependent
trace×phi intersection geometry, not a universal R-stimulus coverage deficit.

---

## 4. Seed split

Global trace/phi rates do not explain the seed123/999 split.

Seed family aggregate:

| family | trace_src_positive_rate | phi_tgt_positive_rate |
|---|---:|---:|
| seed42/77 | 0.0967 | 0.0540 |
| seed123/999 | 0.0904 | 0.0602 |

The global difference is small. The split is local/subgraph-level.

Key RR example:

| seed | subgraph | trace_rate | phi_rate | support_rate |
|---|---|---:|---:|---:|
| 123 | RR | 0.1209 | 0.0841 | 0.010216 |
| 999 | RR | 0.0609 | 0.0150 | 0.000819 |

seed123 RR has high trace, high phi, and high support. seed999 RR has low
trace, very low phi, and near-zero support. This is a local trace×phi overlap
split, not a global seed-rate split.

---

## 5. h interpretation

Closed_loop aggregate h correlations:

| seed | corr_h_trace_src | corr_h_phi_tgt |
|---|---:|---:|
| 42 | 0.0013 | -0.0313 |
| 77 | 0.0394 | 0.0016 |
| 123 | 0.0564 | 0.0486 |
| 999 | 0.0594 | 0.0120 |

h weakly correlates with trace_src and phi_tgt. At this level, current h[u]
is not a direct upstream variable for 9C support.

Do not use this result to design an h-gate or tag mechanism.

---

## 6. Decision

10F Step 2 closes the support identity question.

Next step: Phase 10F Step 3 — trace×phi support subgraph decomposition.

Do not enter 10E.2.
Do not change mechanism.
Do not modify 9C, 9D, tag rule, or h[u].
