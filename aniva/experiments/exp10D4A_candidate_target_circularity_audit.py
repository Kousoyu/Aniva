"""Phase 10D.4A — Candidate-Target Circularity Audit.

Audits whether 10D.4A novelty/surprise alignment reflects genuine historical
context or tag_abs self-alignment (since candidates = tag_abs × factor and
slow_delta is tag-derived).

Five audit metrics per capture:
  1. tag_only_baseline: cosine/Pearson(tag_abs, slow_delta_abs)
  2. factor_only: Pearson(factor, tag_abs/slow_delta) without tag_abs multiplier
  3. residualized: partial out tag_abs from both candidate and slow_delta
  4. within_tag: correlation within tagged connections only
  5. shuffled_null: permute h_norm, compare observed vs shuffle distribution

h[u] is strictly read-only. No mechanism changes.
"""

import argparse, csv, hashlib, json, sys, time
import numpy as np

from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.environment.environment import Stimulus, StimulusEvent, Environment

L_STIM = Stimulus(position=(-0.5, 0.0, 0.0), intensity=0.02, radius=0.5)
R_STIM = Stimulus(position=(0.5, 0.0, 0.0), intensity=0.02, radius=0.5)
STIM_MAP = {"L": L_STIM, "R": R_STIM}

TOTAL_STEPS = 7500
WARMUP_END = 2000
DECISION_INTERVAL = 250
PULSE_DURATION = 80

W = 5.0
B_NONE = +1.0
B_L = -1.5
B_R = -1.5
B_SIM = -3.0
TAU = 1.0

DIVERGENT_NOISE_OFFSET = 5000
HISTORICAL_CONTEXT_TAU = 10000.0
EVENT_SET = ["none", "L", "R", "simultaneous"]


def _unit_region(pos):
    x = pos[0]
    if x < -0.1: return "L"
    elif x > 0.1: return "R"
    return "M"


def _compute_region_activity(core):
    acts = core._activations
    positions = core._positions
    l_vals, r_vals = [], []
    for uid in range(len(acts)):
        reg = _unit_region(positions[uid])
        if reg == "L": l_vals.append(acts[uid])
        elif reg == "R": r_vals.append(acts[uid])
    return (float(np.mean(l_vals)) if l_vals else 0.0,
            float(np.mean(r_vals)) if r_vals else 0.0)


def _snapshot_core_state(core):
    return {
        "activations": core._activations.copy(),
        "energies": core._energies.copy(),
        "thresholds": core._thresholds.copy(),
        "traces": core._traces.copy(),
        "activity_traces": core._activity_traces.copy(),
        "previous_activations": core._previous_activations.copy(),
        "onset_traces": core._onset_traces.copy(),
        "current_onsets": core._current_onsets.copy(),
        "event_trace": core._event_trace.copy(),
        "last_event_step": core._last_event_step,
        "positions": core._positions.copy(),
        "time_constants": core._time_constants.copy(),
        "source_indices": core._source_indices.copy(),
        "target_indices": core._target_indices.copy(),
        "weights": np.array([c.weight for c in core.connections], dtype=np.float64),
        "weight_cache": core._weight_cache.copy(),
        "step_count": core.step_count,
    }


def _restore_core_state(core, snap):
    core._activations[:] = snap["activations"]
    core._energies[:] = snap["energies"]
    core._thresholds[:] = snap["thresholds"]
    core._traces[:] = snap["traces"]
    core._activity_traces[:] = snap["activity_traces"]
    core._previous_activations[:] = snap["previous_activations"]
    core._onset_traces[:] = snap["onset_traces"]
    core._current_onsets[:] = snap["current_onsets"]
    core._event_trace[:] = snap["event_trace"]
    core._last_event_step = snap["last_event_step"]
    core._positions[:] = snap["positions"]
    core._time_constants[:] = snap["time_constants"]
    core._source_indices[:] = snap["source_indices"]
    core._target_indices[:] = snap["target_indices"]
    core._weight_cache[:] = snap["weight_cache"]
    core.step_count = snap["step_count"]
    for i, conn in enumerate(core.connections):
        conn.weight = float(snap["weights"][i])


def _run_warmup_weight_frozen(core, warmup_steps, env):
    w0 = core._weight_cache.copy()
    w0_conn = [c.weight for c in core.connections]
    for s in range(warmup_steps):
        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)
        core._weight_cache[:] = w0
        for i, conn in enumerate(core.connections):
            conn.weight = w0_conn[i]
    return float(np.sum(np.abs(core._weight_cache - w0)))


# ═══════════════════════════════════════════════════════════════════
# Math helpers
# ═══════════════════════════════════════════════════════════════════

def _cosine(a, b):
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _pearson(a, b):
    if len(a) < 2:
        return 0.0
    std_a = float(np.std(a))
    std_b = float(np.std(b))
    if std_a < 1e-12 or std_b < 1e-12:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def _residualize(x, ref):
    """Remove the component of x explained by ref (linear projection)."""
    denom = float(np.dot(ref, ref))
    if denom < 1e-12:
        return x.copy()
    beta = float(np.dot(x, ref)) / denom
    return x - beta * ref


def _percentile_rank(observed, distribution):
    """Fraction of distribution values strictly below observed."""
    dist = np.array(distribution)
    if len(dist) == 0:
        return float("nan")
    return float(np.mean(dist < observed))


# ═══════════════════════════════════════════════════════════════════
# Core audit function (per capture event)
# ═══════════════════════════════════════════════════════════════════

def _circularity_audit(h_pre, tag_pre, slow_delta, acts_pre,
                       src_idx, tgt_idx, seed, arm, capture_idx,
                       n_shuffles, shuffle_rng):
    """Compute all five audit metrics for one capture event."""
    eps = 1e-9

    # Project to connection space
    h_conn = 0.5 * (h_pre[src_idx] + h_pre[tgt_idx])
    h_max = float(np.max(h_conn))
    h_norm = h_conn / (h_max + eps)
    phi_conn = 0.5 * (acts_pre[src_idx] + acts_pre[tgt_idx])

    tag_abs = np.abs(tag_pre)
    slow_abs = np.abs(slow_delta)
    n_tagged = int(np.sum(tag_abs > 1e-10))

    # ── 1. tag_only_baseline ──
    tag_only_alignment = _cosine(tag_abs, slow_abs)
    tag_only_corr = _pearson(tag_abs, slow_abs)

    # ── 2. factor_only ──
    novelty_factor = 1.0 - h_norm
    surprise_factor = np.abs(phi_conn - h_norm)
    pos_factor = np.maximum(0.0, phi_conn - h_norm)
    neg_factor = np.maximum(0.0, h_norm - phi_conn)

    novelty_factor_tag_corr = _pearson(novelty_factor, tag_abs)
    novelty_factor_slow_corr = _pearson(novelty_factor, slow_abs)
    surprise_factor_tag_corr = _pearson(surprise_factor, tag_abs)
    surprise_factor_slow_corr = _pearson(surprise_factor, slow_abs)
    pos_factor_slow_corr = _pearson(pos_factor, slow_abs)
    neg_factor_slow_corr = _pearson(neg_factor, slow_abs)

    tagged_mask = tag_abs > 1e-10
    novelty_tagged_mean = (float(np.mean(novelty_factor[tagged_mask]))
                           if tagged_mask.any() else float("nan"))
    novelty_untagged_mean = (float(np.mean(novelty_factor[~tagged_mask]))
                             if (~tagged_mask).any() else float("nan"))
    if tagged_mask.sum() >= 2:
        top_k = max(1, tagged_mask.sum() // 4)
        tag_order = np.argsort(tag_abs)[::-1]
        top_tag_idx = tag_order[:top_k]
        bot_tag_idx = tag_order[-top_k:]
        top_tag_novelty_mean = float(np.mean(novelty_factor[top_tag_idx]))
        bot_tag_novelty_mean = float(np.mean(novelty_factor[bot_tag_idx]))
    else:
        top_tag_novelty_mean = float("nan")
        bot_tag_novelty_mean = float("nan")

    # ── 3. residualized ──
    residual_slow = _residualize(slow_abs, tag_abs)
    residual_novelty = _residualize(tag_abs * novelty_factor, tag_abs)
    residual_surprise = _residualize(tag_abs * surprise_factor, tag_abs)
    residual_pos = _residualize(tag_abs * pos_factor, tag_abs)
    residual_neg = _residualize(tag_abs * neg_factor, tag_abs)

    residual_novelty_corr = _pearson(residual_novelty, residual_slow)
    residual_surprise_corr = _pearson(residual_surprise, residual_slow)
    residual_pos_corr = _pearson(residual_pos, residual_slow)
    residual_neg_corr = _pearson(residual_neg, residual_slow)
    residual_novelty_alignment = _cosine(residual_novelty, residual_slow)
    residual_surprise_alignment = _cosine(residual_surprise, residual_slow)

    # ── 4. within-tag ──
    if tagged_mask.sum() >= 2:
        wt_novelty = _pearson(novelty_factor[tagged_mask], slow_abs[tagged_mask])
        wt_surprise = _pearson(surprise_factor[tagged_mask], slow_abs[tagged_mask])
        wt_pos = _pearson(pos_factor[tagged_mask], slow_abs[tagged_mask])
        wt_neg = _pearson(neg_factor[tagged_mask], slow_abs[tagged_mask])
        wt_h_norm = _pearson(h_norm[tagged_mask], slow_abs[tagged_mask])
    else:
        wt_novelty = wt_surprise = wt_pos = wt_neg = wt_h_norm = float("nan")

    # ── 5. shuffled null (closed_loop only to bound runtime) ──
    novelty_alignment_original = _cosine(tag_abs * novelty_factor, slow_abs)
    surprise_alignment_original = _cosine(tag_abs * surprise_factor, slow_abs)
    if arm == "closed_loop":
        obs_novelty_align = novelty_alignment_original
        obs_surprise_align = surprise_alignment_original
        shuffle_novelty = []
        shuffle_surprise = []
        for _ in range(n_shuffles):
            h_shuf = shuffle_rng.permutation(h_norm)
            nf_shuf = 1.0 - h_shuf
            sf_shuf = np.abs(phi_conn - h_shuf)
            shuffle_novelty.append(_cosine(tag_abs * nf_shuf, slow_abs))
            shuffle_surprise.append(_cosine(tag_abs * sf_shuf, slow_abs))
        pct_novelty = _percentile_rank(obs_novelty_align, shuffle_novelty)
        pct_surprise = _percentile_rank(obs_surprise_align, shuffle_surprise)
    else:
        pct_novelty = float("nan")
        pct_surprise = float("nan")

    return {
        "seed": seed, "arm": arm, "capture_index": capture_idx,
        "n_tagged": n_tagged,
        # 1. tag_only
        "tag_only_alignment": round(tag_only_alignment, 8),
        "tag_only_corr": round(tag_only_corr, 8),
        # 2. factor_only
        "novelty_factor_tag_corr": round(novelty_factor_tag_corr, 8),
        "novelty_factor_slow_corr": round(novelty_factor_slow_corr, 8),
        "surprise_factor_tag_corr": round(surprise_factor_tag_corr, 8),
        "surprise_factor_slow_corr": round(surprise_factor_slow_corr, 8),
        "pos_factor_slow_corr": round(pos_factor_slow_corr, 8),
        "neg_factor_slow_corr": round(neg_factor_slow_corr, 8),
        "novelty_factor_tagged_mean": round(novelty_tagged_mean, 8) if not np.isnan(novelty_tagged_mean) else "nan",
        "novelty_factor_untagged_mean": round(novelty_untagged_mean, 8) if not np.isnan(novelty_untagged_mean) else "nan",
        "top_tag_novelty_factor_mean": round(top_tag_novelty_mean, 8) if not np.isnan(top_tag_novelty_mean) else "nan",
        "bot_tag_novelty_factor_mean": round(bot_tag_novelty_mean, 8) if not np.isnan(bot_tag_novelty_mean) else "nan",
        # 3. residualized
        "residual_novelty_corr": round(residual_novelty_corr, 8),
        "residual_surprise_corr": round(residual_surprise_corr, 8),
        "residual_pos_surprise_corr": round(residual_pos_corr, 8),
        "residual_neg_surprise_corr": round(residual_neg_corr, 8),
        "residual_novelty_alignment": round(residual_novelty_alignment, 8),
        "residual_surprise_alignment": round(residual_surprise_alignment, 8),
        # 4. within-tag
        "within_tag_novelty_corr": round(wt_novelty, 8) if not np.isnan(wt_novelty) else "nan",
        "within_tag_surprise_corr": round(wt_surprise, 8) if not np.isnan(wt_surprise) else "nan",
        "within_tag_pos_corr": round(wt_pos, 8) if not np.isnan(wt_pos) else "nan",
        "within_tag_neg_corr": round(wt_neg, 8) if not np.isnan(wt_neg) else "nan",
        "within_tag_h_norm_corr": round(wt_h_norm, 8) if not np.isnan(wt_h_norm) else "nan",
        # 5. shuffle
        "shuffle_percentile_novelty": round(pct_novelty, 4) if not np.isnan(pct_novelty) else "nan",
        "shuffle_percentile_surprise": round(pct_surprise, 4) if not np.isnan(pct_surprise) else "nan",
        "novelty_alignment_original": round(novelty_alignment_original, 8),
        "surprise_alignment_original": round(surprise_alignment_original, 8),
    }


def _mean_or_nan(rows, key):
    vals = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
    return float(np.mean(vals)) if vals else float("nan")


def _audit_verdict(means):
    tag_only = means.get("mean_tag_only_alignment", float("nan"))
    novelty_orig = means.get("mean_novelty_alignment_original", float("nan"))
    residual_nv = means.get("mean_residual_novelty_corr", float("nan"))
    wt_nv = means.get("mean_within_tag_novelty_corr", float("nan"))
    pct_nv = means.get("mean_shuffle_percentile_novelty", float("nan"))

    def _ok(v): return not np.isnan(v)

    # tag_only ≈ novelty_orig means novelty adds nothing
    tag_self = (_ok(tag_only) and _ok(novelty_orig) and
                abs(tag_only - novelty_orig) < 0.05)
    residual_pass = _ok(residual_nv) and residual_nv > 0.05
    within_pass = _ok(wt_nv) and wt_nv > 0.0
    shuffle_pass = _ok(pct_nv) and pct_nv > 0.90

    if tag_self and not residual_pass and not shuffle_pass:
        return "tag_self_alignment_artifact"
    if residual_pass or shuffle_pass:
        return "novelty_contains_extra_context_signal"
    if within_pass:
        return "weak_within_tag_signal"
    return "inconclusive"


class Scheduler:
    def __init__(self, rng):
        self._rng = rng

    def propose(self, activity_L, activity_R):
        logit_none = B_NONE
        logit_L = W * activity_R + B_L
        logit_R = W * activity_L + B_R
        logit_sim = B_SIM
        logits = np.array([logit_none, logit_L, logit_R, logit_sim], dtype=np.float64)
        logits -= np.max(logits)
        exp_logits = np.exp(logits / TAU)
        probs = exp_logits / np.sum(exp_logits)
        u = float(self._rng.random())
        cum = 0.0
        chosen_idx = 0
        for i, p in enumerate(probs):
            cum += p
            if u < cum:
                chosen_idx = i
                break
        return {"chosen": EVENT_SET[chosen_idx]}


def _build_phi_cache(core):
    n = core.unit_count
    phi_l = np.array([L_STIM.influence_at(tuple(core._positions[u]))
                      for u in range(n)], dtype=np.float64)
    phi_r = np.array([R_STIM.influence_at(tuple(core._positions[u]))
                      for u in range(n)], dtype=np.float64)
    return {"L": phi_l, "R": phi_r, "simultaneous": phi_l + phi_r}


def _make_cfg(seed, event_pair_on=True, consolidation_on=True):
    return AnivaConfig(
        unit_count=300, seed=seed,
        event_pair_plasticity_enabled=event_pair_on,
        event_pair_ledger_enabled=event_pair_on,
        consolidation_enabled=consolidation_on,
        consolidation_ledger_enabled=consolidation_on,
        historical_context_enabled=True,
        historical_context_tau=HISTORICAL_CONTEXT_TAU,
        historical_context_clip=True,
    )


def _git_sha():
    import subprocess
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


# ═══════════════════════════════════════════════════════════════════
# Arm runners (same experiment logic as 10D4A, audit callback only)
# ═══════════════════════════════════════════════════════════════════

def _run_arm_closed_loop(seed_env, decision_points, n_shuffles):
    cfg = _make_cfg(seed_env)
    core = LifeCore(cfg)
    sched_rng = np.random.default_rng(seed_env + 1000)
    scheduler = Scheduler(sched_rng)
    env = Environment()
    phi_cache = _build_phi_cache(core)
    # per-capture shuffle rng: fixed seed for reproducibility
    shuffle_rng = np.random.default_rng(seed_env + 9999)
    audit_rows = []
    event_log = []

    _run_warmup_weight_frozen(core, WARMUP_END, env)

    for s in range(WARMUP_END, TOTAL_STEPS):
        ledger_before = len(core._consolidation_ledger)
        h_pre = core._historical_context_trace.copy()
        acts_pre = core._activations.copy()
        tag_pre = core._tag_cache.copy() if core._tag_cache is not None else None
        slow_pre = core._slow_weight_cache.copy() if core._slow_weight_cache is not None else None

        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)

        if (tag_pre is not None and slow_pre is not None and
                len(core._consolidation_ledger) > ledger_before):
            slow_delta = core._slow_weight_cache - slow_pre
            row = _circularity_audit(
                h_pre, tag_pre, slow_delta, acts_pre,
                core._source_indices, core._target_indices,
                seed_env, "closed_loop", len(audit_rows),
                n_shuffles, shuffle_rng)
            audit_rows.append(row)

        if s in decision_points:
            act_l, act_r = _compute_region_activity(core)
            result = scheduler.propose(act_l, act_r)
            chosen = result["chosen"]
            if chosen != "none":
                phi = phi_cache[chosen]
                stim = STIM_MAP.get(chosen)
                if stim is None:
                    env.add_event(StimulusEvent(stimulus=L_STIM, start_step=s,
                                                duration_steps=PULSE_DURATION))
                    env.add_event(StimulusEvent(stimulus=R_STIM, start_step=s,
                                                duration_steps=PULSE_DURATION))
                else:
                    env.add_event(StimulusEvent(stimulus=stim, start_step=s,
                                                duration_steps=PULSE_DURATION))
                core.apply_event_pair_phi(phi)
            event_log.append({"t": s, "chosen": chosen})

    event_trace = [(d["t"], d["chosen"],
                    hashlib.sha256(phi_cache[d["chosen"]].tobytes()).hexdigest()[:16])
                   for d in event_log if d["chosen"] != "none"]
    return audit_rows, event_trace


def _run_arm_exact_replay(seed_env, event_trace, n_shuffles):
    cfg = _make_cfg(seed_env)
    core = LifeCore(cfg)
    core.config.event_pair_plasticity_enabled = False
    core.config.consolidation_enabled = False
    phi_cache = _build_phi_cache(core)
    env = Environment()
    shuffle_rng = np.random.default_rng(seed_env + 9998)
    audit_rows = []
    replay_idx = 0
    n_expected = len(event_trace)
    hash_mismatches = 0

    _run_warmup_weight_frozen(core, WARMUP_END, env)
    core.config.event_pair_plasticity_enabled = True
    core.config.consolidation_enabled = True
    if core._tag_cache is None:
        core._init_consolidation()

    for s in range(WARMUP_END, TOTAL_STEPS):
        ledger_before = len(core._consolidation_ledger)
        h_pre = core._historical_context_trace.copy()
        acts_pre = core._activations.copy()
        tag_pre = core._tag_cache.copy() if core._tag_cache is not None else None
        slow_pre = core._slow_weight_cache.copy() if core._slow_weight_cache is not None else None

        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)

        if (tag_pre is not None and slow_pre is not None and
                len(core._consolidation_ledger) > ledger_before):
            slow_delta = core._slow_weight_cache - slow_pre
            row = _circularity_audit(
                h_pre, tag_pre, slow_delta, acts_pre,
                core._source_indices, core._target_indices,
                seed_env, "exact_replay", len(audit_rows),
                n_shuffles, shuffle_rng)
            audit_rows.append(row)

        while replay_idx < n_expected and event_trace[replay_idx][0] == s:
            t_dec, chosen, exp_hash = event_trace[replay_idx]
            phi = phi_cache[chosen]
            actual_hash = hashlib.sha256(phi.tobytes()).hexdigest()[:16]
            if actual_hash != exp_hash:
                hash_mismatches += 1
            stim = STIM_MAP.get(chosen)
            if stim is None:
                env.add_event(StimulusEvent(stimulus=L_STIM, start_step=s,
                                            duration_steps=PULSE_DURATION))
                env.add_event(StimulusEvent(stimulus=R_STIM, start_step=s,
                                            duration_steps=PULSE_DURATION))
            else:
                env.add_event(StimulusEvent(stimulus=stim, start_step=s,
                                            duration_steps=PULSE_DURATION))
            core.apply_event_pair_phi(phi)
            replay_idx += 1

    return audit_rows, hash_mismatches, replay_idx, n_expected


def _run_arm_divergent(seed_env, event_trace, n_shuffles):
    hc_kw = dict(historical_context_enabled=True,
                 historical_context_tau=HISTORICAL_CONTEXT_TAU,
                 historical_context_clip=True)
    cfg_ref = AnivaConfig(unit_count=300, seed=seed_env,
                          event_pair_plasticity_enabled=False,
                          consolidation_enabled=False, **hc_kw)
    core_ref = LifeCore(cfg_ref)
    ref_snap = _snapshot_core_state(core_ref)

    cfg_div = AnivaConfig(unit_count=300, seed=seed_env + DIVERGENT_NOISE_OFFSET,
                          event_pair_plasticity_enabled=False,
                          consolidation_enabled=False, **hc_kw)
    core_div = LifeCore(cfg_div)
    _restore_core_state(core_div, ref_snap)

    env_div = Environment()
    _run_warmup_weight_frozen(core_div, WARMUP_END, env_div)
    div_state = {
        "activations": core_div._activations.copy(),
        "energies": core_div._energies.copy(),
        "traces": core_div._traces.copy(),
        "event_trace": core_div._event_trace.copy(),
        "weight_cache": core_div._weight_cache.copy(),
        "h_trace": core_div._historical_context_trace.copy(),
    }

    cfg_replay = _make_cfg(seed_env, event_pair_on=True, consolidation_on=True)
    core_replay = LifeCore(cfg_replay)
    core_replay._activations[:] = div_state["activations"]
    core_replay._energies[:] = div_state["energies"]
    core_replay._traces[:] = div_state["traces"]
    core_replay._event_trace[:] = div_state["event_trace"]
    core_replay._weight_cache[:] = div_state["weight_cache"]
    core_replay._historical_context_trace[:] = div_state["h_trace"]
    for i, conn in enumerate(core_replay.connections):
        conn.weight = float(div_state["weight_cache"][i])

    phi_cache = _build_phi_cache(core_replay)
    env_replay = Environment()
    shuffle_rng = np.random.default_rng(seed_env + 9997)
    audit_rows = []
    replay_idx = 0
    n_expected = len(event_trace)
    hash_mismatches = 0

    for s in range(WARMUP_END, TOTAL_STEPS):
        ledger_before = len(core_replay._consolidation_ledger)
        h_pre = core_replay._historical_context_trace.copy()
        acts_pre = core_replay._activations.copy()
        tag_pre = (core_replay._tag_cache.copy()
                   if core_replay._tag_cache is not None else None)
        slow_pre = (core_replay._slow_weight_cache.copy()
                    if core_replay._slow_weight_cache is not None else None)

        influences = env_replay.compute_influences(core_replay.units, s)
        core_replay.step(env_influences=influences if influences else None)

        if (tag_pre is not None and slow_pre is not None and
                len(core_replay._consolidation_ledger) > ledger_before):
            slow_delta = core_replay._slow_weight_cache - slow_pre
            row = _circularity_audit(
                h_pre, tag_pre, slow_delta, acts_pre,
                core_replay._source_indices, core_replay._target_indices,
                seed_env, "divergent_warmup_replay", len(audit_rows),
                n_shuffles, shuffle_rng)
            audit_rows.append(row)

        while replay_idx < n_expected and event_trace[replay_idx][0] == s:
            t_dec, chosen, exp_hash = event_trace[replay_idx]
            phi = phi_cache[chosen]
            actual_hash = hashlib.sha256(phi.tobytes()).hexdigest()[:16]
            if actual_hash != exp_hash:
                hash_mismatches += 1
            stim = STIM_MAP.get(chosen)
            if stim is None:
                env_replay.add_event(StimulusEvent(stimulus=L_STIM, start_step=s,
                                                   duration_steps=PULSE_DURATION))
                env_replay.add_event(StimulusEvent(stimulus=R_STIM, start_step=s,
                                                   duration_steps=PULSE_DURATION))
            else:
                env_replay.add_event(StimulusEvent(stimulus=stim, start_step=s,
                                                   duration_steps=PULSE_DURATION))
            core_replay.apply_event_pair_phi(phi)
            replay_idx += 1

    return audit_rows, hash_mismatches, replay_idx, n_expected


# ═══════════════════════════════════════════════════════════════════
# Output helpers
# ═══════════════════════════════════════════════════════════════════

def _build_arm_means(rows):
    if not rows:
        return {}
    keys = [k for k in rows[0].keys() if k not in ("seed", "arm", "capture_index")]
    return {f"mean_{k}": _mean_or_nan(rows, k) for k in keys}


def _save_csv(rows, path):
    if not rows:
        return
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Phase 10D.4A Circularity Audit")
    parser.add_argument("--seeds", nargs="+", type=int, default=[42, 77])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--estimate-only", action="store_true")
    parser.add_argument("--n-shuffles", type=int, default=100)
    args = parser.parse_args()

    seeds = args.seeds
    n_shuffles = args.n_shuffles
    decision_points = set(range(WARMUP_END, TOTAL_STEPS, DECISION_INTERVAL))

    print("Phase 10D.4A Circularity Audit")
    print(f"  seeds={seeds}  n_shuffles={n_shuffles}")
    print(f"  TOTAL_STEPS={TOTAL_STEPS}  WARMUP_END={WARMUP_END}")
    print(f"  decision_points={len(decision_points)}")

    if args.dry_run:
        print("[dry-run] config OK, exiting.")
        return 0

    if args.estimate_only:
        steps = (TOTAL_STEPS - WARMUP_END) * 3 * len(seeds)
        est = steps / 500
        print(f"[estimate] ~{est:.0f}s ({est/60:.1f} min) — "
              f"{len(seeds)} seeds × 3 arms × {TOTAL_STEPS - WARMUP_END} steps")
        return 0

    all_rows = []
    seed_summaries = []

    for seed in seeds:
        print(f"\n=== seed={seed} ===")
        t0 = time.time()

        print("  [1/3] closed_loop ...")
        cl_rows, event_trace = _run_arm_closed_loop(seed, decision_points, n_shuffles)
        print(f"    captures={len(cl_rows)}  events={len(event_trace)}")
        all_rows.extend(cl_rows)

        print("  [2/3] exact_replay ...")
        er_rows, er_mm, er_rep, er_exp = _run_arm_exact_replay(seed, event_trace, 0)
        print(f"    captures={len(er_rows)}  hash_mismatches={er_mm}")
        all_rows.extend(er_rows)

        print("  [3/3] divergent_warmup_replay ...")
        dv_rows, dv_mm, dv_rep, dv_exp = _run_arm_divergent(seed, event_trace, 0)
        print(f"    captures={len(dv_rows)}  hash_mismatches={dv_mm}")
        all_rows.extend(dv_rows)

        elapsed = time.time() - t0
        print(f"  seed={seed} done in {elapsed:.1f}s")

        cl_means = _build_arm_means(cl_rows)
        verdict = _audit_verdict(cl_means)
        print(f"  verdict={verdict}")
        for key in ("mean_tag_only_alignment", "mean_novelty_alignment_original",
                    "mean_residual_novelty_corr", "mean_within_tag_novelty_corr",
                    "mean_shuffle_percentile_novelty"):
            v = cl_means.get(key, float("nan"))
            label = key.replace("mean_", "")
            print(f"    {label}={v:.4f}" if not np.isnan(v) else f"    {label}=nan")

        seed_summaries.append({
            "seed": seed,
            "n_cl_captures": len(cl_rows),
            "n_er_captures": len(er_rows),
            "n_dv_captures": len(dv_rows),
            "n_events": len(event_trace),
            "er_hash_mismatches": er_mm,
            "dv_hash_mismatches": dv_mm,
            "elapsed_s": round(elapsed, 2),
            "verdict": verdict,
            **{k: (round(v, 6) if not np.isnan(v) else "nan")
               for k, v in cl_means.items()},
        })

    # Protocol checks
    checks = {}
    for ss in seed_summaries:
        s = ss["seed"]
        checks[f"P1_cl_captures_gt0_seed{s}"] = ss["n_cl_captures"] > 0
        checks[f"P2_er_captures_gt0_seed{s}"] = ss["n_er_captures"] > 0
        checks[f"P3_dv_captures_gt0_seed{s}"] = ss["n_dv_captures"] > 0
        checks[f"P4_er_hash_ok_seed{s}"] = ss["er_hash_mismatches"] == 0
        checks[f"P5_dv_hash_ok_seed{s}"] = ss["dv_hash_mismatches"] == 0

    all_pass = all(checks.values())
    print("\n=== Protocol Checks ===")
    for k, v in checks.items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")
    print(f"  ALL_PASS: {all_pass}")

    verdicts = [ss["verdict"] for ss in seed_summaries]
    final_verdict = (verdicts[0] if len(set(verdicts)) == 1
                     else "mixed_" + "_".join(sorted(set(verdicts))))
    print(f"\n=== Final Verdict: {final_verdict} ===")

    sha = _git_sha()
    ts = int(time.time())
    out_prefix = "results/phase10D4A_circularity_audit"
    _save_csv(all_rows, f"{out_prefix}_rows.csv")

    summary = {
        "experiment": "phase10D4A_circularity_audit",
        "git_sha": sha,
        "timestamp": ts,
        "seeds": seeds,
        "n_shuffles": n_shuffles,
        "total_steps": TOTAL_STEPS,
        "warmup_end": WARMUP_END,
        "tau": HISTORICAL_CONTEXT_TAU,
        "protocol_checks": checks,
        "all_protocol_pass": all_pass,
        "final_verdict": final_verdict,
        "seed_summaries": seed_summaries,
    }
    with open(f"{out_prefix}_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nSaved: {out_prefix}_rows.csv")
    print(f"Saved: {out_prefix}_summary.json")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
