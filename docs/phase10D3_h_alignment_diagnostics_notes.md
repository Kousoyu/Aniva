# Phase 10D.3 — h[u] Alignment Diagnostics: Results Notes

**Date:** 2026-05-12
**Branch:** phase10-closed-loop-event-history
**Runner:** `aniva/experiments/exp10D3_h_alignment_diagnostics.py`
**Results:** `results/phase10D3_h_alignment_seed42_77_*.csv/json`

---

## Setup

- Seeds: 42, 77
- Units: 300, Steps: 7500, Warmup: 2000
- h[u] τ = 10000, default-off, **read-only** (does not affect gate/capture/slow_weight)
- Four arms: closed_loop, exact_replay, divergent_warmup_replay, matched_warmup_control

---

## Protocol Results

| Check | Seed 42 | Seed 77 |
|-------|---------|---------|
| P1 events > 0 | OK (12) | OK (14) |
| P2 exact replay complete | OK | OK |
| P3 no hash mismatches | OK | OK |
| P4 captures > 0 | OK (10) | OK (11) |
| P5 closed_vs_exact_h_l1 < 1e-6 | OK (0.0) | OK (0.0) |
| P6 warmup divergence > 1e-8 | OK (0.089) | OK (0.114) |
| P7 warmup weights frozen | OK (0.0) | OK (0.0) |

**Overall: ALL PASS**

---

## Diagnostic Results

| Metric | Seed 42 | Seed 77 | Criterion |
|--------|---------|---------|-----------|
| H1: closed_vs_divergent_h_l1 | 7.982 | 3.725 | > threshold (0.557 / 0.525) → **PASS** |
| D1: mean_h_tag_cosine (closed) | 0.0349 | 0.0638 | > 0.05 → **FAIL / PASS** |
| D2: mean_h_capture_corr (closed) | −0.0148 | 0.0053 | > 0.05 → **FAIL / FAIL** |
| D1: h_tag_ratio | 0.834 | 0.803 | > 1.0 expected → **FAIL / FAIL** |

---

## Interpretation

### What passed

**H1 PASS (both seeds):** h[u] diverges significantly between closed_loop and divergent_warmup_replay.
The "film" did capture something — warmup history is encoded in h[u] and differs when warmup differs.
This confirms h[u] is a real historical trace, not noise.

### What failed

**D1 borderline (1/2 seeds):** h[u]'s shape is only weakly aligned with the tag vector.
Seed 77 barely passes (0.064 > 0.05); seed 42 fails (0.035 < 0.05).
Not a consistent signal.

**D2 consistently fails (0/2 seeds):** h[u] does not predict which connections get captured.
Pearson correlation between h_conn and |slow_delta| is near zero or negative.
The "film" does not predict where the camera shutter fires.

**h_tag_ratio < 1.0 (both seeds):** Tagged units actually have *lower* h[u] than untagged units.
This is the opposite of what we'd expect if h[u] tracked "important" or "active" units.
Possible explanation: tagged units are those that fired strongly during the event window,
but h[u] with τ=10000 is dominated by the long warmup baseline — units that were
*consistently* active during warmup (not just during events) have higher h[u].

---

## Core Finding

> h[u] records warmup activity history, but that history is **not aligned** with the
> tag/capture mechanism. The "film" captured the wrong scene.

h[u] at τ=10000 is a slow average over 2000 warmup steps. The tag/capture mechanism
fires on short-timescale event responses. These two timescales are mismatched:
- h[u] reflects *who was active during warmup* (background baseline)
- tag reflects *who responded to the specific event* (foreground signal)

---

## Implications for 10D.4

The current h[u] (τ=10000, warmup-dominated) is **not a useful prior** for the capture gate.
Before designing an h-gate, the question is: what kind of history *would* be useful?

Options:
1. **Shorter τ** — h[u] with τ~100-500 would track recent event-window activity, not warmup baseline. More likely to align with tag.
2. **Event-gated h** — only update h[u] during event windows, not during warmup. Directly tracks event-response history.
3. **Drop h-gate entirely** — if h[u] doesn't align with capture, there's no principled basis for an h-gate. Move to a different mechanism.

**Recommendation:** Do not proceed to h-gate (10D.4) with current τ=10000.
Either redesign h[u] (shorter τ or event-gated) or pivot to a different direction.

---

## Next Step

Discuss with Max before entering 10D.4.
The 10D.3 result is a meaningful negative: the diagnostic infrastructure works,
the "film" exists, but it's filming the wrong thing.
