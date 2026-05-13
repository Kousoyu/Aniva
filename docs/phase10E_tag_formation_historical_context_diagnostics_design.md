# Phase 10E — Tag Formation Historical Context Diagnostics Design

**Date:** 2026-05-13
**Status:** Design only. No implementation. No runner yet.

---

## One-line framing

> 10D asked whether historical context predicts consolidation output.
> Audit showed that output is downstream of tag and therefore circular.
> 10E moves upstream: does historical context predict tag formation itself?

不是看墨水干了以后像不像历史，而是看**笔尖落在哪儿**。

---

## Background

| phase | finding |
|---|---|
| 10D.2 | h[u] stores warmup history; τ=10000 gives stable, differentiated traces |
| 10D.3 | h_tag_ratio < 1.0 in both seeds (0.834 / 0.803); tagged connections fall in historically low-h regions |
| 10D.4A | novelty candidate (tag_abs × (1−h_norm)) appeared strongest vs slow_delta_abs (0.857 / 0.768) |
| 10D.4A audit | tag_only_alignment ≈ 0.90 / 0.82; residual = 0.000; shuffle_pct = 0.59 / 0.55 |
| decision | `candidate × tag → slow_delta` route closed; slow_delta ∝ tag_cache by construction |

**What survives:** h_tag_ratio < 1.0 is a structural signal about tag formation, not about
consolidation transfer. It is the entry point for 10E.

---

## Why slow_delta is the wrong target

```
event-pair plasticity → tag_cache update (dtag)
                              ↓
consolidation gate fires → slow_weight += f(tag_cache)
                              ↓
slow_delta = slow_weight_after - slow_weight_before
```

`slow_delta_abs ∝ tag_cache` by construction. Any candidate of the form
`tag_abs × factor` will produce high cosine alignment with `slow_delta_abs`
regardless of whether `factor` carries genuine information. Residualizing
against `tag_abs` collapses the target to near-zero variance.

The correct target is **upstream**: the tag formation step itself.

---

## Core question

Does h[u] predict which connections receive nonzero tag_delta during
event-pair plasticity, before slow consolidation writes them?

---

## New targets

### 1. tag_presence
Binary: whether a connection receives nonzero tag_delta during event-pair update.
`tag_presence[i] = 1 if |tag_after[i] - tag_before[i]| > ε else 0`

### 2. tag_strength
Magnitude of tag increment.
`tag_strength[i] = |tag_after[i] - tag_before[i]|`

### 3. dtag
Signed tag delta.
`dtag[i] = tag_after[i] - tag_before[i]`

### 4. event_pair_dW
Raw plasticity update before tag accumulation, if accessible from LifeCore internals.
Label as proxy if not directly exposed; note limitation.

**Not a valid target:** `slow_delta_abs` — downstream of tag, circular.

---

## Candidate predictors

### A. background_h
`h_conn = 0.5 * (h[src] + h[tgt])`
Tests whether high/low historical activity predicts tag formation.
Expected direction from h_tag_ratio < 1.0: low h_conn → higher tag_presence.

### B. novelty_factor
`novelty_factor = 1.0 - h_norm_conn`
where `h_norm_conn = h_conn / max(h_conn) + ε`
Tests whether historically novel (low-h) connections are preferentially tagged.

### C. surprise_factor
`surprise_factor = |phi_conn - h_norm_conn|`
`phi_conn = 0.5 * (acts[src] + acts[tgt])` at event time (proxy — label limitation).
Tests whether deviation from expected activity predicts tagging.

### D. signed_surprise
`pos_factor = max(0, phi_conn - h_norm_conn)` — activation exceeds history
`neg_factor = max(0, h_norm_conn - phi_conn)` — activation below history

### E. topology / region controls
- src_region, tgt_region (L / M / R by x-position)
- subgraph label (LR / RL / LL / RR / MM / cross)
- baseline_weight_abs: |weight| before event
- connection degree proxy if available
These are controls, not primary predictors. Used to check topology confound.

---

## Diagnostics

### 1. Tagged vs untagged distribution

For each event-pair update, split connections into tagged (tag_presence=1) and untagged.

Compute:
- `mean_h_tagged` vs `mean_h_untagged`
- `mean_novelty_tagged` vs `mean_novelty_untagged`
- Cohen's d for h_conn and novelty_factor
- `h_tag_ratio = mean_h_tagged / mean_h_untagged` (should be < 1.0 if 10D.3 holds)
- `novelty_tag_ratio = mean_novelty_tagged / mean_novelty_untagged` (should be > 1.0)

This is the direct replication of 10D.3 at event-pair resolution.

### 2. Binary prediction (AUC)

For each predictor, compute rank-AUC for predicting tag_presence.
No external ML package required: rank-AUC = P(predictor[tagged] > predictor[untagged]).

Predictors to test: h_conn (inverted), novelty_factor, surprise_factor, pos_factor, neg_factor.

Expected: novelty_factor AUC > 0.5 if low-h connections are preferentially tagged.

### 3. Strength prediction

Among tagged connections only, compute:
- Spearman(novelty_factor, tag_strength)
- Spearman(h_conn, tag_strength) — expected negative
- Spearman(surprise_factor, tag_strength)

Tests whether the degree of tagging (not just presence) is modulated by history.

### 4. Shuffle null

Permute h_conn across connections (preserving tag_delta assignment).
Recompute AUC for novelty_factor and h_conn.
Repeat n_shuffles=100 times.
Report observed percentile vs shuffle distribution.

Threshold: shuffle_percentile > 0.90 for signal to be considered non-trivial.

### 5. Topology / event-type controls

- Split by subgraph (LR / RL / LL / RR / cross-M): does signal hold within subgraph?
- Split by event_type (L / R / simultaneous): does signal hold per event type?
- If signal disappears after topology split: flag topology_confound.
- If signal holds within subgraph: topology is not the explanation.

---

## Output schema

### Event-pair-level CSV (one row per connection per event)

| field | description |
|---|---|
| seed | RNG seed |
| arm | closed_loop / exact_replay / divergent_warmup_replay |
| event_index | sequential event counter |
| event_step | simulation step |
| event_type | L / R / simultaneous |
| connection_id | connection index |
| src | source unit index |
| tgt | target unit index |
| src_region | L / M / R |
| tgt_region | L / M / R |
| subgraph | LL / LR / RL / RR / LM / RM / MM / other |
| h_conn | 0.5*(h[src]+h[tgt]) at event time |
| h_norm_conn | h_conn / max(h_conn) |
| novelty_factor | 1 - h_norm_conn |
| surprise_factor | \|phi_conn - h_norm_conn\| |
| pos_factor | max(0, phi_conn - h_norm_conn) |
| neg_factor | max(0, h_norm_conn - phi_conn) |
| tag_before | tag_cache[i] before event-pair update |
| tag_after | tag_cache[i] after event-pair update |
| tag_delta | tag_after - tag_before |
| tag_presence | 1 if \|tag_delta\| > ε else 0 |
| tag_strength | \|tag_delta\| |
| baseline_weight_abs | \|weight[i]\| before event |
| phi_conn | activation proxy (label: proxy, not clean delta) |

### Summary CSV (one row per seed × arm × event_type)

| field | description |
|---|---|
| seed, arm, event_type | grouping keys |
| n_connections | total connections evaluated |
| n_tagged | connections with tag_presence=1 |
| tag_rate | n_tagged / n_connections |
| h_tag_ratio | mean_h_tagged / mean_h_untagged |
| novelty_tag_ratio | mean_novelty_tagged / mean_novelty_untagged |
| auc_h | rank-AUC for h_conn (inverted) predicting tag_presence |
| auc_novelty | rank-AUC for novelty_factor |
| auc_surprise | rank-AUC for surprise_factor |
| auc_pos | rank-AUC for pos_factor |
| auc_neg | rank-AUC for neg_factor |
| corr_novelty_tag_strength | Spearman within tagged |
| corr_h_tag_strength | Spearman within tagged |
| shuffle_percentile_novelty_auc | observed vs shuffle distribution |
| shuffle_percentile_surprise_auc | observed vs shuffle distribution |
| topology_confound_flag | True if signal disappears within subgraph |
| best_predictor | predictor with highest AUC |
| verdict | see decision rules |

---

## Decision rules

### Pass: historical context influences tag formation
Condition: novelty_factor AUC > 0.5 in both seeds AND shuffle_percentile > 0.90 in both seeds.

Interpretation: historically low-activity connections are preferentially tagged.
h[u] carries information about where experience marks the structure.
Next step: 10E.1 runner implementation.

### Pass (weak): h_conn predicts tag_presence negatively
Condition: AUC for inverted h_conn > 0.5 in both seeds, shuffle_percentile > 0.90.
novelty_factor AUC may be similar (since novelty = 1 − h_norm).

Interpretation: same as above, just framed as "low-h → tagged" rather than "high-novelty → tagged".
Next step: same as pass.

### Topology confound
Condition: signal present in aggregate but disappears within subgraph split.

Interpretation: h_tag_ratio < 1.0 is explained by network topology (e.g., cross-region
connections have both lower h and higher tag rate by geometry).
Next step: matched topology diagnostic — compare connections with similar topology but
different h values.

### Null: no predictor beats shuffle
Condition: all AUCs ≤ 0.5 or shuffle_percentile ≤ 0.90 for all predictors.

Interpretation: h[u] as currently defined is not a sufficient tag formation descriptor.
Possible causes: h[u] τ too slow (10000 steps), h[u] not capturing the right timescale,
or tag formation is not history-dependent at this resolution.
Next step: design event-gated history descriptor (shorter τ, or event-triggered h reset).
Do not implement novelty gate yet.

### Seed disagreement
Condition: one seed passes, one fails.

Next step: expand to 4-seed diagnostic before mechanism design.

---

## Arm structure

Same three-arm structure as 10D.4A:

1. **closed_loop**: live scheduler, real event history, real h[u] accumulation
2. **exact_replay**: same events, same warmup, different h trajectory (control)
3. **divergent_warmup_replay**: divergent warmup → different h[u] → same events

The divergent arm is the key test: if h[u] predicts tag formation, then a different
warmup history should produce different tag formation patterns for the same events.

---

## Boundaries

- Do not alter tag rule or event_pair_plasticity.
- Do not alter consolidation or slow_weight.
- Do not introduce reward, fitness, or evaluator.
- Do not use LLM or external interestingness judge.
- Do not claim digital life / consciousness / personhood.
- Do not enter 10D.4B (rarity / compression progress).
- Do not implement novelty gate.
- Do not redesign capture gate.
- Do not change 9D or 9C mechanisms.
- This document is design only. Runner: Phase 10E.1.

