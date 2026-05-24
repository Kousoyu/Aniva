# Phase 10E.1B — Four-Seed Tag Formation Validation Design

**Date:** 2026-05-13
**Status:** Design only. No implementation. No runner change. No mechanism change.

---

## One-line framing

> 10E.1 produced a protocol-clean weak positive on 2 seeds.
> 10E.1B asks four seeds to vote before any mechanism design begins.

Not "does it work" — "does it replicate."

---

## Background

10E.1 (commit 18cd057) final state:

- Protocol: 14/14 PASS (including P7 exact tag hash bit-for-bit match)
- seed42 closed_loop aggregate: pass, auc_novelty=0.565, shuffle_pct=1.00
- seed42 event_type: L/R both pass
- seed77 closed_loop aggregate: weak pass, auc_novelty=0.521, shuffle_pct=0.95
- seed77 event_type: L weak pass, **R null** (auc=0.495, shuffle_pct=0.38)
- seed77 divergent arm: **weak_signal** (shuffle_pct=0.87 < 0.90)
- h_tag_ratio: 0.949 (seed42), **1.008 (seed77, direction flipped)**
- tag_rate: 0.41% / 0.79% (sparse, high-variance)

Two seeds disagree at event_type resolution. That is not a mechanism-ready
signal. Four seeds decide whether the aggregate weak positive generalizes or
dissolves.

---

## Scope

Validation only. No new hypotheses, no new candidates, no new diagnostics.
The point is to see whether the same runner produces the same verdict across
a wider seed panel.

**Fixed:**
- Runner: `aniva/experiments/exp10E1_tag_formation_historical_context_diagnostics.py`
  (commit 98fc2b0 or later, no code changes for 10E.1B)
- Seeds: **42, 77, 123, 999**
- total_steps=7500, warmup_end=2000, decision_interval=250
- historical_context_tau=10000, historical_context_clip=True
- warmup weights frozen
- 9C/9D enabled after warmup, disabled during warmup
- exact_replay tag-hash check required for all seeds
- n_shuffles=100

**Not changing:**
- Tag rule
- event_pair_plasticity
- consolidation / slow_weight
- capture gate
- h[u] τ or semantics
- Candidate signals (novelty_factor, surprise_factor, pos/neg)

---

## Primary criteria (for a 10E.2 go-ahead)

All of the following must hold:

1. **Protocol clean on all seeds.** P1–P7 PASS for every seed.
   Any `exact_tag_hash_mismatch_count > 0` ⇒ protocol fail, no interpretation.

2. **Aggregate novelty AUC > 0.5 in at least 3/4 seeds** in closed_loop.

3. **Shuffle_percentile_novelty > 0.90 in at least 3/4 seeds** in closed_loop.

4. **No seed has severe inverse signal.** No seed with aggregate
   `auc_novelty < 0.48` (i.e., no seed actively pointing the wrong way).

5. **Event-type splits should not show systematic collapse in one direction
   across most seeds.** If 3+ seeds show one event type null, that is an
   event-type confound, not a validation.

---

## Secondary diagnostics (informative, not gates)

- **L vs R event stability**: does the L-R asymmetry seen in seed77 persist?
- **tag_rate distribution**: is the 0.4–0.8% range typical or seed-dependent?
- **h_tag_ratio direction**: does it stabilize on one side of 1.0 as seeds grow,
  or stay mixed?
- **Divergent arm consistency**: does the divergent arm ever show markedly
  different signal from closed_loop, suggesting h[u] trajectory matters?
- **topology_confound flag**: should remain False. If it flips, open 10E.1C.

---

## Decision rules

| outcome | verdict | next step |
|---|---|---|
| 4/4 or 3/4 pass primary, no severe inverse | **validated_weak_positive** | Proceed to **Phase 10E.2 diagnostic design** (still diagnostic, not mechanism) |
| 2/4 pass | **unstable** | Do not proceed. Open 10E.1C event-type / topology diagnostic |
| ≤ 1/4 pass | **null_after_validation** | h[u] is not a sufficient tag-formation descriptor; redesign history representation (shorter τ, event-gated h) |
| Systematic event-type asymmetry across 3+ seeds | **event_type_confound** | Open 10E.1C before any further work |
| Any P7 tag-hash mismatch | **protocol_fail** | Investigate determinism / RNG state before interpreting anything |

**10E.2 is blocked** until 10E.1B returns `validated_weak_positive`.
Even then, 10E.2 is still diagnostic, not mechanism.

---

## Output schema

Per-seed: same as 10E.1 (event rows + summary).
Cross-seed aggregation (new, 10E.1B-only):

| field | description |
|---|---|
| seed | 42 / 77 / 123 / 999 |
| aggregate_auc_novelty | closed_loop ALL events |
| aggregate_shuffle_pct | same |
| aggregate_verdict | pass / weak / null |
| L_auc_novelty, L_verdict | per event_type |
| R_auc_novelty, R_verdict | per event_type |
| divergent_auc, divergent_verdict | divergent arm aggregate |
| exact_tag_hash_mismatch | must be 0 |
| n_events, n_tagged, tag_rate | sparsity context |

Cross-seed summary row:
- n_seeds_passing_primary
- n_seeds_severe_inverse
- event_type_asymmetry_seeds_count
- final_cross_seed_verdict

---

## Estimated cost

Per seed: ~185s × 3 arms ≈ 185s in practice (arms overlap in the current runner
architecture). 4 seeds ≈ ~12–13 min local. Well within local budget.

Events CSV size: ~27MB/seed × 4 ≈ ~108MB total. Summary JSON remains small.
Commit the summary + notes; skip the events CSV (over 50MB threshold).

---

## Boundaries

- No mechanism changes.
- No new candidates.
- No τ tuning.
- No h[u] redesign.
- No novelty gate.
- No capture redesign.
- No claim of digital life / consciousness / personhood.
- 10E.1B is validation; it produces a verdict, not a mechanism.
