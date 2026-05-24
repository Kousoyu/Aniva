# Phase 10F Step 1 — Support Geometry Proxy Audit Notes

**Date:** 2026-05-21
**Status:** proxy_phi_support_insufficient
**Analyzer commit:** 50c3441
**Input:** results/phase10E1B_tag_formation_events.csv

---

## 1. Step 1 positioning

This was an offline proxy audit.

- Read existing `results/phase10E1B_tag_formation_events.csv`
- No simulation rerun
- No mechanism change
- No 9C change
- No 9D change
- No tag rule change

Important limitation: the 10E.1B event CSV contains `phi_conn`, which is a
recorded proxy, not confirmed true `phi[tgt]`. It does not contain
`trace[src]`. Therefore Step 1 can only audit whether the existing proxy
explains support; it cannot verify the exact 9C identity.

---

## 2. Result

Cross-seed proxy verdict:

| metric | value |
|---|---:|
| final_verdict | proxy_phi_support_insufficient |
| tag_dW_match_rate | 1.000000 |
| phi_proxy_dW_match_rate | 0.005690 |
| phi_proxy_false_positive_rate | 0.994310 |
| phi_proxy_false_negative_rate | 0.000000 |
| phi_proxy_positive_rate | 1.000000 |
| exact_phi_tgt_available | False |
| trace_src_available | False |
| step2_required | True |

L/R phi proxy coverage rate was 1.0 for both L and R in all seeds. The proxy is
too dense to explain sparse dW support.

---

## 3. Interpretation

`tag_support == dW_support` is confirmed. This matches the tag rule:

```
tag_cache += abs(dW)
tag_presence == 1 iff abs(event_pair_dW) > 0
```

This is expected and confirms the extraction is internally consistent.

`phi_conn proxy != dW_support`. The recorded `phi_conn` proxy is positive for
nearly all connections (`phi_proxy_positive_rate = 1.0`), while dW support is
sparse. The mismatch is almost entirely false positive:

```
phi_proxy says support everywhere
actual dW support is sparse
```

Therefore `phi_conn` is not usable as true `phi[tgt]` support. It is a dense
activation proxy, not the support gate itself.

Step 1 cannot decide the true 9C identity:

```
dW_support == (trace[src] != 0 AND phi[tgt] != 0)
```

because the required fields `trace[src]` and true `phi[tgt]` are absent from
the current CSV.

---

## 4. Decision

**Step 2 is required.**

Next diagnostic must capture the true event-pair support components at update
time:

- trace_src
- phi_tgt
- raw = trace_src * phi_tgt
- dW
- tag_delta

Only then can we test whether 9C support is exactly trace×phi support.

---

## 5. Boundaries

- Do not modify 9C.
- Do not modify tag rule.
- Do not modify 9D.
- Do not enter 10E.2.
- Do not claim mechanism yet.
- Do not infer true phi support from `phi_conn` proxy.
