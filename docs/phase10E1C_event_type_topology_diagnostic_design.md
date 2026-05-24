# Phase 10E.1C — Event-Type / Topology Diagnostic Design

**Date:** 2026-05-13
**Status:** Design only. No implementation. No runner change. No mechanism change.
**Blocked by:** 10E.1B verdict = unstable_event_type_confound (commit 18f3507)

---

## One-line framing

> 10E.1B showed that global novelty_factor is not a universal tag-formation predictor.
> 10E.1C asks: does the signal survive when we control for event type and subgraph topology?

Not "does history matter" — "where does history matter, and why does it invert elsewhere."

---

## Background

10E.1B (commit 18f3507) final state:

- Protocol: 28/28 PASS, P7 exact tag hash clean
- seed42: pass (auc_novelty=0.565, shuffle=1.00, h_tag_ratio=0.949)
- seed77: borderline (auc_novelty=0.521, shuffle=0.95, h_tag_ratio=1.008)
- seed123: severe inverse (auc_novelty=0.428, shuffle=0.00, h_tag_ratio=1.242)
- seed999: severe inverse (auc_novelty=0.431, shuffle=0.00, h_tag_ratio=1.285)
- R-events null in 3/4 seeds (seed77, seed123, seed999)
- seed123/999 best_predictor = surprise, not novelty

The split is structurally clean:
- seed42/77: h_tag_ratio < 1.01 → tagged connections have lower h → novelty predicts tagging
- seed123/999: h_tag_ratio > 1.24 → tagged connections have higher h → novelty inverts

Two hypotheses for the inversion:

**H1 — Topology composition confound:**
The aggregate novelty signal is driven by subgraph composition, not local history.
If R-events mostly activate subgraphs where h is globally high, the aggregate
will invert even if novelty holds within each subgraph.

**H2 — Event-response asymmetry:**
L and R stimuli project onto different connection populations with different
h distributions. R-event phi mass lands on connections that are already
well-activated (high h), so novelty_factor is systematically low for R-tagged
connections regardless of seed.

These are not mutually exclusive. 10E.1C distinguishes them by stratifying
within subgraph and within event type.

---

## Diagnostic axes

### Axis 1 — Event-type split

For each seed × arm:
- L events only
- R events only
- simultaneous events (if present)

Per group: tag_rate, auc_novelty, auc_surprise, h_tag_ratio, novelty_tag_ratio,
shuffle_percentile_novelty, shuffle_percentile_surprise, best_predictor.

Question: does novelty hold for L across all 4 seeds even when R collapses?
If yes → event-response asymmetry, not global failure.

### Axis 2 — Directional subgraph split

Connection subgraphs by (src_region, tgt_region):
- LL, LR, RL, RR
- LM, ML, RM, MR, MM (if region M exists)

Per subgraph: same fields as Axis 1.

Question: does R-event null come from a specific subgraph (e.g., RR or RL),
or is it uniform across all subgraphs touched by R events?
If concentrated in one subgraph → topology composition confound.
If uniform → event-response asymmetry.

### Axis 3 — Stimulus geometry / phi mass

Per seed × event_type:
- phi_conn distribution (mean, std, percentiles)
- phi_mass total (sum of abs phi over all connections)
- phi_mass by subgraph
- h_conn distribution for connections with phi > 0 vs phi = 0

Question: does R stimulus project onto connections with systematically higher h
than L stimulus? If yes → the inversion is a phi-coverage artifact, not a
historical-context effect.

### Axis 4 — h distribution topology at event time

Per seed × event_type × subgraph:
- mean h for tagged connections
- mean h for untagged connections
- h_tag_ratio
- h distribution percentiles (p10, p25, p50, p75, p90)

Question: do seed123/999 have a different h topology at warmup end that
reverses the novelty relationship globally, or only in specific subgraphs?
If global reversal → seed_topology_dependent_history.
If subgraph-local → topology composition confound.

### Axis 5 — Tag formation mechanics

Per seed × event_type × subgraph:
- event_pair_dW L1 (total plasticity mass per event)
- tag_delta mass (total tag increment per event)
- tag_presence rate
- raw dW sign distribution (fraction positive vs negative)
- correlation between h_conn and event_pair_dW

Question: is the novelty inversion in seed123/999 visible in raw dW, or only
in tag_presence? If dW also inverts → the plasticity rule itself is
h-topology-dependent. If only tag_presence inverts → the tag gate is the
locus of the asymmetry.

### Axis 6 — Matched-subgraph novelty diagnostic

Within each (seed, event_type, subgraph) cell:
- split connections into high-h vs low-h (median split on h_conn)
- compare tag_rate between high-h and low-h halves
- compute within-subgraph auc_novelty

Question: does novelty predict tagging within matched subgraph even when
aggregate inverts? If yes → the global inversion is purely compositional,
and local historical context has genuine predictive value.
This is the key gate for deciding whether to proceed to 10E.2 local design.

---

## Output schema

Summary CSV grouped by:
- seed
- arm
- event_type
- src_region
- tgt_region (subgraph)

Fields per row:
- n_connections
- n_tagged
- tag_rate
- mean_h_tagged
- mean_h_untagged
- h_tag_ratio
- novelty_tag_ratio
- auc_novelty
- auc_surprise
- auc_h_inverted
- phi_mass
- phi_mass_per_connection
- tag_delta_mass
- event_pair_dW_l1
- shuffle_percentile_novelty
- shuffle_percentile_surprise
- within_subgraph_auc_novelty (high-h vs low-h split)
- verdict

Cross-seed summary:
- n_seeds_L_pass
- n_seeds_R_pass
- n_seeds_subgraph_confound
- n_seeds_event_asymmetry
- n_seeds_within_subgraph_novelty_holds
- final_verdict

---

## Decision rules

| finding | verdict | next step |
|---|---|---|
| R-events collapse in specific subgraph(s) only | topology_composition_confound | matched-subgraph diagnostic (Axis 6) |
| R-events collapse uniformly across subgraphs | event_response_asymmetry | inspect phi/dW geometry (Axis 3/5) |
| seed123/999 invert globally (all subgraphs) | seed_topology_dependent_history | seed-conditioned model; no universal novelty rule |
| novelty holds within matched subgraph in ≥3/4 seeds | local_historical_context_signal | proceed to 10E.2 local diagnostic design |
| L-events pass in ≥3/4 seeds, R-events null in ≥3/4 seeds | event_type_asymmetry_confirmed | redesign: L-only or event-gated history descriptor |
| no stable signal in any stratification | null_for_current_h_descriptor | design alternative history descriptor (shorter τ, event-gated h); not tag rule |

**10E.2 is blocked** until 10E.1C returns `local_historical_context_signal`
or `event_type_asymmetry_confirmed` with a clear L-only path.

---

## Secondary diagnostics (informative, not gates)

- **h_tag_ratio trajectory across seeds**: does h_tag_ratio correlate with
  network density, E/I ratio, or warmup event count?
- **tag_rate by subgraph**: is tagging concentrated in specific subgraphs
  regardless of event type?
- **surprise_factor as alternative**: seed123/999 show auc_surprise ≈ 0.55–0.57
  with shuffle_pct = 0.95–1.00. Is surprise a more stable predictor than novelty
  across seeds? If yes, 10E.2 should test surprise_factor, not novelty_factor.
- **divergent arm within subgraph**: does the divergent arm show different
  within-subgraph auc than closed_loop? If yes, h trajectory matters locally
  even when global aggregate is noisy.

---

## Boundaries

- No mechanism changes.
- No tag rule changes.
- No event_pair_plasticity changes.
- No consolidation changes.
- No τ tuning.
- No h[u] redesign.
- No novelty gate.
- No capture redesign.
- No claim of digital life / consciousness / personhood.
- 10E.1C is diagnostic; it produces a verdict and a stratified picture,
  not a mechanism.
