# Phase 10E.1 Tag Formation Historical Context Diagnostics — Notes

**Date:** 2026-05-13
**Status:** weak_positive_preliminary
**Protocol:** clean (14/14 PASS, exact replay bit-for-bit mirror)

---

## Headline

> Historical context h[u] has a small, non-random relationship with where tags
> form. The signal is weak and unstable across seeds and event types; it is
> **not strong enough to motivate mechanism design**. Next required step:
> 4-seed validation (Phase 10E.1B).

Not a strong positive. Not a null. A protocol-clean weak positive that needs
more seeds before it earns any mechanism design.

---

## Protocol hardening timeline

| commit | change |
|---|---|
| 73bdddc | runner initial version |
| 94c6299 | repaired `_run_arm_divergent` placement (was after `sys.exit`) |
| 98fc2b0 | added exact_replay tag-formation hash check (P7) |
| (this run) | official rerun from clean HEAD 98fc2b0 |

The first run (after 94c6299) produced the same numbers but with no tag-formation
content check on exact_replay — only row count and phi hash. After 98fc2b0, each
event-pair update produces a sha256 over `(event_index, event_step, event_type,
tag_pre, tag_after)`, and closed_loop vs exact_replay hashes must match bit-for-bit.
They do. Exact_replay is now a true mirror.

---

## Official results (commit 98fc2b0)

### Protocol checks — ALL 14 PASS

| check | seed42 | seed77 |
|---|---|---|
| P1 cl_rows > 0 | PASS | PASS |
| P2 er_rows > 0 | PASS | PASS |
| P3 dv_rows > 0 | PASS | PASS |
| P4 exact_replay phi hash | PASS (0 mm) | PASS (0 mm) |
| P5 divergent phi hash | PASS (0 mm) | PASS (0 mm) |
| P6 cl/er row count match | PASS | PASS |
| **P7 exact tag hash match** | **PASS (12/12)** | **PASS (14/14)** |

### closed_loop aggregate

| metric | seed42 | seed77 |
|---|---|---|
| events | 12 | 14 |
| rows | 53,820 | 62,790 |
| n_tagged | 223 | 493 |
| tag_rate | 0.41% | 0.79% |
| h_tag_ratio | 0.949 | **1.008** |
| novelty_tag_ratio | 1.081 | 1.030 |
| auc_novelty | 0.565 | 0.521 |
| shuffle_pct_novelty | 1.00 | 0.95 |
| verdict | pass | pass (borderline) |

### closed_loop per event_type

| seed | event | n_tagged | auc_nv | shuffle_pct | h_tag_ratio | verdict |
|---|---|---|---|---|---|---|
| 42 | L | 65 | 0.591 | 0.98 | 0.935 | pass |
| 42 | R | 158 | 0.553 | 0.99 | 0.911 | pass |
| 77 | L | 325 | 0.534 | 0.99 | 0.951 | pass (weak) |
| 77 | R | 168 | **0.495** | **0.38** | **1.152** | **null** |

### divergent_warmup_replay (key test arm, aggregate)

| seed | auc_nv | shuffle_pct | h_tag_ratio | verdict |
|---|---|---|---|---|
| 42 | 0.570 | 1.00 | 0.978 | pass |
| 77 | 0.516 | **0.87** | 0.996 | **weak_signal** |

topology_confound_flag: False across all seed × event_type splits.

---

## Caveats

1. **Effect size is small.** All AUCs fall in [0.50, 0.59]. Strong signals
   would be in the 0.7+ range. A reader looking only at the aggregate verdict
   would overstate this.

2. **seed77 R-events are null, not weak.** auc=0.495 is below random; shuffle
   percentile=0.38 means the observed AUC is below the 62nd percentile of the
   shuffle distribution. h_tag_ratio=1.152 points the opposite direction from
   10D.3 (0.803) and from seed42 (0.911). The seed77 aggregate pass is carried
   by the L-events (325/493 tagged) diluting the R null.

3. **seed77 divergent arm is weak_signal.** shuffle_pct=0.87 < 0.90 threshold.
   Changing the warmup trajectory does not strengthen the signal; it stays
   at the noise floor.

4. **Tag formation is sparse.** tag_rate 0.41% / 0.79% means 223 / 493 positive
   samples across 12–14 events. The class imbalance inflates variance in any
   per-event or per-subgraph statistic.

5. **h_tag_ratio direction is not stable.** seed42 < 1.0 (consistent with 10D.3),
   seed77 > 1.0. The 10D.3 finding of "tagged connections fall in historically
   low-h regions" does not reliably replicate at event-pair resolution.

---

## Interpretation

Historical context h[u] has a **small, non-random** relationship with tag
formation in some seeds / event types. This is consistent with "historical
context weakly biases tag formation" but does not demonstrate it strongly
enough to act on.

**Do not modify the tag rule.**
**Do not modify 9C or 9D mechanisms.**
**Do not enter novelty gate or capture redesign.**
**Do not proceed to 10E.2 on 2-seed evidence.**

The signal may be real; it may also be a sampling artifact under sparse tag
formation. Four seeds will decide.

---

## Decision

- Label: **weak_positive_preliminary**
- Protocol: clean (P1–P7 all pass)
- Next required step: **Phase 10E.1B — four-seed tag formation validation**
- Mechanism design blocked until 10E.1B passes

