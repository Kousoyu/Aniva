# Phase 10D.4A — Candidate Diagnostics Smoke: Scope Freeze

**Status:** Scope freeze document — no implementation, no experiments
**Parent design:** `docs/phase10D4_historical_context_candidate_diagnostics_design.md`
**Branch:** phase10-closed-loop-event-history

---

## Why a Scope Freeze

The full 10D.4 design covers 5 candidates × 5 τ values × 4 arms × 2 seeds.
That is a large space. Running it all at once risks:

1. Drowning in output before the basic signal is confirmed
2. τ ladder results contaminating candidate interpretation
3. rarity/progress proxies adding noise before the base candidates are stable
4. Debugging a large runner when a small one would have caught the same issue

10D.4A is the **first probe**: one τ, four candidates, three arms.
It answers one question before expanding:

> In the current h[u] (τ=10000), do novelty or signed_surprise
> beat background alignment in both seeds?

If yes → 10D.4B adds rarity/progress.
If no → inspect formulas before expanding.

---

## Fixed Scope

### Seeds
42, 77

### Arms
| Arm | Role |
|-----|------|
| closed_loop | Primary: candidate signals measured here |
| exact_replay | Protocol check: signals must match closed_loop |
| divergent_warmup_replay | H1 check: signals diverge with warmup? |
| matched_warmup_control | Baseline only; not included in candidate ranking |

### h τ
**10000 only.** No τ ladder in 10D.4A.

### Candidates
| # | Name | Formula |
|---|------|---------|
| 1 | background_alignment | `cosine(h_conn, tag_abs)` |
| 2 | novelty | `tag_abs * (1 - h_norm_conn)` |
| 3 | surprise_magnitude | `tag_abs * abs(phi_conn - h_norm_conn)` |
| 4a | positive_surprise | `tag_abs * max(0, phi_conn - h_norm_conn)` |
| 4b | negative_surprise | `tag_abs * max(0, h_norm_conn - phi_conn)` |
| 4c | signed_surprise_corr | `Pearson(tag * (phi_conn - h_norm_conn), slow_delta)` |

where:
```
h_conn      = 0.5 * (h[src] + h[tgt])
h_norm_conn = h_conn / (max(h_conn) + ε)
phi_conn    = 0.5 * (phi[src] + phi[tgt])   # activation at capture time
```

---

## Explicitly Excluded from 10D.4A

| Excluded | Reason |
|----------|--------|
| surprise_rarity (5A) | Needs cross-capture history; wait for base CSV to stabilize |
| compression_progress proxy (5B) | Same; also needs multiple captures to trend |
| τ ladder (500/2000/5000/20000) | Would expand interpretation space 5× before base signal confirmed |
| event-gated h | Not implemented; separate design needed |
| New traces in life_core.py | 10D.4A is read-only diagnostics |
| Capture gate changes | Not in scope for any 10D.4 phase |
| 9D mechanism changes | Not in scope |

---

## Output Specification

### Capture-level CSV

One row per capture event per arm per seed.

| Column | Description |
|--------|-------------|
| seed | seed_env |
| arm | arm name |
| capture_index | index within arm |
| capture_step | simulation step |
| tag_mass | sum(abs(tag_cache)) at capture |
| slow_delta_l1 | sum(abs(slow_weight_after − slow_weight_before)) |
| h_tag_cosine | candidate 1 |
| novelty_alignment | cosine(novelty_conn, slow_delta_abs) |
| surprise_mag_alignment | cosine(surprise_conn, slow_delta_abs) |
| pos_surprise_alignment | cosine(positive_surprise, max(0, slow_delta)) |
| neg_surprise_alignment | cosine(negative_surprise, max(0, -slow_delta)) |
| signed_surprise_slow_corr | Pearson(tag*(phi−h_norm), slow_delta) |
| h_tag_ratio | mean(h_conn[tagged]) / mean(h_conn[untagged]) |
| novelty_ratio | novelty_mass / (tag_mass + ε) |
| surprise_ratio | surprise_mass / (tag_mass + ε) |

### Summary CSV

One row per arm per seed.

| Column | Description |
|--------|-------------|
| seed | seed_env |
| arm | arm name |
| mean_h_tag_cosine | mean over captures |
| mean_novelty_alignment | mean over captures |
| mean_surprise_mag_alignment | mean over captures |
| mean_pos_surprise_alignment | mean over captures |
| mean_neg_surprise_alignment | mean over captures |
| mean_signed_surprise_slow_corr | mean over captures |
| h_tag_ratio | per-arm mean |
| candidate_rank | ordered list by alignment strength (closed_loop only) |
| p1_p7_protocol_pass | True/False |

---

## Success Criteria

10D.4A is complete when:

1. P1-P7 all pass (same protocol as 10D.3)
2. exact_replay matches closed_loop on all candidate signals
3. All candidate alignment values are finite (no NaN/Inf)
4. `candidate_rank` is computed for closed_loop in both seeds
5. No mechanism changed (life_core.py diff = 0)

10D.4A does **not** require any candidate to beat background.
The question is answered either way.

---

## Decision Rules

| Outcome | Next step |
|---------|-----------|
| novelty or signed_surprise beats background in both seeds | 10D.4B: add surprise_rarity and compression_progress |
| only one seed shows improvement | Inspect per-seed topology; do not expand to 10D.4B yet |
| no candidate beats background in either seed | Pause; inspect formulas and phi_conn proxy before expanding |
| positive_surprise aligns with positive slow_delta AND negative_surprise aligns with negative slow_delta | Strong RPE-like signal; note in 10D.4B design |
| exact_replay does not match closed_loop on candidate signals | Protocol failure; fix before interpreting results |

**No 10D.5 design from 10D.4A results alone.**

---

## Relationship to Full 10D.4 Design

10D.4A is a **subset** of the full 10D.4 design. It does not replace it.

| Full 10D.4 | 10D.4A | 10D.4B | 10D.4C |
|------------|--------|--------|--------|
| 5 candidates | 4 (no rarity/progress) | + rarity/progress | — |
| 5 τ values | τ=10000 only | τ=10000 only | + τ ladder |
| 4 arms | 3 (+optional control) | same | same |
| 2 seeds | 2 seeds | 2 seeds | possibly 4 |

The full 10D.4 design document remains the authoritative spec.
10D.4A/B/C are execution phases within it.
