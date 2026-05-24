# Phase 10D.3 → 10D.4 Direction Decision

**Date:** 2026-05-13
**Status:** Decision document — no implementation, no experiments

---

## 10D.3 Evidence Summary

| Metric | Seed 42 | Seed 77 | Verdict |
|--------|---------|---------|---------|
| H1: closed_vs_divergent_h_l1 | 7.982 >> 0.557 | 3.725 >> 0.525 | PASS |
| D1: mean_h_tag_cosine | 0.035 | 0.064 | mixed |
| D2: mean_h_capture_corr | −0.015 | +0.005 | FAIL |
| h_tag_ratio | 0.834 | 0.803 | < 1.0 both |

**Core conclusion:**
Current τ=10000 h[u] is a valid historical background trace, but not a direct positive
capture prior. It records background activity history; tag/capture reflects event-window
foreground response. The two are semantically and temporally mismatched.

---

## What This Rules Out

- **Do not connect current h[u] to capture gate.** D2 fails; h[u] does not predict
  where slow_weight delta lands.
- **Do not tune τ to get better-looking numbers.** τ sensitivity is a diagnostic tool,
  not a mechanism selection criterion.
- **Do not enter 10D.4 implementation yet.** The gate design has no validated prior.
- **Do not modify 9D default mechanism.** The capture mechanism itself is not the problem.

---

## The Deeper Signal: h_tag_ratio < 1.0

h_tag_ratio < 1.0 means tagged connections fall in regions where h[u] is *lower* than
average. This is not noise — it is a consistent finding across both seeds.

Interpretation: tag/capture is not rewarding "familiar" regions (high background h).
It is firing in regions that are historically *less* active — regions where the current
event is relatively novel against the individual's background.

This reframes the question. The relevant signal is not:

> "h[u] is high → this region is important → capture here"

It is:

> "event response is high AND h[u] is low → this region is being activated in a way
> that departs from background → this is worth capturing"

In other words: **novelty against historical background**, not familiarity.

---

## Candidate Directions for 10D.4

### A. τ Sensitivity Diagnostic

Test τ = 2000 / 5000 / 10000 / 20000 and measure D1/D2 alignment at each.

- **Purpose:** Determine whether the D1/D2 failure is purely a timescale mismatch,
  or whether h[u] is structurally the wrong signal regardless of τ.
- **Risk:** Easy to slide into τ tuning. Must be treated as diagnostic only.
- **Role:** Supporting evidence, not primary direction.

### B. Event-Gated Historical Trace

h_event[u] updates only during event influence windows, not during warmup baseline.

- **Purpose:** Record event-relevant history rather than background baseline.
  Since tag is also event-driven, h_event may align better with tag/capture.
- **Risk:** If the event window definition is too loose, h_event becomes a slow
  duplicate of the event trace itself.
- **Role:** Secondary candidate. Worth a diagnostic pass.

### C. Novelty / Surprise Trace

Motivated directly by h_tag_ratio < 1.0.

Candidate formulations:
```
novelty_conn  = tag_conn * (1 - h_conn_normalized)
surprise_conn = tag_conn * abs(event_response_conn - h_conn)
```

- **Interpretation:** Capture is not about reinforcing familiar pathways.
  It is about marking where the current event departed from the individual's
  background — where experience is genuinely new.
- **Alignment with Aniva vision:** "经历改变个体" — experience changes the individual
  precisely when it hits regions that were not already active. A life that only
  reinforces what it already knows is not growing.
- **Risk:** Requires defining "event_response_conn" cleanly. Needs careful
  operationalization before implementation.
- **Role:** Primary candidate. Most information-rich direction given current evidence.

### D. Dual-Trace Model

Two separate traces:
- background_h[u]: current τ=10000, long-term baseline
- event_h[u]: event-window slow trace, event-relevant history

novelty = event_h − background_h, or event_response − background_h

- **Risk:** Mechanism complexity increases significantly. Premature without
  first validating that either trace alone is useful.
- **Role:** Future consideration only. Do not design yet.

---

## Recommended Decision

**10D.4 is not h-gate implementation. It is:**

> Phase 10D.4 — Historical Context Candidate Diagnostics

10D.4 runs offline diagnostics comparing four candidate signals against tag/capture:

1. **background alignment:** h_conn vs tag (baseline — already measured in 10D.3)
2. **novelty alignment:** tag × (1 − h_conn_normalized) vs slow_delta
3. **surprise alignment:** tag × |event_response_conn − h_conn| vs slow_delta
4. **event-gated alignment:** h_event_conn vs tag (if event-gated h is implemented)

No gate is implemented. No mechanism is changed. The question is:
which of these candidate signals has the strongest alignment with actual capture?

**Priority order:**
1. Novelty / surprise diagnostics (C) — primary
2. Event-gated h diagnostics (B) — secondary
3. τ sensitivity (A) — supporting only
4. No capture gate implementation

---

## Next Document

`docs/phase10D4_historical_context_candidate_diagnostics_design.md`

This document will specify the exact operationalization of novelty_conn and
surprise_conn, the diagnostic metrics, and the pass criteria for 10D.4.
