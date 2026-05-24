# Phase 10E.1C — Event-Type / Topology Diagnostic Notes

**Date:** 2026-05-13
**Status:** null_for_current_h_descriptor
**Analyzer commit:** d14f457
**Results commit:** ec1a8ab
**Input:** results/phase10E1B_tag_formation_events.csv (618,930 rows)

---

## 1. Protocol / source

- Offline analysis only. No simulation rerun.
- No mechanism change. No tag rule change. No 9C/9D change.
- Analyzer: `aniva/experiments/analyze10E1C_event_type_topology.py`
- Input: `results/phase10E1B_tag_formation_events.csv` (10E.1B, 4 seeds × 3 arms)
- 360 groups analyzed (seed × arm × event_type × subgraph)
- n_shuffles=100, RNG seed=99999

---

## 2. Headline

**Verdict: null_for_current_h_descriptor**

The current global h[u]/novelty_factor descriptor is insufficient to explain
tag formation robustly across seeds and subgraphs. This is not "history has
no effect" — it is "global novelty_factor = 1 − h_norm is the wrong lens."

Do not proceed to 10E.2.
Do not modify tag rule, 9C, or 9D.

---

## 3. Event-type result

| seed | L verdict | R verdict |
|------|-----------|-----------|
| 42   | novelty_pass | novelty_pass |
| 77   | novelty_pass | null |
| 123  | novelty_inverse | novelty_inverse |
| 999  | novelty_inverse_surprise_pass | surprise_pass |

n_L_pass=2, n_R_pass=1. L-events do not pass in ≥3/4 seeds.
Event-type asymmetry alone is not the whole explanation.

---

## 4. Subgraph result

**LL subgraph (closed_loop, ALL event_type):**

| seed | auc_novelty | h_tag_ratio | verdict |
|------|-------------|-------------|---------|
| 42   | 0.412       | 1.253       | novelty_inverse |
| 77   | 0.494       | 1.343       | null |
| 123  | 0.442       | 1.342       | novelty_inverse |
| 999  | 0.336       | 1.481       | novelty_inverse |

4/4 seeds: h_tag_ratio > 1.0, novelty inverse or null. LL is a systematic
inversion subgraph. Same-side (L→L) connections behave differently from
cross-side connections.

**RL subgraph:**

| seed | auc_novelty | h_tag_ratio | verdict |
|------|-------------|-------------|---------|
| 42   | 0.764       | 0.487       | novelty_pass |
| 77   | 0.550       | 1.049       | novelty_pass |
| 123  | 0.480       | 1.109       | null |
| 999  | 0.415       | 1.396       | novelty_inverse_surprise_pass |

Direction is seed-dependent. seed42 shows the strongest novelty signal
(h_tag_ratio=0.487, auc=0.764).

**RR subgraph:**

| seed | auc_novelty | h_tag_ratio | verdict |
|------|-------------|-------------|---------|
| 42   | 0.620       | 0.876       | novelty_pass |
| 77   | 0.540       | 0.760       | novelty_weak |
| 123  | 0.355       | 1.350       | novelty_inverse |
| 999  | 0.488       | 0.935       | surprise_pass |

seed42/77 pass; seed123 inverse; seed999 surprise-only.

**inversion_global_fraction for seed123/999 ≈ 0.333** — inversion is
subgraph-local, not global. seed123/999 are not uniformly inverted.

---

## 5. Phi result

| seed | etype | mean_phi_tagged | mean_phi_untagged | direction |
|------|-------|-----------------|-------------------|-----------|
| 42   | L     | 0.314           | 0.359             | tagged < untagged |
| 42   | R     | 0.312           | 0.361             | tagged < untagged |
| 77   | L     | 0.334           | 0.363             | tagged < untagged |
| 77   | R     | 0.350           | 0.361             | tagged < untagged |
| 123  | L     | 0.420           | 0.379             | **tagged > untagged** |
| 123  | R     | 0.448           | 0.373             | **tagged > untagged** |
| 999  | L     | 0.374           | 0.321             | **tagged > untagged** |
| 999  | R     | 0.275           | 0.317             | tagged < untagged |

seed42/77: tagged connections have lower phi (consistent with novelty/low-h
connections being tagged). seed123/999: tagged connections have higher phi
(consistent with phi/surprise-driven tagging, not novelty-driven).

This is the clearest structural split in the data.

---

## 6. Interpretation

The current h[u] as a global novelty descriptor cannot explain tag formation
robustly. Tag formation appears to depend on:

1. **Subgraph geometry**: LL connections systematically invert across all seeds.
   Same-side recurrent connections accumulate h differently from cross-side.

2. **Phi projection**: seed123/999 tag formation follows high-phi connections,
   not low-h connections. The stimulus landing pattern determines which
   connections get tagged, not their historical novelty.

3. **Seed topology**: the h distribution at warmup end differs between
   seed42/77 (h_tag_ratio < 1.0 in most subgraphs) and seed123/999
   (h_tag_ratio > 1.0 in LL/RL/RR). This is a seed-level topology difference,
   not a random fluctuation.

Historical context may still matter, but only as a local/contextual descriptor
within specific subgraphs, not as a global scalar novelty predictor.

---

## 7. Decision

**Label:** null_for_current_h_descriptor

**Next step:** Phase 10E.1D — LL/RR subgraph + phi-driven tag formation
diagnostic design.

Key questions for 10E.1D:
- Why does LL invert in 4/4 seeds?
- Is tag formation in seed123/999 better explained by phi/surprise than novelty?
- Does novelty survive within matched phi bins?
- Is the split already visible in raw event_pair_dW, or only in tag accumulation?

Mechanism design remains blocked.
