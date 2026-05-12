# Phase 10D.4 — Historical Context Candidate Diagnostics Design

**Status:** Design only — no implementation, no experiments
**Depends on:** 10D.2 (h[u] stores warmup history), 10D.3 (h[u] not directly aligned with tag/capture)
**Branch:** phase10-closed-loop-event-history

---

## Positioning

10D.4 is **candidate diagnostics only**.

- Not a gate.
- Not a capture redesign.
- Not τ tuning.
- Does not modify `life_core.py`.
- Does not modify 9D mechanism.
- Does not write to `slow_weight`.

The question 10D.4 answers:

> If background h[u] is not a positive capture prior, which historical-context
> candidate signal is most aligned with tag/capture?

---

## Evidence Inherited from 10D.3

| Finding | Implication |
|---------|-------------|
| H1 PASS (both seeds) | h[u] is a real historical trace, not noise |
| D1 mixed (0.035 / 0.064) | background h weakly aligned with tag shape |
| D2 FAIL (−0.015 / +0.005) | background h does not predict slow_delta |
| h_tag_ratio < 1.0 (0.834 / 0.803) | tag fires in historically low-h regions |

The h_tag_ratio finding is the key signal. It suggests capture is not reinforcing
familiar pathways — it is marking where the current event departed from background.
This motivates the novelty / surprise framing.

---

## Core Question

```
background h[u]  →  "熟悉度地图"  (familiarity map)
novelty signal   →  "新异性地图"  (novelty map)
surprise signal  →  "预测误差地图" (prediction-error map)
```

Which of these three is the better substrate for capture?

---

## Four Candidate Signals

### 1. Background Alignment (baseline — from 10D.3)

```
h_conn = 0.5 * (h[src] + h[tgt])
background_alignment = cosine(h_conn, tag_abs)
```

Already measured in 10D.3. Retained as baseline for comparison.
Expected: weak positive or near-zero (confirmed by 10D.3).

### 2. Novelty Candidate

```
h_norm_conn = h_conn / (max(h_conn) + ε)   # normalize to [0, 1]
novelty_conn = tag_abs * (1 - h_norm_conn)
```

**Interpretation:** The current event hits a connection that is historically
underactive. The less familiar the region, the higher the novelty weight.

**Motivation:** h_tag_ratio < 1.0 means tag already fires preferentially in
low-h regions. novelty_conn makes this explicit: it amplifies tag signal
precisely where background h is low.

**Diagnostics:**
- `novelty_mass` = sum(novelty_conn)
- `novelty_alignment` = cosine(novelty_conn, slow_delta_abs)
- `novelty_slow_corr` = Pearson(novelty_conn, slow_delta_abs)
- `novelty_ratio` = novelty_mass / (tag_mass + ε)
- `background_vs_novelty_delta` = novelty_alignment − background_alignment

### 3. Surprise Candidate

```
phi_conn = 0.5 * (phi[src] + phi[tgt])   # current activation proxy
surprise_conn = tag_abs * abs(phi_conn - h_norm_conn)
```

**Interpretation:** Capture is proportional to how much the current event
response deviates from the historical baseline — a prediction-error signal.

**Proxy limitation:** `phi_conn` is the activation at capture time, not a
clean "event response" isolated from background. This is a proxy. The design
must record this limitation explicitly in the runner and notes.

A cleaner operationalization would require an event-response delta
(activation at event peak minus pre-event baseline), which is not currently
available in the capture ledger. 10D.4 uses the phi proxy; 10D.5 may
refine if the signal is promising.

**Diagnostics:**
- `surprise_mass` = sum(surprise_conn)
- `surprise_alignment` = cosine(surprise_conn, slow_delta_abs)
- `surprise_slow_corr` = Pearson(surprise_conn, slow_delta_abs)
- `surprise_ratio` = surprise_mass / (tag_mass + ε)
- `background_vs_surprise_delta` = surprise_alignment − background_alignment

### 4. Event-Gated Historical Trace Candidate

`h_event[u]` is **not implemented** in 10D.4.

Design note for future phases (10D.4B or 10D.5):

```
h_event[u] += α_event * (acts[u] - h_event[u])   # only during event windows
```

This would record event-relevant history rather than background baseline.
Since tag is also event-driven, h_event may align better with tag/capture.

10D.4 cannot measure this directly. If novelty/surprise diagnostics are
promising, 10D.4B should implement h_event as a read-only trace and run
the same D1/D2 diagnostics against it.

---

## τ Sensitivity — Supporting Diagnostic Only

τ = 2000 / 5000 / 10000 / 20000 may be tested as a supporting sweep.

**Hard constraint:** τ sensitivity is diagnostic only.
- If alignment improves at a different τ, this means timescale mismatch.
- It does not mean that τ can be tuned into the mechanism.
- A τ that produces better-looking numbers is not a validated mechanism.
- τ selection requires a principled justification, not a grid search result.

---

## Experiment Structure

Reuse the 10D.3 four-arm structure:

| Arm | Purpose |
|-----|---------|
| closed_loop | Primary: all candidate signals measured here |
| exact_replay | Verify h[u] determinism; candidate signals should match closed_loop |
| divergent_warmup_replay | H1 check: do candidate signals diverge with warmup? |
| matched_warmup_control | Baseline: no events, no captures |

10D.4 runner is **not implemented in this document**. This design specifies
what the runner must output when implemented.

---

## Output Specification

### Capture-level CSV (one row per capture event per arm per seed)

| Column | Description |
|--------|-------------|
| seed | seed_env |
| arm | closed_loop / exact_replay / divergent_warmup_replay / matched_warmup_control |
| capture_index | index within arm |
| capture_step | simulation step at capture |
| tag_mass | sum(abs(tag_cache)) at capture |
| slow_delta_l1 | sum(abs(slow_weight_cache_after − slow_weight_cache_before)) |
| h_tag_cosine | cosine(h_conn, tag_abs) — background baseline |
| tag_weighted_h | sum(tag_abs * h_conn) / tag_mass |
| novelty_mass | sum(novelty_conn) |
| novelty_alignment | cosine(novelty_conn, slow_delta_abs) |
| novelty_slow_corr | Pearson(novelty_conn, slow_delta_abs) |
| surprise_mass | sum(surprise_conn) |
| surprise_alignment | cosine(surprise_conn, slow_delta_abs) |
| surprise_slow_corr | Pearson(surprise_conn, slow_delta_abs) |
| background_vs_novelty_delta | novelty_alignment − h_tag_cosine |
| background_vs_surprise_delta | surprise_alignment − h_tag_cosine |

### Summary CSV (one row per arm per seed)

| Column | Description |
|--------|-------------|
| seed | seed_env |
| arm | arm name |
| mean_h_tag_cosine | mean over captures |
| mean_novelty_alignment | mean over captures |
| mean_surprise_alignment | mean over captures |
| mean_novelty_slow_corr | mean over captures |
| mean_surprise_slow_corr | mean over captures |
| h_tag_ratio | mean(h_conn[tagged]) / mean(h_conn[untagged]) |
| novelty_ratio | mean(novelty_mass) / mean(tag_mass) |
| surprise_ratio | mean(surprise_mass) / mean(tag_mass) |
| candidate_rank | novelty / surprise / background / tie — best alignment |

---

## Decision Rules

Results from 10D.4 closed_loop (both seeds) determine the next step:

| Outcome | Next step |
|---------|-----------|
| novelty consistently beats background in both seeds | 10D.5: novelty-aware diagnostics or default-off novelty gate design |
| surprise consistently beats novelty in both seeds | 10D.5: surprise / prediction-error trace design |
| neither beats background in both seeds | h[u] family may be wrong substrate; reconsider capture mechanism |
| seed disagreement | expand to 4-seed diagnostic before any mechanism design |

**No gate implementation from 10D.4 directly, regardless of outcome.**

---

## Boundaries

- Do not change capture gate.
- Do not change slow_weight.
- Do not tune τ for performance.
- Do not enter 10D.5 implementation from this document.

---

## Next Document

`docs/phase10D4_historical_context_candidate_diagnostics_runner_notes.md`
(written after 10D.4 runner is implemented and results are in)
