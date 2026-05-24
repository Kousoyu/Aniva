# Phase 10D.4A — Candidate Diagnostics Smoke: Results Notes

**Date:** 2026-05-13
**Commit:** `5075d69`
**Branch:** phase10-closed-loop-event-history
**Runner:** `aniva/experiments/exp10D4A_candidate_diagnostics_smoke.py`
**Results:** `results/phase10D4A_candidate_diagnostics_*.csv/json`

---

## Scope (Frozen)

- Seeds: 42, 77
- τ = 10000 only (no τ ladder)
- Candidates: background / novelty / surprise_magnitude / signed_surprise
- No rarity/progress
- No gate change
- No `life_core.py` change
- h[u] strictly read-only

---

## Protocol

| Check | Seed 42 | Seed 77 |
|-------|---------|---------|
| P1 events > 0 | OK (12) | OK (14) |
| P2 exact replay complete | OK | OK |
| P3 no hash mismatches | OK | OK |
| P4 captures > 0 | OK (10) | OK (11) |
| P5 closed_vs_exact_h_l1 < 1e-6 | OK | OK |
| P6 warmup divergence > 1e-8 | OK | OK |
| P7 warmup weights frozen | OK | OK |
| H1 h divergence | PASS | PASS |

**Overall: ALL PASS**

---

## Results

### Seed 42

| Candidate | Alignment | Delta vs background |
|-----------|-----------|---------------------|
| background | 0.035 | — |
| novelty | 0.857 | +0.822 |
| surprise_magnitude | 0.734 | +0.699 |
| neg_surprise | 0.605 | +0.570 |
| pos_surprise | 0.345 | +0.310 |
| signed_corr | −0.413 | — |
| h_tag_ratio | 0.834 | — |

Rank: novelty > surprise_mag > neg_surprise > pos_surprise > background

### Seed 77

| Candidate | Alignment | Delta vs background |
|-----------|-----------|---------------------|
| background | 0.064 | — |
| novelty | 0.768 | +0.704 |
| surprise_magnitude | 0.697 | +0.633 |
| neg_surprise | 0.649 | +0.585 |
| pos_surprise | 0.257 | +0.193 |
| signed_corr | −0.562 | — |
| h_tag_ratio | 0.803 | — |

Rank: novelty > surprise_mag > neg_surprise > pos_surprise > background

---

## Interpretation

**What the numbers say:**

1. **novelty strongly beats background in both seeds** (×20 margin). The
   `(1 - h_norm)` factor dramatically improves alignment over raw `h_conn`.

2. **surprise_magnitude also beats background** by a large margin. The
   `|phi - h_norm|` factor is the second-strongest signal.

3. **neg_surprise > pos_surprise** in both seeds. Capture is more aligned
   with connections where `phi < h_norm` (current activation below historical
   baseline) than where `phi > h_norm`. Combined with `h_tag_ratio < 1.0`,
   this suggests capture fires preferentially in regions that are both
   historically quiet AND currently below their own baseline.

4. **signed_corr is negative** (−0.41 / −0.56). The signed `(phi − h_norm)`
   correlates negatively with slow_delta — consistent with neg_surprise
   outperforming pos_surprise.

**Verdict: candidate_signal_present in both seeds.**

---

## Critical Caveat

All winning candidates share the form `tag_abs × [factor]`.
The alignment target `slow_delta_abs` is produced by the 9D capture step,
which reads `tag_cache` directly.

Therefore:

> High alignment may partially reflect **tag_abs self-alignment** rather than
> the historical factor `(1 - h_norm)` adding genuine predictive value.

**10D.4A is promising but not decisive.**

The question that must be answered before proceeding:

> Does novelty beat background because `(1 - h_norm)` adds useful historical
> context, or because `novelty_conn` already contains `tag_abs` and
> `slow_delta_abs` is tag-derived?

---

## Next Step

Run the candidate-target circularity audit
(`exp10D4A_candidate_target_circularity_audit.py`) before entering 10D.4B.

The audit will determine whether:
- `novelty_contains_extra_context_signal` → proceed to 10D.4B
- `tag_self_alignment_artifact` → redesign candidate formulas first
