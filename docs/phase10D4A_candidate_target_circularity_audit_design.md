# Phase 10D.4A — Candidate-Target Circularity Audit Design

**Status:** Design only — no implementation, no experiments
**Depends on:** 10D.4A results (commit `5075d69`)
**Branch:** phase10-closed-loop-event-history

---

## The Problem

10D.4A showed novelty winning by a large margin:

| Candidate | Seed 42 | Seed 77 |
|-----------|---------|---------|
| background | 0.035 | 0.064 |
| novelty | 0.857 | 0.768 |
| surprise_magnitude | 0.734 | 0.697 |
| neg_surprise | 0.605 | 0.649 |
| pos_surprise | 0.345 | 0.257 |

But all winning candidates share a structural property:

```
novelty_conn       = tag_abs * (1 - h_norm_conn)
surprise_mag_conn  = tag_abs * abs(phi_conn - h_norm_conn)
pos_surprise_conn  = tag_abs * max(0, phi_conn - h_norm_conn)
neg_surprise_conn  = tag_abs * max(0, h_norm_conn - phi_conn)
```

Every candidate is `tag_abs × [some factor]`.

The alignment target is:

```
slow_delta_abs = abs(slow_weight_after - slow_weight_before)
```

In the 9D mechanism, `slow_delta` is produced by the capture step which reads
`tag_cache` directly. Therefore `slow_delta_abs` is structurally derived from
`tag_abs`. A vector of the form `tag_abs × anything` will tend to align with
`slow_delta_abs` simply because both contain `tag_abs`.

**The question:** Does novelty beat background because `(1 - h_norm)` adds
genuine historical context, or because `novelty_conn` already contains `tag_abs`
and `slow_delta_abs` is tag-derived?

**The risk:** If the answer is "tag self-alignment", then 10D.4A's high cosines
are a metric artifact, not evidence that h[u] history is useful for capture.

---

## Audit Metrics

### 1. tag_only_baseline

Measure how well `tag_abs` alone aligns with `slow_delta_abs`, without any
historical factor:

```
tag_only_alignment = cosine(tag_abs, slow_delta_abs)
tag_only_corr      = Pearson(tag_abs, slow_delta_abs)
```

**Expected:** likely high (near 1.0), because slow_delta derives from tag.

**Interpretation:** If `tag_only_alignment ≈ novelty_alignment`, then the
historical factor `(1 - h_norm)` added nothing. If `novelty_alignment >
tag_only_alignment`, the factor genuinely improved alignment.

### 2. Factor-Only Metrics

Strip `tag_abs` out and examine the historical factors alone:

```
novelty_factor      = 1 - h_norm_conn
surprise_mag_factor = abs(phi_conn - h_norm_conn)
pos_surprise_factor = max(0, phi_conn - h_norm_conn)
neg_surprise_factor = max(0, h_norm_conn - phi_conn)
```

For each factor, compute:

```
factor_tag_corr  = Pearson(factor, tag_abs)
factor_slow_corr = Pearson(factor, slow_delta_abs)
```

Also compute:
```
tagged_mask = tag_abs > 1e-10
factor_tagged_mean   = mean(factor[tagged_mask])
factor_untagged_mean = mean(factor[~tagged_mask])
top_tag_factor_mean  = mean(factor[top_k_tag_connections])
bot_tag_factor_mean  = mean(factor[bottom_k_tag_connections])
```

**Purpose:** If `factor_slow_corr` is strong even without `tag_abs` as a
multiplier, the historical factor has independent predictive value.
If `factor_slow_corr ≈ 0` but `candidate_alignment` is high, the signal
is entirely from `tag_abs`.

### 3. Residualized Candidate Metrics

Partial out the `tag_abs` contribution from both candidate and target:

```python
# Residualize slow_delta_abs against tag_abs
# (remove the component of slow_delta explained by tag_abs alone)
beta_slow = dot(slow_delta_abs, tag_abs) / (dot(tag_abs, tag_abs) + eps)
residual_slow = slow_delta_abs - beta_slow * tag_abs

# Residualize candidate against tag_abs
beta_cand = dot(candidate, tag_abs) / (dot(tag_abs, tag_abs) + eps)
residual_candidate = candidate - beta_cand * tag_abs

# Alignment on residuals
residual_alignment = cosine(residual_candidate, residual_slow)
residual_corr      = Pearson(residual_candidate, residual_slow)
```

Apply to: novelty_conn, surprise_mag_conn, neg_surprise_conn.

**Interpretation:**
- If `residual_alignment ≈ 0`: the candidate's alignment was entirely due to
  the shared `tag_abs` component. Historical factor adds nothing.
- If `residual_alignment > 0` (and > background residual): the candidate
  contains information about slow_delta beyond what tag_abs already explains.

### 4. Within-Tag Correlation

Restrict to connections where `tag_abs > threshold` and ask: among tagged
connections, does the historical factor predict the *magnitude* of slow_delta?

```python
tagged_mask = tag_abs > 1e-10

within_tag_novelty_corr   = Pearson(novelty_factor[tagged_mask],
                                    slow_delta_abs[tagged_mask])
within_tag_surprise_corr  = Pearson(surprise_mag_factor[tagged_mask],
                                    slow_delta_abs[tagged_mask])
within_tag_h_norm_corr    = Pearson(h_norm_conn[tagged_mask],
                                    slow_delta_abs[tagged_mask])
```

**Purpose:** This removes the tag_abs multiplier entirely. If novelty_factor
predicts slow_delta magnitude *within* the tagged set, h[u] history is
genuinely informative about capture strength.

**Interpretation:**
- Positive `within_tag_novelty_corr`: low-h connections that get tagged also
  tend to get stronger captures. Historical context matters.
- Near-zero: tag_abs determines capture; h[u] adds nothing within the tagged set.

### 5. Shuffled Factor Null Distribution

Shuffle `h_norm_conn` across connections (preserving `tag_abs` and
`slow_delta_abs` intact) and recompute novelty alignment:

```python
observed_novelty_alignment = cosine(tag_abs * (1 - h_norm_conn), slow_delta_abs)

shuffle_alignments = []
for _ in range(100):
    h_shuffled = np.random.permutation(h_norm_conn)
    shuffled_novelty = tag_abs * (1 - h_shuffled)
    shuffle_alignments.append(cosine(shuffled_novelty, slow_delta_abs))

shuffle_percentile = percentile_rank(observed_novelty_alignment, shuffle_alignments)
```

**Interpretation:**
- `shuffle_percentile > 0.95`: the spatial structure of h[u] matters.
  The observed alignment is not achievable by a random h[u] assignment.
- `shuffle_percentile ≈ 0.5`: h[u]'s spatial structure is irrelevant.
  Any h[u] would give similar alignment — the signal is from `tag_abs` alone.

Apply to: novelty_conn, surprise_mag_conn.

---

## Output Specification

### Capture-level audit CSV

One row per capture event per arm per seed.

| Column | Description |
|--------|-------------|
| seed, arm, capture_index | identifiers |
| tag_only_alignment | cosine(tag_abs, slow_delta_abs) |
| tag_only_corr | Pearson(tag_abs, slow_delta_abs) |
| novelty_factor_tag_corr | Pearson(novelty_factor, tag_abs) |
| novelty_factor_slow_corr | Pearson(novelty_factor, slow_delta_abs) |
| surprise_factor_tag_corr | Pearson(surprise_mag_factor, tag_abs) |
| surprise_factor_slow_corr | Pearson(surprise_mag_factor, slow_delta_abs) |
| residual_novelty_corr | Pearson(residual_novelty, residual_slow) |
| residual_surprise_corr | Pearson(residual_surprise_mag, residual_slow) |
| within_tag_novelty_corr | Pearson(novelty_factor[tagged], slow_delta[tagged]) |
| within_tag_surprise_corr | Pearson(surprise_factor[tagged], slow_delta[tagged]) |
| within_tag_h_norm_corr | Pearson(h_norm[tagged], slow_delta[tagged]) |
| shuffle_percentile_novelty | percentile rank of observed vs 100 shuffles |
| shuffle_percentile_surprise | same for surprise_mag |
| n_tagged | number of tagged connections at this capture |

### Summary audit CSV

One row per arm per seed.

| Column | Description |
|--------|-------------|
| seed, arm | identifiers |
| mean_tag_only_alignment | mean over captures |
| mean_residual_novelty_corr | mean over captures |
| mean_residual_surprise_corr | mean over captures |
| mean_within_tag_novelty_corr | mean over captures |
| mean_within_tag_surprise_corr | mean over captures |
| mean_shuffle_percentile_novelty | mean over captures |
| mean_shuffle_percentile_surprise | mean over captures |
| novelty_vs_tag_only_delta | mean_novelty_alignment − mean_tag_only_alignment |
| audit_verdict | see decision rules |

---

## Decision Rules

| Outcome | Verdict | Next step |
|---------|---------|-----------|
| `tag_only_alignment ≈ novelty_alignment` AND `residual_novelty_corr ≈ 0` AND `shuffle_percentile ≈ 0.5` | `tag_self_alignment_artifact` | Do not proceed to 10D.4B. Redesign candidate formulas to decouple from tag_abs. |
| `residual_novelty_corr > 0` OR `within_tag_novelty_corr > 0` OR `shuffle_percentile > 0.95` in both seeds | `novelty_contains_extra_context_signal` | Proceed to 10D.4B rarity/progress. |
| `factor_slow_corr > 0` without tag_abs multiplier | `factor_has_independent_value` | Consider factor-only formulation in 10D.4B. |
| Mixed seeds | `seed_disagreement` | Expand to 4-seed audit before proceeding. |
| `within_tag_novelty_corr < 0` | `h_norm_suppresses_capture_within_tag` | Interesting negative: high-h tagged connections get weaker captures. Note for 10D.5 design. |

**No gate implementation from audit results.**
**Do not alter 10D.4A results.**
**Do not enter 10D.5.**

---

## Relationship to 10D.4A

This audit does not replace 10D.4A. It audits the validity of 10D.4A's metric.

If the audit returns `novelty_contains_extra_context_signal`:
- 10D.4A result stands as valid
- 10D.4B proceeds with rarity/progress

If the audit returns `tag_self_alignment_artifact`:
- 10D.4A result is a metric artifact
- Candidate formulas must be redesigned before 10D.4B
- The redesign question: how to measure h[u]'s contribution *independently* of tag_abs

---

## Implementation Note (for when runner is built)

The shuffle test (100 permutations per capture) adds ~100× overhead per
capture event. With ~10 captures per arm per seed, this is ~1000 extra
cosine computations per arm — manageable. The runner should run shuffles
only for `closed_loop` arm to keep runtime bounded.
