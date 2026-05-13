# Phase 10D.4 — Historical Context Candidate Diagnostics Design (Revised)

**Status:** Design only — no implementation, no experiments
**Depends on:** 10D.2 (h[u] stores warmup history), 10D.3 (h[u] not directly aligned with tag/capture)
**Inherits from:** `aniva_external_alignment_research.md`
**Branch:** phase10-closed-loop-event-history

---

## Revision Note (2026-05-13)

This document supersedes the prior 3-candidate design. After cross-disciplinary
external research (ALife, computational neuroscience, open-ended learning),
the candidate set is expanded from 3 to 5, and biological / ALife alignment
boundaries are added. Reasoning:

1. The original `surprise_conn = tag * |phi − h_norm|` is **surprise magnitude**,
   not surprise novelty or learning progress. Multiple independent literatures
   (Schultz RPE, Schmidhuber compression progress, Hung 2023 surprise novelty)
   converge on: instantaneous error magnitude is the wrong driver — its sign,
   rarity, or rate of decrease is what matters.
2. The original `surprise_conn` used `abs()`, discarding the **sign** that
   biology preserves (positive RPE → LTP, negative RPE → LTD).
3. The `h_tag_ratio < 1.0` finding from 10D.3 is **not anomalous** — it is
   consistent with BCM sliding threshold, STC heterosynaptic inhibition
   (Sajikumar 2017), VTA-hippocampal novelty loop (Lisman-Grace 2005), and
   Surprise Novelty (Hung 2023). Five independent lines predict it.

---

## Positioning

10D.4 is **candidate diagnostics only**.

- Not a gate.
- Not a capture redesign.
- Not τ tuning.
- Does not modify `life_core.py`.
- Does not modify 9D mechanism.
- Does not write to `slow_weight`.
- Does not introduce LLM, external evaluator, or fitness function.
- Does not make digital life / consciousness / personhood claims.

The question 10D.4 answers:

> Among five historical-context candidate signals, which is most aligned
> with tag/capture across seeds and arms?

---

## Evidence Inherited from 10D.3

| Metric | Seed 42 | Seed 77 | Verdict |
|--------|---------|---------|---------|
| H1: closed_vs_divergent_h_l1 | 7.982 >> 0.557 | 3.725 >> 0.525 | PASS |
| D1: mean_h_tag_cosine | 0.035 | 0.064 | mixed |
| D2: mean_h_capture_corr | −0.015 | +0.005 | FAIL |
| h_tag_ratio | 0.834 | 0.803 | < 1.0 both |

**Reinterpretation after external research:**
`h_tag_ratio < 1.0` is not an anomaly. It is the predicted signature of
capture firing preferentially in historically low-activity regions —
a *novelty* signal. Five independent literatures converge on this
interpretation (see `aniva_external_alignment_research.md`).

---

## Biological / ALife Alignment

| Observation | External literature explanation |
|-------------|----------------------------------|
| `h_tag_ratio < 1.0` | BCM sliding threshold: high history → θ_M up → harder LTP |
| `h_tag_ratio < 1.0` | STC heterosynaptic inhibition (Sajikumar 2017): prior 10-40 min high activity **blocks** tag |
| novelty / surprise framing | VTA-HC novelty loop (Lisman-Grace 2005): novelty = deviation from familiar baseline |
| avoid noisy-TV trap | Surprise Novelty (Hung 2023): reward error rarity, not error magnitude |
| multi-timescale eligibility | BTSP (Bittner-Magee 2017) τ ≈ 0.7-1.3s; BCM τ ≈ 10 min; STC τ ≈ 1h |

**Framing:**
- `background_h` represents a **familiarity map**, not an importance map.
- Tag may fire preferentially in **historically low-activity regions**.
- Capture should prioritize *current event deviation from historical baseline*,
  not *sheer historical activity*.
- "h 越高 → capture 越多" 是错误的先验；应当检验其反面或其偏差。

---

## Five Candidate Signals

### 1. Background Alignment (baseline — from 10D.3)

```
h_conn = 0.5 * (h[src] + h[tgt])
background_alignment = cosine(h_conn, tag_abs)
```

Baseline for comparison. Expected weak/zero (confirmed by 10D.3).

### 2. Novelty (unchanged)

```
h_norm_conn = h_conn / (max(h_conn) + ε)
novelty_conn = tag_abs * (1 - h_norm_conn)
```

**Biological basis:** BCM sliding threshold + STC heterosynaptic inhibition.
High-h regions have elevated θ_M and blocked tag formation; low-h regions
are in a "quiet band" where events can cleanly leave marks.

**Diagnostics:**
- `novelty_mass` = sum(novelty_conn)
- `novelty_alignment` = cosine(novelty_conn, slow_delta_abs)
- `novelty_slow_corr` = Pearson(novelty_conn, slow_delta_abs)
- `novelty_ratio` = novelty_mass / (tag_mass + ε)
- `background_vs_novelty_delta` = novelty_alignment − background_alignment

### 3. Surprise Magnitude (unchanged — explicitly labeled as magnitude only)

```
phi_conn = 0.5 * (phi[src] + phi[tgt])
surprise_conn = tag_abs * abs(phi_conn - h_norm_conn)
```

**Explicit label:** this is surprise *magnitude*, not surprise novelty or
learning progress. It records "how far the current activation deviates from
background" without sign or rarity. Kept as a baseline for comparison against
the signed and rarity-based candidates below.

**Diagnostics:**
- `surprise_mass`, `surprise_alignment`, `surprise_slow_corr`,
  `surprise_ratio`, `background_vs_surprise_delta`

### 4. Signed Surprise (NEW)

```
signed_delta_conn  = phi_conn - h_norm_conn
positive_surprise  = tag_abs * max(0, signed_delta_conn)
negative_surprise  = tag_abs * max(0, -signed_delta_conn)
```

**Biological basis:** Schultz dopamine RPE is bidirectional —
positive RPE drives LTP, negative RPE drives LTD. BCM `φ(y, θ_M)` also
changes sign across the threshold. The original `abs()` candidate
discards this most-essential biological semantic.

**Two complementary signals:**
- `positive_surprise`: event drives current activity *above* historical baseline
  → "事件打进了历史相对低活动的区域" → predicted to align with capture
- `negative_surprise`: event drives current activity *below* historical baseline
  → may align with tag erasure / LTD-like negative slow_delta

**Diagnostics (each computed for both pos and neg):**
- `pos_surprise_mass`, `neg_surprise_mass`
- `pos_surprise_alignment` = cosine(positive_surprise, max(0, slow_delta))
- `neg_surprise_alignment` = cosine(negative_surprise, max(0, -slow_delta))
- `signed_surprise_slow_corr` = Pearson(signed_delta_conn * tag_abs, slow_delta)
  *(no abs on either side — preserves sign)*

### 5. Surprise Novelty / Learning Progress Proxy (NEW)

Two sub-candidates, both designed to **avoid the noisy-TV trap**
where persistent random surprise looks important but isn't.

**5A. Surprise Rarity (rarity of the current surprise distribution)**

```
# For each capture, compute current surprise distribution stats
current_surprise = surprise_conn  (from candidate 3, magnitude form)

# Maintain per-arm running history of surprise_mass values across captures
history_surprise_mass = [..., surprise_mass_t-2, surprise_mass_t-1]

# Rarity = how unusual is the current surprise compared to its own history
surprise_z         = (surprise_mass_t - mean(history)) / (std(history) + ε)
surprise_percentile = rank(surprise_mass_t, history) / len(history)
surprise_tail      = max(0, surprise_z - 1.0)   # only count tail events
```

**Interpretation:** A capture event whose surprise_mass sits in the tail of
this seed/arm's own history is a *rare* event — one that genuinely
departs from "business as usual". Persistent background noise has
high mean surprise but low tail rarity; events have high rarity.

**5B. Compression Progress Proxy**

```
# Between consecutive captures within the same arm:
compression_progress = previous_surprise_mass - current_surprise_mass

# Or rolling version:
progress_trend = mean_diff(surprise_mass over last N captures)
```

**Interpretation:** If surprise_mass is *decreasing* across captures,
the system is "learning" — patterns previously surprising are becoming
familiar. This is a proxy for Schmidhuber's compression progress.

**Explicit caveat:** This is a **proxy**, not true compression progress.
True compression progress requires a predictor model of the dynamics,
which 10D.4 does not build. The proxy only tracks whether surprise_mass
trends down across captures, which is a weak indirect signal.
10D.4 reports this as a diagnostic, not as a claim about learning.

**Diagnostics:**
- `surprise_rarity_mean` = mean(surprise_z) across captures per arm
- `surprise_tail_ratio` = fraction of captures with surprise_tail > 0
- `compression_progress_mean` = mean(compression_progress) across captures
- `rarity_slow_corr` = Pearson(surprise_tail, slow_delta_l1) per capture
- `progress_slow_corr` = Pearson(compression_progress, slow_delta_l1)

---

## Multi-Timescale h Diagnostic

To test whether the 10D.3 D2 failure is a **timescale mismatch** rather
than a structural mismatch, record multiple h[u] traces in parallel
(all read-only, none affect gate/capture/slow_weight):

```
h_tau_500    # fast eligibility (BTSP-like, ~seconds in biology)
h_tau_2000   # intermediate (~tens of seconds)
h_tau_5000   # medium (~minutes)
h_tau_10000  # current (current 10D.3 baseline)
h_tau_20000  # slow (long-term baseline)
```

Each τ contributes its own set of candidate signals (1-5 above).

**Hard boundaries on τ ladder (reiterated, non-negotiable):**

- The τ ladder is a **diagnostic only**.
- Selecting "the best-looking τ" and adopting it as a mechanism parameter
  is **not allowed**.
- If a particular τ improves alignment, the only valid conclusion is:
  *"there exists a timescale mismatch between current h[u] and the
  capture mechanism."*
- Mechanism design (whether to introduce h_fast / h_slow / dual-trace)
  must happen in a **separate document** (e.g., 10D.5 design),
  not be backed into 10D.4 via τ tuning.
- 10D.4 ships a `timescale_mismatch_note` field summarizing the τ ladder
  result; that note feeds the next decision, not the next mechanism.

---

## Experiment Structure (unchanged from prior revision)

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

### Capture-level CSV (one row per capture event per arm per seed per τ)

| Column | Description |
|--------|-------------|
| seed | seed_env |
| arm | closed_loop / exact_replay / divergent_warmup_replay / matched_warmup_control |
| h_tau | which timescale (500 / 2000 / 5000 / 10000 / 20000) |
| capture_index | index within arm |
| capture_step | simulation step at capture |
| tag_mass | sum(abs(tag_cache)) at capture |
| slow_delta_l1 | sum(abs(slow_weight_cache_after − slow_weight_cache_before)) |
| h_tag_cosine | candidate 1 |
| novelty_alignment | candidate 2 |
| surprise_mag_alignment | candidate 3 |
| pos_surprise_alignment | candidate 4a |
| neg_surprise_alignment | candidate 4b |
| signed_surprise_slow_corr | candidate 4 (signed Pearson) |
| surprise_rarity_z | candidate 5A z-score |
| surprise_tail | candidate 5A tail value |
| compression_progress | candidate 5B per-capture |
| rarity_slow_corr_per_arm | cross-capture rarity correlation |
| progress_slow_corr_per_arm | cross-capture progress correlation |
| background_vs_novelty_delta | candidate 2 − candidate 1 |
| background_vs_surprise_delta | candidate 3 − candidate 1 |
| background_vs_signed_surprise_delta | candidate 4 − candidate 1 |
| background_vs_rarity_delta | candidate 5A − candidate 1 |

### Summary CSV (one row per arm per seed per τ)

| Column | Description |
|--------|-------------|
| seed, arm, h_tau | identifiers |
| mean_background_alignment | mean of candidate 1 |
| mean_novelty_alignment | mean of candidate 2 |
| mean_surprise_mag_alignment | mean of candidate 3 |
| mean_pos_surprise_alignment | mean of candidate 4a |
| mean_neg_surprise_alignment | mean of candidate 4b |
| mean_signed_surprise_slow_corr | mean of candidate 4 signed |
| mean_surprise_tail_ratio | fraction of captures in rarity tail |
| mean_compression_progress | mean of candidate 5B |
| h_tag_ratio | mean(h_conn[tagged]) / mean(h_conn[untagged]) |
| candidate_rank | ordered list of candidates by alignment strength |
| timescale_mismatch_note | free-text note on whether a different τ dominates |

---

## Decision Rules

Results determine the next step, not a mechanism:

| Outcome | Next step |
|---------|-----------|
| novelty / signed-surprise / surprise-novelty all beat background in both seeds at any τ | 10D.5 design: surprise-aware diagnostics or default-off candidate gate |
| only one candidate wins cleanly (e.g., novelty only) | 10D.5 design focuses on that single substrate |
| a specific τ (not the default 10000) dominates alignment | write `timescale_mismatch_note`; 10D.4B design addresses multi-timescale h, does **not** adopt the winning τ directly |
| all candidates fail at all τ in both seeds | h[u] family is wrong substrate; reconsider what "history descriptor" means — possibly event-gated traces or activity patterns other than slow EMA |
| seeds disagree | expand to 4-seed diagnostic before any 10D.5 design |
| signed positive surprise aligns with positive slow_delta, signed negative surprise aligns with negative slow_delta | strong evidence for bidirectional RPE-like mechanism; 10D.5 should treat as two separate substrates |

**No gate implementation from 10D.4 directly, regardless of outcome.**
**No τ selected as mechanism parameter from τ ladder.**

---

## Aniva Red Lines (explicit for this phase)

- Do not introduce external fitness, reward, or evaluator.
- Do not introduce LLM, foundation model, or any external "interestingness" judge.
- Do not use novelty / surprise as a global objective function inserted into
  the core dynamics. 10D.4 only measures alignment; it does not steer.
- 10D.4 remains offline diagnostics: no `life_core.py` modification,
  no `slow_weight` writes, no gate change, no 9D modification.
- Do not enter 10D.5 implementation from this document.
- Do not make digital life / consciousness / personhood claims.
- Do not tune τ for performance.
- Do not claim Schmidhuber compression progress; 5B is explicitly a proxy.

---

## What 10D.4 Does NOT Do

- Does not implement a capture gate.
- Does not implement a new trace in `life_core.py`.
- Does not modify the existing h[u] update rule.
- Does not change τ from 10000 in the primary h[u].
- The multi-τ traces run in parallel to the primary h[u], not replacing it.
- Does not evaluate whether any candidate is "good enough" — only ranks alignment.

---

## Next Document (written only after 10D.4 runner + results complete)

`docs/phase10D4_historical_context_candidate_diagnostics_runner_notes.md`

Which candidate (if any) to promote to 10D.5 substrate is a decision for
that notes document, informed by the ranked alignment across seeds, arms,
and τ values.
