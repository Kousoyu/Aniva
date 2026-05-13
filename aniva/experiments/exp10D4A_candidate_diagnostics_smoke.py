"""Phase 10D.4A — Candidate Diagnostics Smoke.

Scope freeze: τ=10000 only, 4 candidates, 3 arms + control.
No τ ladder, no rarity/progress, no life_core.py changes.

Candidates:
  1. background_alignment  = cosine(h_conn, tag_abs)
  2. novelty               = tag_abs * (1 - h_norm_conn)
  3. surprise_magnitude    = tag_abs * |phi_conn - h_norm_conn|  [proxy]
  4. signed_surprise       = tag_abs * (phi_conn - h_norm_conn), split pos/neg

phi_conn is a proxy (activation at capture time, not clean event-response delta).
This limitation is noted in every capture row.

h[u] is strictly read-only: does NOT affect gate, capture, or slow_weight.
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


def _hash_payload(phi):
    return hashlib.sha256(phi.tobytes()).hexdigest()[:16]


def _compute_region_activity(core):
    acts = core._activations
    positions = core._positions
    l_vals, r_vals = [], []
    for uid in range(len(acts)):
        reg = _unit_region(positions[uid])
        if reg == "L": l_vals.append(acts[uid])
        elif reg == "R": r_vals.append(acts[uid])
    act_l = float(np.mean(l_vals)) if l_vals else 0.0
    act_r = float(np.mean(r_vals)) if r_vals else 0.0
    return act_l, act_r


def _fast_weight_l1(core):
    return float(np.sum(np.abs(core._weight_cache)))


def _slow_weight_l1(core):
    return float(np.sum(np.abs(core._slow_weight_cache)))


def _activation_divergence(acts_a, acts_b):
    return float(np.mean(np.abs(acts_a - acts_b)))


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
    """Run warmup with weights frozen every step."""
    w0 = core._weight_cache.copy()
    w0_conn = [c.weight for c in core.connections]
    nan_hit = False
    for s in range(warmup_steps):
        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)
        if not nan_hit and np.any(np.isnan(core._activations)):
            nan_hit = True
        core._weight_cache[:] = w0
        for i, conn in enumerate(core.connections):
            conn.weight = w0_conn[i]
    warmup_weight_delta = float(np.sum(np.abs(core._weight_cache - w0)))
    return warmup_weight_delta, nan_hit


# ═══════════════════════════════════════════════════════════════════
# Candidate diagnostic helpers
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


def _candidate_capture_diag(h_pre, tag_pre, slow_delta, acts_pre,
                             src_idx, tgt_idx, ledger_entry,
                             seed, arm, capture_idx):
    """Compute all 4 candidate signals at a single capture event.

    h_pre:     per-unit h[u] snapshot BEFORE the step (read-only)
    tag_pre:   per-connection tag_cache BEFORE the step
    slow_delta: per-connection slow_weight change in this step
    acts_pre:  per-unit activations BEFORE the step (phi proxy)
    """
    eps = 1e-9

    # Project to connection space
    h_conn = 0.5 * (h_pre[src_idx] + h_pre[tgt_idx])
    h_max = float(np.max(h_conn))
    h_norm_conn = h_conn / (h_max + eps)

    # phi proxy: activation at capture time (NOT clean event-response delta)
    phi_conn = 0.5 * (acts_pre[src_idx] + acts_pre[tgt_idx])

    tag_abs = np.abs(tag_pre)
    tag_sum = float(np.sum(tag_abs))
    slow_abs = np.abs(slow_delta)
    slow_sum = float(np.sum(slow_abs))

    # h_tag_ratio (from 10D.3 baseline)
    tagged_mask = tag_abs > 1e-10
    h_tagged_mean = (float(np.mean(h_conn[tagged_mask]))
                     if tagged_mask.any() else 0.0)
    h_untagged_mean = (float(np.mean(h_conn[~tagged_mask]))
                       if (~tagged_mask).any() else 0.0)
    h_tag_ratio = h_tagged_mean / (h_untagged_mean + eps)

    # ── Candidate 1: background_alignment ──
    h_tag_cosine = _cosine(h_conn, tag_abs)
    tag_weighted_h = (float(np.sum(tag_abs * h_conn)) / tag_sum
                      if tag_sum > eps else 0.0)

    # ── Candidate 2: novelty ──
    novelty_conn = tag_abs * (1.0 - h_norm_conn)
    novelty_mass = float(np.sum(novelty_conn))
    novelty_alignment = _cosine(novelty_conn, slow_abs)
    novelty_slow_corr = _pearson(novelty_conn, slow_abs)
    novelty_ratio = novelty_mass / (tag_sum + eps)

    # ── Candidate 3: surprise_magnitude (proxy) ──
    surprise_mag_conn = tag_abs * np.abs(phi_conn - h_norm_conn)
    surprise_mag_mass = float(np.sum(surprise_mag_conn))
    surprise_mag_alignment = _cosine(surprise_mag_conn, slow_abs)
    surprise_mag_slow_corr = _pearson(surprise_mag_conn, slow_abs)
    surprise_mag_ratio = surprise_mag_mass / (tag_sum + eps)

    # ── Candidate 4: signed_surprise ──
    signed_delta_conn = phi_conn - h_norm_conn
    pos_surprise_conn = tag_abs * np.maximum(0.0, signed_delta_conn)
    neg_surprise_conn = tag_abs * np.maximum(0.0, -signed_delta_conn)
    pos_surprise_mass = float(np.sum(pos_surprise_conn))
    neg_surprise_mass = float(np.sum(neg_surprise_conn))
    pos_surprise_alignment = _cosine(pos_surprise_conn, slow_abs)
    neg_surprise_alignment = _cosine(neg_surprise_conn, slow_abs)
    # signed Pearson: no abs on either side
    signed_surprise_slow_corr = _pearson(tag_abs * signed_delta_conn, slow_delta)

    # Cross-candidate deltas vs background
    bg_vs_novelty = novelty_alignment - h_tag_cosine
    bg_vs_surprise_mag = surprise_mag_alignment - h_tag_cosine
    bg_vs_pos_surprise = pos_surprise_alignment - h_tag_cosine

    return {
        "seed": seed, "arm": arm, "capture_index": capture_idx,
        "capture_step": ledger_entry.get("capture_step", ""),
        "capture_signal": round(ledger_entry.get("capture_signal", 0.0), 8),
        "tag_mass": round(tag_sum, 8),
        "slow_delta_l1": round(slow_sum, 8),
        # Candidate 1
        "h_tag_cosine": round(h_tag_cosine, 8),
        "tag_weighted_h": round(tag_weighted_h, 8),
        "h_tag_ratio": round(h_tag_ratio, 6),
        # Candidate 2
        "novelty_mass": round(novelty_mass, 8),
        "novelty_alignment": round(novelty_alignment, 8),
        "novelty_slow_corr": round(novelty_slow_corr, 8),
        "novelty_ratio": round(novelty_ratio, 6),
        # Candidate 3 (proxy — phi_conn is activation at capture, not event-response delta)
        "surprise_mag_mass": round(surprise_mag_mass, 8),
        "surprise_mag_alignment": round(surprise_mag_alignment, 8),
        "surprise_mag_slow_corr": round(surprise_mag_slow_corr, 8),
        "surprise_mag_ratio": round(surprise_mag_ratio, 6),
        "phi_proxy": True,
        # Candidate 4
        "pos_surprise_mass": round(pos_surprise_mass, 8),
        "pos_surprise_alignment": round(pos_surprise_alignment, 8),
        "neg_surprise_mass": round(neg_surprise_mass, 8),
        "neg_surprise_alignment": round(neg_surprise_alignment, 8),
        "signed_surprise_slow_corr": round(signed_surprise_slow_corr, 8),
        # Cross-candidate deltas
        "background_vs_novelty_delta": round(bg_vs_novelty, 8),
        "background_vs_surprise_mag_delta": round(bg_vs_surprise_mag, 8),
        "background_vs_pos_surprise_delta": round(bg_vs_pos_surprise, 8),
    }


def _mean_or_nan(diags, key):
    vals = [d[key] for d in diags if isinstance(d.get(key), (int, float))]
    return float(np.mean(vals)) if vals else float("nan")


def _candidate_rank(means):
    """Rank candidates by mean alignment (closed_loop only)."""
    candidates = {
        "background": means.get("mean_h_tag_cosine", float("nan")),
        "novelty": means.get("mean_novelty_alignment", float("nan")),
        "surprise_mag": means.get("mean_surprise_mag_alignment", float("nan")),
        "pos_surprise": means.get("mean_pos_surprise_alignment", float("nan")),
        "neg_surprise": means.get("mean_neg_surprise_alignment", float("nan")),
    }
    valid = {k: v for k, v in candidates.items() if not np.isnan(v)}
    ranked = sorted(valid, key=lambda k: valid[k], reverse=True)
    return ranked


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
        return {"probs": {"none": float(probs[0]), "L": float(probs[1]),
                          "R": float(probs[2]), "simultaneous": float(probs[3])},
                "u_draw": u, "chosen": EVENT_SET[chosen_idx]}


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


def _build_summary(arm, seed_env, capture_diags, ledger, warmup_weight_delta,
                   core, nan_hit, extra=None):
    """Build per-arm summary dict from capture diagnostics."""
    means = {
        "mean_h_tag_cosine": _mean_or_nan(capture_diags, "h_tag_cosine"),
        "mean_novelty_alignment": _mean_or_nan(capture_diags, "novelty_alignment"),
        "mean_novelty_slow_corr": _mean_or_nan(capture_diags, "novelty_slow_corr"),
        "mean_surprise_mag_alignment": _mean_or_nan(capture_diags, "surprise_mag_alignment"),
        "mean_surprise_mag_slow_corr": _mean_or_nan(capture_diags, "surprise_mag_slow_corr"),
        "mean_pos_surprise_alignment": _mean_or_nan(capture_diags, "pos_surprise_alignment"),
        "mean_neg_surprise_alignment": _mean_or_nan(capture_diags, "neg_surprise_alignment"),
        "mean_signed_surprise_slow_corr": _mean_or_nan(capture_diags, "signed_surprise_slow_corr"),
        "mean_h_tag_ratio": _mean_or_nan(capture_diags, "h_tag_ratio"),
        "mean_novelty_ratio": _mean_or_nan(capture_diags, "novelty_ratio"),
        "mean_surprise_mag_ratio": _mean_or_nan(capture_diags, "surprise_mag_ratio"),
        "mean_background_vs_novelty_delta": _mean_or_nan(capture_diags, "background_vs_novelty_delta"),
        "mean_background_vs_surprise_mag_delta": _mean_or_nan(capture_diags, "background_vs_surprise_mag_delta"),
        "mean_background_vs_pos_surprise_delta": _mean_or_nan(capture_diags, "background_vs_pos_surprise_delta"),
    }
    ranked = _candidate_rank(means)
    best = ranked[0] if ranked else "none"

    def _fmt(v):
        if isinstance(v, float) and np.isnan(v):
            return "nan"
        if isinstance(v, float):
            return round(v, 8)
        return v

    s = {
        "arm": arm, "seed_env": seed_env,
        "capture_count": len(ledger),
        "warmup_weight_delta_l1": round(warmup_weight_delta, 8),
        "fast_weight_l1": round(float(np.sum(np.abs(core._weight_cache))), 8),
        "slow_weight_l1": round(float(np.sum(np.abs(core._slow_weight_cache))), 8),
        "nan_hit": nan_hit,
        "candidate_rank": "|".join(ranked),
        "best_candidate": best,
    }
    for k, v in means.items():
        s[k] = _fmt(v)
    if extra:
        s.update(extra)
    return s


# ═══════════════════════════════════════════════════════════════════
# Arm 1: closed_loop
# ═══════════════════════════════════════════════════════════════════

def run_closed_loop(cfg, seed_env, seed_sched, decision_points, pulse_dur,
                    code_sha, config_sha):
    core = LifeCore(cfg)
    sched_rng = np.random.default_rng(seed_sched)
    scheduler = Scheduler(sched_rng)
    env = Environment()
    phi_cache = _build_phi_cache(core)
    nan_hit = False
    event_log = []
    capture_diags = []

    warmup_weight_delta, warmup_nan = _run_warmup_weight_frozen(core, WARMUP_END, env)
    if warmup_nan:
        nan_hit = True
    h_warmup_end = core._historical_context_trace.copy()

    for s in range(WARMUP_END, TOTAL_STEPS):
        ledger_before = len(core._consolidation_ledger)
        h_pre = core._historical_context_trace.copy()
        acts_pre = core._activations.copy()
        tag_pre = core._tag_cache.copy() if core._tag_cache is not None else None
        slow_pre = core._slow_weight_cache.copy() if core._slow_weight_cache is not None else None

        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)
        if not nan_hit and np.any(np.isnan(core._activations)):
            nan_hit = True

        if (tag_pre is not None and slow_pre is not None and
                len(core._consolidation_ledger) > ledger_before):
            slow_delta = core._slow_weight_cache - slow_pre
            diag = _candidate_capture_diag(
                h_pre, tag_pre, slow_delta, acts_pre,
                core._source_indices, core._target_indices,
                core._consolidation_ledger[-1],
                seed_env, "closed_loop", len(capture_diags))
            capture_diags.append(diag)

        if s in decision_points:
            act_l, act_r = _compute_region_activity(core)
            result = scheduler.propose(act_l, act_r)
            chosen = result["chosen"]
            row = {"run_id": f"phase10D4A_closed_seed{seed_env}",
                   "arm": "closed_loop", "seed_env": seed_env,
                   "code_sha": code_sha, "config_sha": config_sha,
                   "t_decision": s, "chosen_event": chosen, "payload_hash": ""}
            if chosen != "none":
                phi = phi_cache[chosen]
                row["payload_hash"] = hashlib.sha256(phi.tobytes()).hexdigest()[:16]
                stim = STIM_MAP.get(chosen)
                if stim is None:
                    env.add_event(StimulusEvent(stimulus=L_STIM, start_step=s,
                                                duration_steps=pulse_dur))
                    env.add_event(StimulusEvent(stimulus=R_STIM, start_step=s,
                                                duration_steps=pulse_dur))
                else:
                    env.add_event(StimulusEvent(stimulus=stim, start_step=s,
                                                duration_steps=pulse_dur))
                core.apply_event_pair_phi(phi)
            event_log.append(row)

    h_final = core._historical_context_trace.copy()
    ledger = core._consolidation_ledger if core._consolidation_ledger else []
    n_ev = sum(1 for d in event_log if d["chosen_event"] != "none")
    summary = _build_summary("closed_loop", seed_env, capture_diags, ledger,
                             warmup_weight_delta, core, nan_hit,
                             extra={"event_count": n_ev,
                                    "L_count": sum(1 for d in event_log if d["chosen_event"] == "L"),
                                    "R_count": sum(1 for d in event_log if d["chosen_event"] == "R"),
                                    "simultaneous_count": sum(1 for d in event_log if d["chosen_event"] == "simultaneous")})
    return event_log, summary, ledger, h_warmup_end, h_final, capture_diags


# ═══════════════════════════════════════════════════════════════════
# Arm 2: exact_replay
# ═══════════════════════════════════════════════════════════════════

def run_exact_replay(cfg, seed_env, event_trace, pulse_dur, code_sha, config_sha):
    core = LifeCore(cfg)
    core.config.event_pair_plasticity_enabled = False
    core.config.consolidation_enabled = False
    phi_cache = _build_phi_cache(core)
    env = Environment()
    nan_hit = False
    event_log = []
    replay_idx = 0
    n_expected = len(event_trace)
    hash_mismatches = 0
    capture_diags = []

    warmup_weight_delta, warmup_nan = _run_warmup_weight_frozen(core, WARMUP_END, env)
    if warmup_nan:
        nan_hit = True
    h_warmup_end = core._historical_context_trace.copy()

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
        if not nan_hit and np.any(np.isnan(core._activations)):
            nan_hit = True

        if (tag_pre is not None and slow_pre is not None and
                len(core._consolidation_ledger) > ledger_before):
            slow_delta = core._slow_weight_cache - slow_pre
            diag = _candidate_capture_diag(
                h_pre, tag_pre, slow_delta, acts_pre,
                core._source_indices, core._target_indices,
                core._consolidation_ledger[-1],
                seed_env, "exact_replay", len(capture_diags))
            capture_diags.append(diag)

        while replay_idx < n_expected and event_trace[replay_idx][0] == s:
            t_dec, chosen, exp_hash = event_trace[replay_idx]
            phi = phi_cache[chosen]
            actual_hash = hashlib.sha256(phi.tobytes()).hexdigest()[:16]
            if actual_hash != exp_hash:
                hash_mismatches += 1
            stim = STIM_MAP.get(chosen)
            if stim is None:
                env.add_event(StimulusEvent(stimulus=L_STIM, start_step=s,
                                            duration_steps=pulse_dur))
                env.add_event(StimulusEvent(stimulus=R_STIM, start_step=s,
                                            duration_steps=pulse_dur))
            else:
                env.add_event(StimulusEvent(stimulus=stim, start_step=s,
                                            duration_steps=pulse_dur))
            core.apply_event_pair_phi(phi)
            event_log.append({"run_id": f"phase10D4A_exact_seed{seed_env}",
                               "arm": "exact_replay", "seed_env": seed_env,
                               "code_sha": code_sha, "config_sha": config_sha,
                               "t_decision": s, "chosen_event": chosen,
                               "payload_hash": actual_hash,
                               "expected_payload_hash": exp_hash,
                               "hash_match": actual_hash == exp_hash})
            replay_idx += 1

    h_final = core._historical_context_trace.copy()
    ledger = core._consolidation_ledger if core._consolidation_ledger else []
    summary = _build_summary("exact_replay", seed_env, capture_diags, ledger,
                             warmup_weight_delta, core, nan_hit,
                             extra={"n_expected": n_expected,
                                    "n_replayed": replay_idx,
                                    "hash_mismatches": hash_mismatches})
    return event_log, summary, ledger, h_warmup_end, h_final, capture_diags


# ═══════════════════════════════════════════════════════════════════
# Arm 3: divergent_warmup_replay
# ═══════════════════════════════════════════════════════════════════

def run_divergent_warmup_replay(seed_env, event_trace, pulse_dur, code_sha):
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
    warmup_weight_delta, _ = _run_warmup_weight_frozen(core_div, WARMUP_END, env_div)
    h_warmup_end = core_div._historical_context_trace.copy()

    div_state = {
        "activations": core_div._activations.copy(),
        "energies": core_div._energies.copy(),
        "traces": core_div._traces.copy(),
        "event_trace": core_div._event_trace.copy(),
        "weight_cache": core_div._weight_cache.copy(),
        "h_trace": core_div._historical_context_trace.copy(),
    }

    env_ref = Environment()
    _run_warmup_weight_frozen(core_ref, WARMUP_END, env_ref)
    warmup_act_div = _activation_divergence(core_div._activations, core_ref._activations)

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

    phi_cache_replay = _build_phi_cache(core_replay)
    env_replay = Environment()
    nan_hit = False
    event_log = []
    replay_idx = 0
    n_expected = len(event_trace)
    hash_mismatches = 0
    capture_diags = []

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
        if not nan_hit and np.any(np.isnan(core_replay._activations)):
            nan_hit = True

        if (tag_pre is not None and slow_pre is not None and
                len(core_replay._consolidation_ledger) > ledger_before):
            slow_delta = core_replay._slow_weight_cache - slow_pre
            diag = _candidate_capture_diag(
                h_pre, tag_pre, slow_delta, acts_pre,
                core_replay._source_indices, core_replay._target_indices,
                core_replay._consolidation_ledger[-1],
                seed_env, "divergent_warmup_replay", len(capture_diags))
            capture_diags.append(diag)

        while replay_idx < n_expected and event_trace[replay_idx][0] == s:
            t_dec, chosen, exp_hash = event_trace[replay_idx]
            phi = phi_cache_replay[chosen]
            actual_hash = hashlib.sha256(phi.tobytes()).hexdigest()[:16]
            if actual_hash != exp_hash:
                hash_mismatches += 1
            stim = STIM_MAP.get(chosen)
            if stim is None:
                env_replay.add_event(StimulusEvent(stimulus=L_STIM, start_step=s,
                                                   duration_steps=pulse_dur))
                env_replay.add_event(StimulusEvent(stimulus=R_STIM, start_step=s,
                                                   duration_steps=pulse_dur))
            else:
                env_replay.add_event(StimulusEvent(stimulus=stim, start_step=s,
                                                   duration_steps=pulse_dur))
            core_replay.apply_event_pair_phi(phi)
            event_log.append({"run_id": f"phase10D4A_divergent_seed{seed_env}",
                               "arm": "divergent_warmup_replay",
                               "seed_env": seed_env, "code_sha": code_sha,
                               "t_decision": s, "chosen_event": chosen,
                               "payload_hash": actual_hash,
                               "expected_payload_hash": exp_hash,
                               "hash_match": actual_hash == exp_hash})
            replay_idx += 1

    h_final = core_replay._historical_context_trace.copy()
    ledger = core_replay._consolidation_ledger if core_replay._consolidation_ledger else []
    summary = _build_summary("divergent_warmup_replay", seed_env, capture_diags, ledger,
                             warmup_weight_delta, core_replay, nan_hit,
                             extra={"n_expected": n_expected,
                                    "n_replayed": replay_idx,
                                    "hash_mismatches": hash_mismatches,
                                    "warmup_act_div": round(warmup_act_div, 8)})
    return event_log, summary, ledger, h_warmup_end, h_final, capture_diags


# ═══════════════════════════════════════════════════════════════════
# Arm 4: matched_warmup_control
# ═══════════════════════════════════════════════════════════════════

def run_matched_warmup_control(seed_env, pulse_dur, code_sha):
    """Same divergent warmup as arm 3, no event replay after t=2000.
    Baseline only — not included in candidate ranking."""
    hc_kw = dict(historical_context_enabled=True,
                 historical_context_tau=HISTORICAL_CONTEXT_TAU,
                 historical_context_clip=True)
    cfg_ref = AnivaConfig(unit_count=300, seed=seed_env,
                          event_pair_plasticity_enabled=False,
                          consolidation_enabled=False, **hc_kw)
    core_ref = LifeCore(cfg_ref)
    ref_snap_mc = _snapshot_core_state(core_ref)

    cfg_div = AnivaConfig(unit_count=300, seed=seed_env + DIVERGENT_NOISE_OFFSET,
                          event_pair_plasticity_enabled=False,
                          consolidation_enabled=False, **hc_kw)
    core_div = LifeCore(cfg_div)
    _restore_core_state(core_div, ref_snap_mc)

    env_div = Environment()
    warmup_weight_delta, _ = _run_warmup_weight_frozen(core_div, WARMUP_END, env_div)
    warmup_act_div = _activation_divergence(core_div._activations,
                                            ref_snap_mc["activations"])
    h_warmup_end = core_div._historical_context_trace.copy()

    cfg_replay = _make_cfg(seed_env, event_pair_on=True, consolidation_on=True)
    core_replay = LifeCore(cfg_replay)
    core_replay._activations[:] = core_div._activations
    core_replay._energies[:] = core_div._energies
    core_replay._traces[:] = core_div._traces
    core_replay._event_trace[:] = core_div._event_trace
    core_replay._weight_cache[:] = core_div._weight_cache
    core_replay._historical_context_trace[:] = core_div._historical_context_trace
    for i, conn in enumerate(core_replay.connections):
        conn.weight = float(core_div._weight_cache[i])

    env_replay = Environment()
    nan_hit = False
    capture_diags = []

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
        if not nan_hit and np.any(np.isnan(core_replay._activations)):
            nan_hit = True

        if (tag_pre is not None and slow_pre is not None and
                len(core_replay._consolidation_ledger) > ledger_before):
            slow_delta = core_replay._slow_weight_cache - slow_pre
            diag = _candidate_capture_diag(
                h_pre, tag_pre, slow_delta, acts_pre,
                core_replay._source_indices, core_replay._target_indices,
                core_replay._consolidation_ledger[-1],
                seed_env, "matched_warmup_control", len(capture_diags))
            capture_diags.append(diag)

    h_final = core_replay._historical_context_trace.copy()
    ledger = core_replay._consolidation_ledger if core_replay._consolidation_ledger else []
    summary = _build_summary("matched_warmup_control", seed_env, capture_diags, ledger,
                             warmup_weight_delta, core_replay, nan_hit,
                             extra={"warmup_act_div": round(warmup_act_div, 8),
                                    "baseline_only": True})
    return [], summary, ledger, h_warmup_end, h_final, capture_diags

# ═══════════════════════════════════════════════════════════════════
# Output helpers
# ═══════════════════════════════════════════════════════════════════

def _save_csv(rows, path):
    if not rows:
        return
    all_fields = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                all_fields.append(k)
                seen.add(k)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=all_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def main(argv=None):
    p = argparse.ArgumentParser(
        description="Phase 10D.4A — Candidate Diagnostics Smoke")
    p.add_argument("--seeds", type=int, nargs="+", default=[42, 77])
    p.add_argument("--estimate-only", action="store_true")
    p.add_argument("--dry-run-schedule", action="store_true")
    p.add_argument("--captures-csv", type=str,
                   default="results/phase10D4A_candidate_diagnostics_captures.csv")
    p.add_argument("--summary-csv", type=str,
                   default="results/phase10D4A_candidate_diagnostics_summary.csv")
    p.add_argument("--summary-json", type=str,
                   default="results/phase10D4A_candidate_diagnostics_summary.json")
    args = p.parse_args(argv)

    decision_points = set(range(WARMUP_END, TOTAL_STEPS, DECISION_INTERVAL))
    n_decisions = len(decision_points)

    print("Phase 10D.4A -- Candidate Diagnostics Smoke")
    print(f"  seeds={args.seeds}  unit_count=300  steps={TOTAL_STEPS}  warmup={WARMUP_END}")
    print(f"  decision_points={n_decisions}  interval={DECISION_INTERVAL}")
    print(f"  h_tau={HISTORICAL_CONTEXT_TAU}  clip=True  h[u] read-only")
    print(f"  candidates: background / novelty / surprise_magnitude / signed_surprise")
    print(f"  scope: tau=10000 only, no rarity/progress, no tau ladder")
    print()

    if args.dry_run_schedule:
        dp_list = sorted(decision_points)
        print(f"  Arms: closed_loop, exact_replay, divergent_warmup_replay, matched_warmup_control")
        print(f"  Decision points (first 5): {dp_list[:5]}...")
        print(f"  Decision points (last 5): ...{dp_list[-5:]}")
        print(f"  Warmup: 0-{WARMUP_END-1} (weights frozen)")
        print(f"  Replay: {WARMUP_END}-{TOTAL_STEPS-1} (9C+9D ON)")
        print(f"  Per-step: h_pre + acts_pre + tag_pre + slow_pre snapshots")
        print(f"  phi_conn proxy: activation at capture time (not clean event-response delta)")
        print(f"  Estimated per seed: ~5-9 min")
        print(f"  Total: ~10-18 min for 2 seeds")
        print()
        return 0

    code_sha = _git_sha()
    all_summaries = []
    all_capture_rows = []
    h_snapshots = {}

    if args.estimate_only:
        est_total = 0.0
        for seed in args.seeds:
            print(f"-- Seed {seed} (estimate) --")
            cfg = _make_cfg(seed)
            config_sha = hashlib.sha256(
                json.dumps({k: v for k, v in cfg.__dict__.items()
                            if not k.startswith("_")},
                           sort_keys=True, default=str).encode()
            ).hexdigest()[:16]
            print(f"  Sampling closed_loop...", end=" ", flush=True)
            t0 = time.time()
            _, s_info, _, _, _, _ = run_closed_loop(
                cfg, seed_env=seed, seed_sched=seed + 1000,
                decision_points=decision_points, pulse_dur=PULSE_DURATION,
                code_sha=code_sha, config_sha=config_sha)
            wall = time.time() - t0
            print(f"{wall:.0f}s  events={s_info.get('event_count', 0)}"
                  f"  captures={s_info['capture_count']}")
            est_seed = wall * 4.5
            est_total += est_seed
            print(f"    Estimated per seed: ~{est_seed:.0f}s = ~{est_seed/60:.1f} min")
        print(f"\n  Total estimate: ~{est_total:.0f}s = ~{est_total/60:.1f} min")
        if est_total > 900:
            print(f"  <- ECS recommended (>15 min)")
        else:
            print(f"  <- OK for local")
        return 0

    # ── Full run ──
    for seed in args.seeds:
        print(f"== Seed {seed} ==")
        cfg_9c_9d = _make_cfg(seed, event_pair_on=True, consolidation_on=True)
        config_sha = hashlib.sha256(
            json.dumps({k: v for k, v in cfg_9c_9d.__dict__.items()
                        if not k.startswith("_")},
                       sort_keys=True, default=str).encode()
        ).hexdigest()[:16]

        print(f"  [1/4] closed_loop ...", end=" ", flush=True)
        t0 = time.time()
        el_cl, s_cl, led_cl, h_wu_cl, h_fin_cl, cap_cl = run_closed_loop(
            cfg_9c_9d, seed_env=seed, seed_sched=seed + 1000,
            decision_points=decision_points, pulse_dur=PULSE_DURATION,
            code_sha=code_sha, config_sha=config_sha)
        wall = time.time() - t0
        h_snapshots[(seed, "closed_loop")] = (h_wu_cl, h_fin_cl)
        event_trace = [(d["t_decision"], d["chosen_event"], d["payload_hash"])
                       for d in el_cl if d["chosen_event"] != "none"]
        trace_hash = hashlib.sha256(
            "|".join(f"{t}:{e}:{h}" for t, e, h in event_trace).encode()
        ).hexdigest()[:16]
        s_cl.update({"trace_hash": trace_hash, "wall_time_s": round(wall, 1)})
        all_summaries.append(s_cl)
        all_capture_rows.extend(cap_cl)
        print(f"{wall:.0f}s  events={s_cl.get('event_count', 0)}"
              f"  captures={s_cl['capture_count']}"
              f"  best={s_cl['best_candidate']}"
              f"  novelty={s_cl.get('mean_novelty_alignment', 'nan')}"
              f"  pos_surp={s_cl.get('mean_pos_surprise_alignment', 'nan')}")

        print(f"  [2/4] exact_replay ...", end=" ", flush=True)
        t0 = time.time()
        cfg_exact = _make_cfg(seed, event_pair_on=True, consolidation_on=True)
        el_ex, s_ex, led_ex, h_wu_ex, h_fin_ex, cap_ex = run_exact_replay(
            cfg_exact, seed_env=seed, event_trace=event_trace,
            pulse_dur=PULSE_DURATION, code_sha=code_sha, config_sha=config_sha)
        wall = time.time() - t0
        h_snapshots[(seed, "exact_replay")] = (h_wu_ex, h_fin_ex)
        replay_exact = (s_ex["hash_mismatches"] == 0
                        and s_ex["n_replayed"] == s_ex["n_expected"])
        s_ex.update({"trace_hash": trace_hash, "wall_time_s": round(wall, 1),
                     "replay_exact": replay_exact})
        all_summaries.append(s_ex)
        all_capture_rows.extend(cap_ex)
        status = "EXACT" if replay_exact else "MISMATCH"
        print(f"{wall:.0f}s  replayed={s_ex['n_replayed']}"
              f"  captures={s_ex['capture_count']}"
              f"  w_delta={s_ex['warmup_weight_delta_l1']:.6f}"
              f"  [{status}]")

        print(f"  [3/4] divergent_warmup_replay ...", end=" ", flush=True)
        t0 = time.time()
        el_dv, s_dv, led_dv, h_wu_dv, h_fin_dv, cap_dv = run_divergent_warmup_replay(
            seed_env=seed, event_trace=event_trace,
            pulse_dur=PULSE_DURATION, code_sha=code_sha)
        wall = time.time() - t0
        h_snapshots[(seed, "divergent_warmup_replay")] = (h_wu_dv, h_fin_dv)
        replay_div = (s_dv["hash_mismatches"] == 0
                      and s_dv["n_replayed"] == s_dv["n_expected"])
        s_dv.update({"trace_hash": trace_hash, "wall_time_s": round(wall, 1),
                     "replay_exact": replay_div})
        all_summaries.append(s_dv)
        all_capture_rows.extend(cap_dv)
        p6_ok = s_dv.get("warmup_act_div", 0.0) > 1e-8
        print(f"{wall:.0f}s  replayed={s_dv['n_replayed']}"
              f"  captures={s_dv['capture_count']}"
              f"  act_div={s_dv.get('warmup_act_div', 0):.6f}"
              f"  [P6={'OK' if p6_ok else 'FAIL'}]")

        print(f"  [4/4] matched_warmup_control ...", end=" ", flush=True)
        t0 = time.time()
        _, s_mc, led_mc, h_wu_mc, h_fin_mc, cap_mc = run_matched_warmup_control(
            seed_env=seed, pulse_dur=PULSE_DURATION, code_sha=code_sha)
        wall = time.time() - t0
        h_snapshots[(seed, "matched_warmup_control")] = (h_wu_mc, h_fin_mc)
        s_mc["wall_time_s"] = round(wall, 1)
        all_summaries.append(s_mc)
        all_capture_rows.extend(cap_mc)
        print(f"{wall:.0f}s  captures={s_mc['capture_count']}"
              f"  w_delta={s_mc['warmup_weight_delta_l1']:.6f}  [baseline only]")

    # ── Cross-arm comparison + protocol checks ──
    print()
    print("== Candidate Alignment Summary ==")
    all_pass = True
    for seed in args.seeds:
        h_wu_cl, h_fin_cl = h_snapshots.get((seed, "closed_loop"), (None, None))
        h_wu_ex, h_fin_ex = h_snapshots.get((seed, "exact_replay"), (None, None))
        h_wu_dv, h_fin_dv = h_snapshots.get((seed, "divergent_warmup_replay"), (None, None))
        if h_fin_cl is None:
            continue

        cl_vs_ex_l1 = (float(np.sum(np.abs(h_fin_cl - h_fin_ex)))
                       if h_fin_ex is not None else float("nan"))
        cl_vs_dv_l1 = (float(np.sum(np.abs(h_fin_cl - h_fin_dv)))
                       if h_fin_dv is not None else float("nan"))
        h_l1_ref = float(np.sum(h_fin_cl))
        h1_threshold = 0.01 * h_l1_ref
        h1_pass = cl_vs_dv_l1 > h1_threshold if not np.isnan(cl_vs_dv_l1) else False
        p5_pass = cl_vs_ex_l1 < 1e-6 if not np.isnan(cl_vs_ex_l1) else False

        by_arm = {s["arm"]: s for s in all_summaries if s["seed_env"] == seed}
        cl = by_arm.get("closed_loop", {})
        ex = by_arm.get("exact_replay", {})
        dv = by_arm.get("divergent_warmup_replay", {})

        p1 = cl.get("event_count", 0) > 0
        p2 = ex.get("n_replayed", 0) == ex.get("n_expected", -1)
        p3 = ex.get("hash_mismatches", 1) == 0
        p4 = cl.get("capture_count", 0) > 0
        p7_ex = ex.get("warmup_weight_delta_l1", 1.0) < 1e-6
        p7_dv = dv.get("warmup_weight_delta_l1", 1.0) < 1e-6
        p6 = dv.get("warmup_act_div", 0.0) > 1e-8
        ok = lambda v: "OK" if v else "FAIL"
        checks = [p1, p2, p3, p4, p5_pass, p6, p7_ex and p7_dv]
        seed_pass = all(checks)
        all_pass = all_pass and seed_pass

        cl_bg = cl.get("mean_h_tag_cosine", "nan")
        cl_nv = cl.get("mean_novelty_alignment", "nan")
        cl_sm = cl.get("mean_surprise_mag_alignment", "nan")
        cl_ps = cl.get("mean_pos_surprise_alignment", "nan")
        cl_ns = cl.get("mean_neg_surprise_alignment", "nan")
        cl_rank = cl.get("candidate_rank", "none")

        try:
            bg_v = float(cl_bg) if cl_bg != "nan" else float("nan")
            nv_v = float(cl_nv) if cl_nv != "nan" else float("nan")
            ps_v = float(cl_ps) if cl_ps != "nan" else float("nan")
            any_beats_bg = ((not np.isnan(nv_v) and nv_v > bg_v) or
                            (not np.isnan(ps_v) and ps_v > bg_v))
        except (ValueError, TypeError):
            any_beats_bg = False

        print(f"  Seed {seed}:")
        print(f"    P1={ok(p1)} P2={ok(p2)} P3={ok(p3)} P4={ok(p4)}"
              f" P5={ok(p5_pass)} P6={ok(p6)} P7={ok(p7_ex and p7_dv)}"
              f" H1={ok(h1_pass)} -> {'PASS' if seed_pass else 'FAIL'}")
        print(f"    background  = {cl_bg}")
        print(f"    novelty     = {cl_nv}"
              f"  (delta: {cl.get('mean_background_vs_novelty_delta', 'nan')})")
        print(f"    surp_mag    = {cl_sm}"
              f"  (delta: {cl.get('mean_background_vs_surprise_mag_delta', 'nan')})")
        print(f"    pos_surp    = {cl_ps}"
              f"  (delta: {cl.get('mean_background_vs_pos_surprise_delta', 'nan')})")
        print(f"    neg_surp    = {cl_ns}")
        print(f"    signed_corr = {cl.get('mean_signed_surprise_slow_corr', 'nan')}")
        print(f"    h_tag_ratio = {cl.get('mean_h_tag_ratio', 'nan')}")
        print(f"    rank        = {cl_rank}")
        print(f"    verdict     = {'candidate_signal_present' if any_beats_bg else 'no_candidate_beats_background'}")

        for s in all_summaries:
            if s["seed_env"] != seed:
                continue
            s["closed_vs_exact_h_l1"] = round(cl_vs_ex_l1, 8)
            s["closed_vs_divergent_h_l1"] = round(cl_vs_dv_l1, 8)
            s["h1_threshold"] = round(h1_threshold, 8)
            s["h1_pass"] = h1_pass
            s["p5_pass"] = p5_pass
            s["p7_pass"] = p7_ex and p7_dv
            s["seed_verdict"] = ("candidate_signal_present" if any_beats_bg
                                 else "no_candidate_beats_background")
            s["p1_p7_protocol_pass"] = seed_pass

    print()
    print(f"Overall: {'ALL PASS' if all_pass else 'SOME FAIL'}")

    # ── Save outputs ──
    _save_csv(all_capture_rows, args.captures_csv)
    _save_csv(all_summaries, args.summary_csv)

    with open(args.summary_json, "w", encoding="utf-8") as fj:
        json.dump(all_summaries, fj, indent=2, default=str)

    print()
    print(f"captures  -> {args.captures_csv}")
    print(f"summary   -> {args.summary_csv}")
    print(f"summary   -> {args.summary_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
