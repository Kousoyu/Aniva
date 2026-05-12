# Phase 10D.3 — h[u] Alignment Diagnostics Design

## Context

Phase 10D.2 confirmed: `historical_context_trace` h[u] (τ=10000) stores warmup history
that is invisible to `event_trace`, `tag_cache`, and all existing 9C/9D diagnostics.
The film is exposed. h[u] is a genuine history container.

h[u] is still read-only and does not affect gate, capture, or slow_weight.

**10D.3 does not connect h[u] to any mechanism.**
It asks: if capture could read h[u], what projection would be most informative?

---

## Hypothesis

**H1 (h-tag alignment):** At capture time, units with high h[u] are more likely to be
tagged (tag_cache > 0). If warmup history concentrates in the same units that get tagged
during replay, h[u] and tag_cache are structurally aligned.

**H2 (h-weighted capture signal):** The capture signal (slow_weight delta) is larger
when the capturing units have higher h[u]. h[u] magnitude predicts capture strength.

**H3 (h-context divergence predicts h-final divergence):** The h[u] divergence at
warmup end (`h_divergence_at_warmup_end`) predicts the h[u] divergence at final
(`h_divergence_at_final`). History imprint is stable, not washed out by replay.

---

## Four-Arm Structure (same as 10D.2)

Reuse the 10D.2 runner unchanged. Add diagnostic extraction only.

Arms: closed_loop, exact_replay, divergent_warmup_replay, matched_warmup_control.
Warmup weights frozen (fix from 10D.2 v2 already in place).

---

## New Diagnostics (read-only, no mechanism change)

### D1 — h-tag alignment score

At each capture event in closed_loop and exact_replay:
- `h_tag_alignment = corr(h[u], tag_cache[u])` over all units u
  (Pearson correlation between h[u] vector and tag_cache vector)
- `h_tagged_mean = mean(h[u] for u where tag_cache[u] > 0)`
- `h_untagged_mean = mean(h[u] for u where tag_cache[u] == 0)`
- `h_tag_ratio = h_tagged_mean / (h_untagged_mean + 1e-9)`

Logged per capture event. Aggregated as mean ± std across all captures per seed.

### D2 — h-weighted capture signal

At each capture event:
- `h_weighted_slow_delta = sum(h[u] * |slow_weight_delta[u]|) / sum(h[u] + 1e-9)`
  (h[u]-weighted average of slow_weight change magnitude)
- `h_capture_corr = corr(h[u], |slow_weight_delta[u]|)` over all units

Logged per capture event.

### D3 — h-context stability

Computed once per seed at end of run:
- `h_warmup_end_l1` — L1 norm of h[u] at warmup end (already in 10D.2)
- `h_final_l1` — L1 norm of h[u] at final (already in 10D.2)
- `h_decay_ratio = h_final_l1 / h_warmup_end_l1`
  (how much of the warmup imprint survives through replay)
- `h_divergence_stability = h_divergence_at_final / h_divergence_at_warmup_end`
  (does the divergence between closed and divergent arms grow, shrink, or hold?)

### D4 — h-concentration profile

At warmup end and at final:
- `h_top10_frac` — fraction of total h[u] L1 mass in top-10% units
- `h_effective_support` — number of units with h[u] > 0.01 * max(h[u])
- `h_gini` — Gini coefficient of h[u] distribution

These describe whether h[u] is diffuse or concentrated, which matters for
whether a future h-gate would be selective or global.

---

## Protocol Checks (same as 10D.2 P1-P7, plus)

**P8:** `h_tag_ratio > 1.0` in at least one arm (tagged units have higher h[u] than
untagged — directional alignment exists).

**P9:** `h_decay_ratio > 0.5` (warmup imprint survives at least 50% through replay).

P8 and P9 are soft checks — failure is informative, not disqualifying.

---

## Success Criteria

**H1 PASS:** `mean(h_tag_alignment) > 0.05` across captures in closed_loop.
Interpretation: h[u] and tag_cache are positively correlated at capture time.

**H2 PASS:** `mean(h_capture_corr) > 0.05` across captures in closed_loop.
Interpretation: units with more history tend to receive larger slow_weight updates.

H1 and H2 are independent. Either passing is informative.

**Target outcome:** H1 or H2 PASS → h[u] is structurally aligned with capture,
justifying a future h-gate design in 10D.4.

**Null outcome:** Both fail → h[u] and capture are orthogonal. h[u] stores history
but it is not the history that capture cares about. Still informative — rules out
naive h-gate designs.

---

## Implementation Notes

- Do not modify `life_core.py`, `config.py`, or any existing mechanism
- All diagnostics computed in the runner from existing arrays:
  `core._historical_context_trace`, `core._tag_cache`, `core._slow_weight_cache`
- `slow_weight_delta[u]` = difference in `_slow_weight_cache` before and after
  `apply_consolidation()` — snapshot before, diff after
- h[u] at capture time = `core._historical_context_trace.copy()` at the step
  when `_consolidation_ledger` gains a new entry

---

## Output Files

```
results/phase10D3_h_alignment_seed{seed}_summary.csv
results/phase10D3_h_alignment_seed{seed}_captures.csv   ← per-capture diagnostics
results/phase10D3_h_alignment_seed{seed}_events.csv
results/phase10D3_h_alignment_summary.json
```

---

## Frozen Parameters

| parameter | value |
|---|---|
| seeds | [42, 77] |
| unit_count | 300 |
| total_steps | 7500 |
| warmup_end | 2000 |
| τ_h | 10000 |
| h clip | True |
| h affects gate | False |
| h affects capture | False |
| h affects slow_weight | False |

---

## Relation to 10D.2

10D.2 asked: *can h[u] see warmup history?* → Yes.
10D.3 asks: *is h[u]'s history aligned with what capture cares about?*

If yes → 10D.4 designs a minimal h-gate: capture reads h[u] as a context signal.
If no → revisit h[u] definition (different τ, different aggregation, or different
history variable entirely).
