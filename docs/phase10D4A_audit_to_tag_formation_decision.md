# Phase 10D.4A Audit → Tag Formation Direction Decision

**Date:** 2026-05-13
**Status:** Decision only. No implementation. No 10D.4B.

---

## 1. 10D.4A Initial Result

Phase 10D.4A ran four candidate signals against `slow_delta_abs` as the consolidation target.
Novelty appeared strongest across both seeds:

| candidate | seed42 | seed77 |
|---|---|---|
| background_alignment | 0.035 | 0.064 |
| novelty (tag × (1−h_norm)) | **0.857** | **0.768** |
| surprise_magnitude | 0.734 | 0.697 |
| neg_surprise | 0.605 | 0.649 |
| pos_surprise | 0.345 | 0.257 |

All candidates shared the same construction: `candidate = tag_abs × factor`.
The target was `slow_delta_abs`.

---

## 2. Circularity Audit Result

| metric | seed42 | seed77 |
|---|---|---|
| tag_only_alignment | 0.900 | 0.818 |
| novelty_alignment_original | 0.857 | 0.768 |
| residual_novelty_corr | **0.000** | **0.000** |
| shuffle_percentile_novelty | 0.593 | 0.549 |
| verdict | tag_self_alignment_artifact | inconclusive |

**Final verdict:** `mixed_inconclusive_tag_self_alignment_artifact`

Protocol checks: ALL PASS (10/10).

---

## 3. Interpretation

### Why residual = 0.000

`slow_delta ∝ tag_cache` by construction. The consolidation mechanism writes
`slow_delta[i] = f(tag[i])`, so `slow_abs` and `tag_abs` are mechanistically
co-linear. Residualizing `slow_abs` against `tag_abs` collapses the target to
near-zero variance. Pearson is undefined → returns 0.0.

This is not a numerical accident. It is a structural property of the system:
**any candidate of the form `tag_abs × factor` will produce high alignment with
`slow_delta_abs`, because both sides are dominated by `tag_abs`.**

### Why shuffle fails

`(1 − h_norm)` is a slowly-varying scalar field (~0.6–0.7 across all connections).
It acts as a near-constant multiplier and does not change the direction of the
novelty vector relative to `tag_abs`. Shuffling `h_norm` produces similar cosine
values because the directional information comes from `tag_abs`, not from `h_norm`.

Shuffle percentiles 0.593 / 0.549 are not significant (threshold: > 0.90).

### Closed conclusion

The `candidate × tag → slow_delta` diagnostic route is **closed**.

- `slow_delta` is the wrong target for these diagnostics.
- Any candidate built as `tag_abs × factor` will inherit tag self-alignment.
- The h_norm spatial structure does not survive the shuffle test.
- Novelty is not promoted to mechanism-positive.

---

## 4. What Is Preserved

**h_tag_ratio < 1.0 remains valid** (Phase 10D.3, both seeds):

```
seed42: h_tag_ratio = 0.834
seed77: h_tag_ratio = 0.803
```

This finding is about *which connections become tagged*, not about how tag
transfers into slow_weight. It says: tagged connections fall in historically
low-activity regions. This is upstream of consolidation.

The audit does not touch this finding. It survives.

---

## 5. Direction Switch

The question changes:

```
Before:
  Can h[u] / novelty predict slow_delta?

After:
  Does h[u] influence where tags form?
```

`slow_delta` is downstream of `tag`. Using it as a target creates a closed loop.
The right target is `tag` itself — specifically, the event-pair plasticity step
that decides which connections get marked.

The h_tag_ratio < 1.0 finding is the entry point. It shows that h[u] and tag
formation are correlated. The next question is whether this correlation is:

- **Causal**: h[u] suppresses or gates tag formation (BCM-style threshold)
- **Structural**: tagged connections happen to be in low-h regions by network topology
- **Sampling**: sparse connections are both low-h and more likely to be tagged

These three hypotheses require different diagnostics.

---

## 6. Next Phase: Phase 10E

**Name:** Phase 10E — Historical Context and Tag Formation Diagnostics

**Core question:**
Does h[u] predict where tags form, before slow consolidation writes them?

**Candidate targets (not slow_delta):**
- `tag_presence`: binary — whether a connection gets tagged at all
- `tag_strength`: `tag_cache` magnitude at capture time
- `dtag`: tag delta during event-pair update step
- `event_pair_dW`: raw plasticity update before tag accumulation

**Candidate predictors:**
- `h_conn`: mean h[u] of src/tgt pair
- `novelty_factor = 1 − h_norm`: low-history bias
- `surprise_factor = |phi − h_norm|`: deviation from expectation
- `baseline_activity`: recent activation level (topology control)

**Key diagnostics:**
- h distribution: tagged vs untagged connections
- AUC / logistic: can h_conn predict tag_presence?
- Shuffle h spatial structure null (same as audit, but against tag target)
- Per-seed topology control: is h_tag_ratio < 1.0 explained by connection density?
- Do not touch capture gate, slow_weight, or consolidation mechanism

**Design document:** `docs/phase10E_tag_formation_historical_context_diagnostics_design.md`

---

## 7. Boundaries

- No 10D.4B (rarity / compression progress candidates)
- No novelty gate implementation
- No capture redesign
- No changes to 9D mechanism
- No new plasticity rule
- Phase 10E is diagnostics only — read-only on h[u] and tag_cache
