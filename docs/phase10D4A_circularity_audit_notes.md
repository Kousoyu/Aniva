# Phase 10D.4A Circularity Audit — Notes

**Date:** 2026-05-13
**Commit:** 50d4c2c (results), 4a97a78 (runner)
**Status:** AUDIT FAILED — novelty is tag self-alignment artifact

---

## Results

| metric | seed42 | seed77 |
|---|---|---|
| tag_only_alignment | 0.900 | 0.818 |
| novelty_alignment_original | 0.857 | 0.768 |
| residual_novelty_corr | 0.000 | 0.000 |
| shuffle_percentile_novelty | 0.593 | 0.549 |
| within_tag_novelty_corr | +0.134 | −0.099 |
| verdict | tag_self_alignment_artifact | inconclusive |

**Final verdict:** `mixed_inconclusive_tag_self_alignment_artifact`

Protocol checks: ALL PASS (10/10)

---

## What the numbers mean

**tag_only ≈ novelty_orig**: seed42 diff = 0.043 (< 0.05 threshold → artifact).
seed77 diff = 0.050 (borderline, just above threshold → inconclusive).
In both cases, the novelty candidate adds essentially nothing over tag_abs alone.

**residual = 0.000 (both seeds)**: This is exact zero, not near-zero.
Root cause: `slow_delta ∝ tag` by construction — consolidation writes
`slow_delta[i] = f(tag[i])`, so `slow_abs` is mechanistically proportional to `tag_abs`.
Residualizing `slow_abs` by `tag_abs` leaves `residual_slow ≈ 0` (std < 1e-12),
making Pearson undefined → returns 0.0. The residualization metric is
**not informative** for this system because the target is tag-derived.

**shuffle_pct = 0.59 / 0.55**: Observed novelty alignment is at the 59th / 55th
percentile of the shuffle distribution. Not significant (threshold: > 0.90).
Shuffling h_norm produces similar alignment — the h_norm factor is not contributing
directional information.

**Mechanistic explanation**: `novelty_conn = tag_abs × (1 − h_norm)`.
Since `(1 − h_norm)` is a slowly-varying scalar field (values ~0.6–0.7 across
all connections), it acts as a near-constant multiplier. It doesn't change the
*direction* of the novelty vector relative to tag_abs, only its magnitude.
Therefore `cosine(novelty_conn, slow_abs) ≈ cosine(tag_abs, slow_abs)`.

---

## Conclusion

The 10D.4A novelty signal (0.857 / 0.768) is explained by tag_abs self-alignment.
The h_norm factor `(1 − h_norm)` does not contribute genuine historical context
information to the consolidation target.

**10D.4A is NOT promoted to mechanism-positive.**

The novelty candidate as formulated (`tag_abs × (1 − h_norm)`) cannot distinguish
"historically novel connections consolidate more" from "tagged connections consolidate
more" — because the two are nearly identical vectors.

---

## What this rules out vs. what it doesn't

**Rules out**: novelty_conn as a *target signal* for consolidation.
The high cosine in 10D.4A was an artifact of the candidate construction.

**Does NOT rule out**: h[u] as a *gating variable* for consolidation.
The h_tag_ratio < 1.0 finding from 10D.3 (tagged connections fall in
historically low-h regions) is still valid and unexplained by this audit.
That finding is about *which connections get tagged*, not about the
consolidation target.

**Does NOT rule out**: a different formulation where h[u] modulates
*whether* consolidation fires (threshold gate), not *how much* it writes.

---

## Next direction

The circularity audit closes the "novelty as target" path.
The surviving question from 10D.3 is: **why do tagged connections
preferentially fall in low-h regions?**

This is a structural question about the tagging mechanism, not the
consolidation target. Possible 10D.5 directions:

1. **h-gated tagging threshold**: does h[u] suppress tag formation?
   (BCM-style: high history → higher threshold → less tagging)
2. **h-stratified consolidation rate**: does consolidation write more
   to low-h connections even without novelty weighting?
3. **Null hypothesis**: h_tag_ratio < 1.0 is a sampling artifact
   (tagged connections are sparse; sparse connections happen to be
   in low-activity regions by network topology).

Before 10D.5, the null hypothesis (option 3) should be tested.
