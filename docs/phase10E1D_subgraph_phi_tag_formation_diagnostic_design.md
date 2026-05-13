# Phase 10E.1D — Subgraph / Phi-Driven Tag Formation Diagnostic Design

**Date:** 2026-05-13
**Status:** Design only. No implementation. No runner change. No mechanism change.
**Blocked by:** 10E.1C verdict = null_for_current_h_descriptor (commit ec1a8ab)

---

## One-line framing

> 10E.1C showed that tag formation splits along subgraph geometry and phi projection.
> 10E.1D asks: is tag formation driven by local stimulus geometry (phi/surprise),
> or does historical context (h[u]) survive when we control for phi?

Not "which predictor wins globally" — "what is the actual upstream of tag formation."

---

## Background

10E.1C (commit ec1a8ab) key findings:

- LL subgraph: 4/4 seeds h_tag_ratio > 1.0, novelty inverse/null — systematic inversion
- RL/RR: seed-dependent direction
- seed123/999: tagged connections have higher phi than untagged (phi-driven pattern)
- seed42/77: tagged connections have lower phi than untagged (novelty-consistent pattern)
- inversion_global_fraction for seed123/999 ≈ 0.333 — not global, subgraph-local
- surprise_factor more predictive than novelty in seed123/999 aggregate

Two competing explanations:

**H1 — Phi/stimulus geometry dominant:**
Tag formation follows where the stimulus lands (high phi connections).
Historical context (h[u]) is irrelevant or secondary.
The novelty signal in seed42/77 is a coincidence: their h topology happens
to anti-correlate with phi projection.

**H2 — Local historical context survives:**
Within matched phi bins, novelty still predicts tag formation.
The global inversion is a composition artifact: high-phi connections in
seed123/999 happen to also have high h, so novelty inverts at the aggregate
level but not within phi-controlled strata.

10E.1D distinguishes these by stratifying within phi bins and within subgraphs.

---

## Diagnostic axes

### Axis 1 — LL systematic inversion

LL (L→L, same-side recurrent) inverts in 4/4 seeds. Investigate why.

Per seed, LL connections only:
- h_conn distribution (mean, std, p10–p90)
- phi_conn distribution
- surprise_factor distribution
- baseline_weight_abs distribution
- tag_rate
- auc_novelty, auc_phi, auc_surprise, auc_baseline_weight
- event_pair_dW_l1 for tagged vs untagged

Question: do LL connections have systematically higher h (more history) than
cross-side connections? If yes, novelty_factor is compressed near zero for LL,
making it a poor discriminator. This would be a descriptor range problem, not
a mechanism problem.

### Axis 2 — RR seed split

RR passes in seed42/77 but inverts in seed123. Investigate the h/phi difference.

Per seed, RR connections only:
- h_conn distribution
- phi_conn distribution
- h_tag_ratio
- phi_tag_ratio
- auc_novelty, auc_phi, auc_surprise

Question: do seed123/999 have higher phi projection onto high-h RR connections
compared to seed42/77? If yes, the RR split is a phi-coverage artifact.

### Axis 3 — Phi as predictor

For each seed × event_type × subgraph, rank all predictors:
- auc_phi (phi_conn predicting tag_presence)
- auc_surprise (surprise_factor)
- auc_novelty (novelty_factor)
- auc_h_inverted (-h_conn)
- auc_baseline_weight (baseline_weight_abs)

If phi/surprise consistently beats novelty in seed123/999 and LL/RR:
verdict = phi_surprise_driven_tag_formation.

### Axis 4 — Matched-phi novelty diagnostic

Within narrow phi bins (e.g., quartiles of phi_conn), compute:
- auc_novelty within each bin
- auc_surprise within each bin

If novelty survives within phi bins (auc > 0.5 in most bins):
verdict = local_historical_context_signal — history matters after controlling
for stimulus geometry.

If novelty disappears within phi bins:
verdict = stimulus_geometry_dominant — phi explains the tag formation pattern,
history is not adding independent information.

### Axis 5 — Raw plasticity layer

Use event_pair_dW to check whether the split is upstream of tag accumulation.

Per seed × subgraph:
- event_pair_dW_l1 for tagged vs untagged connections
- auc: does dW magnitude predict tag_presence?
- correlation between phi_conn and abs(event_pair_dW)
- correlation between h_conn and abs(event_pair_dW)

If the phi/h split is already visible in dW:
root is in 9C event-pair plasticity geometry, not tag accumulation.
This would mean the tag rule is working correctly — it is just accumulating
what 9C produces, and 9C is phi-geometry-dependent.

If dW does not split but tag_presence does:
the tag accumulation gate itself is the locus of the asymmetry.

---

## Output schema

Summary CSV grouped by:
- seed, arm, event_type, subgraph

Fields per row:
- n_connections, n_tagged, tag_rate
- h_tag_ratio, phi_tag_ratio, surprise_tag_ratio
- mean_h_tagged, mean_h_untagged
- mean_phi_tagged, mean_phi_untagged
- mean_surprise_tagged, mean_surprise_untagged
- auc_novelty, auc_phi, auc_surprise, auc_h_inverted, auc_baseline_weight
- shuffle_percentile_novelty, shuffle_percentile_phi, shuffle_percentile_surprise
- matched_phi_q1_auc_novelty, matched_phi_q2_auc_novelty
- matched_phi_q3_auc_novelty, matched_phi_q4_auc_novelty
- dW_l1_tagged, dW_l1_untagged, dW_l1_ratio
- auc_dW_predicts_tag
- best_predictor
- subgraph_verdict

Cross-seed summary:
- n_seeds_phi_beats_novelty
- n_seeds_novelty_survives_phi_control
- n_seeds_dW_split_matches_tag_split
- LL_inversion_explanation
- final_verdict

---

## Decision rules

| finding | verdict | next step |
|---|---|---|
| phi/surprise beats novelty in seed123/999 and LL/RR; novelty disappears within phi bins | stimulus_geometry_dominant | inspect 9C event-pair geometry; redesign history descriptor to be phi-independent |
| novelty survives within matched phi bins in ≥3/4 seeds | local_historical_context_signal | 10E.2 local history descriptor design (phi-conditioned novelty) |
| dW split matches tag split across subgraphs | dW_geometry_root | 9C event-pair plasticity geometry is the upstream; tag rule is downstream |
| LL inversion explained by h compression (h_conn near 1.0 for all LL) | LL_h_saturation | exclude LL from novelty analysis; test on cross-side subgraphs only |
| phi/surprise beats novelty globally, no subgraph where novelty survives | null_for_novelty_descriptor | redesign history descriptor; consider event-gated h or shorter τ |

**10E.2 is blocked** until 10E.1D returns `local_historical_context_signal`
or a clear path to a revised descriptor.

---

## Secondary diagnostics (informative, not gates)

- **baseline_weight_abs as predictor**: does connection strength predict tagging
  independently of h or phi? If yes, the tag rule has a weight-magnitude bias.
- **event_pair_dW sign distribution**: are tagged connections predominantly
  potentiated or depressed? Does this differ between L and R events?
- **phi × h interaction**: is there a phi × h interaction term that predicts
  tagging better than either alone? This would suggest a multiplicative
  (not additive) relationship.
- **LL h saturation check**: compute mean h_norm for LL vs RL/RR connections.
  If LL h_norm is compressed near 1.0, novelty_factor ≈ 0 for all LL connections,
  making discrimination impossible regardless of mechanism.

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
- 10E.1D is diagnostic; it produces a verdict and a stratified picture,
  not a mechanism.
