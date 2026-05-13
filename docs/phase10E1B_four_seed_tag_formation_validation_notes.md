# Phase 10E.1B — Four-Seed Tag Formation Validation Notes

**Date:** 2026-05-13
**Status:** unstable_event_type_confound
**Runner commit:** 7a4579d (design), 98fc2b0 (runner)
**Results:** results/phase10E1B_tag_formation_summary.json, results/phase10E1B_tag_formation_summary.csv

---

## 1. Protocol

28/28 PASS. No protocol failure.

- P1–P6: row counts, hash integrity, arm parity — all clean
- P7 exact tag hash mirror: 0 mismatches for all 4 seeds
  - exact_replay tag formation is bit-for-bit identical to closed_loop
  - protocol is not the source of instability

Runner/fix lineage:
- 94c6299 — divergent arm placement fix (was after sys.exit)
- 98fc2b0 — P7 exact replay tag hash check added
- 18cd057 — 10E.1 weak positive results archived
- 7a4579d — 10E.1B four-seed validation design

---

## 2. Per-seed closed_loop aggregate (ALL events)

| seed | auc_novelty | shuffle_pct | h_tag_ratio | tag_rate | verdict |
|------|-------------|-------------|-------------|----------|---------|
| 42   | 0.565       | 1.00        | 0.949       | 0.41%    | pass |
| 77   | 0.521       | 0.95        | 1.008       | 0.79%    | borderline / weak |
| 123  | 0.428       | 0.00        | 1.242       | 0.63%    | severe inverse |
| 999  | 0.431       | 0.00        | 1.285       | 0.43%    | severe inverse |

topology_confound_flag: false for all seeds.

Event-type split (closed_loop):

| seed | L verdict | R verdict |
|------|-----------|-----------|
| 42   | pass      | pass      |
| 77   | pass      | null      |
| 123  | null      | null      |
| 999  | null      | null      |

R-events null in seed77, seed123, seed999 — 3/4 seeds.

Divergent arm (ALL events):

| seed | auc_novelty | shuffle_pct | verdict |
|------|-------------|-------------|---------|
| 42   | 0.570       | 1.00        | pass |
| 77   | 0.516       | 0.87        | weak_signal |
| 123  | 0.427       | 0.00        | null |
| 999  | 0.424       | 0.00        | null |

---

## 3. Primary criteria

1. Protocol all pass: **YES**
2. auc_novelty > 0.5 in ≥3/4 seeds: **FAIL** — only 2/4 (seed42, seed77)
3. shuffle_pct > 0.90 in ≥3/4 seeds: **FAIL** — only 2/4 (seed42, seed77)
4. No severe inverse (auc < 0.48): **FAIL** — seed123=0.428, seed999=0.431
5. No systematic event-type collapse: **FAIL** — R-events null in 3/4 seeds

---

## 4. Interpretation

10E.1 weak positive did not validate across 4 seeds.

The split is structurally clean:

- seed42/77: h_tag_ratio ≈ 0.95–1.01 → tagged connections have lower h → novelty_factor predicts tagging → auc_novelty > 0.5
- seed123/999: h_tag_ratio ≈ 1.24–1.29 → tagged connections have higher h → novelty_factor inverts → auc_novelty < 0.48

For seed123/999, best_predictor = surprise, auc_surprise ≈ 0.55–0.57, shuffle_pct = 0.95–1.00. The signal is real but in the opposite direction from the novelty hypothesis.

R-event instability is systematic: 3/4 seeds show R-events null. This is not noise — it suggests event-type geometry, stimulus coverage, or subgraph h-distribution differs between L and R events in a way that breaks the global novelty rule.

The failure mode is not "historical context has no effect." It is "global novelty_factor is not a universal predictor — seed topology and event direction both modulate the relationship."

Do not modify tag rule.
Do not modify 9C/9D.
Do not enter 10E.2.

---

## 5. Decision

**Label:** unstable_event_type_confound

**Next step:** Phase 10E.1C — event-type / topology diagnostic design

Inspect:
- Why R-events collapse in 3/4 seeds (subgraph composition vs event response asymmetry)
- Why seed123/999 invert (h topology at warmup end vs seed42/77)
- Whether novelty holds within matched subgraphs even when global aggregate inverts
