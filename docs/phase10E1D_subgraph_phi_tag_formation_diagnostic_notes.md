# Phase 10E.1D — Subgraph / Phi-Driven Tag Formation Diagnostic Notes

**Date:** 2026-05-21
**Status:** tautological_dW_predictor — upstream question redirected to 9C support geometry
**Analyzer commit:** 8e3622c
**Results commit:** 84da374
**Input:** results/phase10E1B_tag_formation_events.csv

---

## 1. Result headline

Analyzer verdict: `raw_9C_event_pair_geometry`

**Reinterpretation required.** `auc_abs_dW = 1.0` everywhere is not a discovery.
It is a tautology. The verdict label is technically correct but misleading.

---

## 2. Why tautological

The tag rule accumulates `abs(dW)` from event-pair plasticity:

```
tag_cache += abs(event_pair_dW)
tag_presence = 1  iff  abs(tag_delta) > eps
tag_delta = tag_after - tag_before = abs(event_pair_dW)
```

Therefore:

```
tag_presence == 1  ⟺  abs(event_pair_dW) > 0
```

Using `abs_dW` to predict `tag_presence` is circular by construction.
`auc_abs_dW = 1.0` and `corr_abs_dW_tag_strength = 1.0` are definitional,
not empirical findings. This closes the "predict tag from dW" route.

---

## 3. Matched controls

| seed | matched_phi_novelty_auc | matched_h_phi_auc |
|------|------------------------|-------------------|
| 42   | 0.523                  | 0.503             |
| 77   | 0.504                  | 0.465             |
| 123  | 0.440                  | 0.539             |
| 999  | 0.434                  | 0.536             |

No seed reaches > 0.55 in either control. Novelty disappears under phi control.
Phi disappears under h control. Neither h[u] nor phi_conn is an independent
predictor of tag formation at this diagnostic level.

---

## 4. Interpretation

The question has moved upstream from tag formation to event-pair dW support.

h[u] and phi_conn as currently measured are downstream or correlated views of
9C event-pair plasticity output. They are not sufficient independent causes.

The real question is: **what determines nonzero event-pair dW support in 9C?**

Specifically:
- Is dW support determined by `trace[src] > 0 AND phi[tgt] > 0`?
- Does the L/R event-type null in 10E.1B map to phi support geometry?
- Does the seed123/999 inversion map to trace source distribution?
- Does h[u] correlate with trace[src] or phi[tgt]? If not, h is not upstream.

---

## 5. Decision

- Do not enter 10E.2.
- Do not modify tag rule.
- Do not modify 9C or 9D.
- Next: **Phase 10F — Event-Pair Plasticity Support Geometry** design.

The 10E diagnostic chain is complete. The question has been correctly
redirected from "does h predict tag?" to "what is the support of 9C dW?"
