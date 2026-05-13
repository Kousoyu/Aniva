"""Phase 10E.1 — Tag Formation Historical Context Diagnostics.

Core question: does h[u] predict which connections receive nonzero tag_delta
during event-pair plasticity, before slow consolidation writes them?

Targets (upstream of slow_delta):
  tag_presence  — binary: |tag_delta| > eps
  tag_strength  — |tag_delta|
  dtag          — tag_after - tag_before (= abs(event_pair_dW))
  event_pair_dW — raw weight update (accessible via weight_cache diff)

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
TAG_EPS = 1e-10


def _unit_region(pos):
    x = pos[0]
    if x < -0.1: return "L"
    elif x > 0.1: return "R"
    return "M"


def _subgraph(src_reg, tgt_reg):
    return src_reg + tgt_reg


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

def _pearson(a, b):
    if len(a) < 2: return float("nan")
    sa, sb = float(np.std(a)), float(np.std(b))
    if sa < 1e-12 or sb < 1e-12: return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def _spearman(a, b):
    if len(a) < 2: return float("nan")
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    return _pearson(ra, rb)


def _rank_auc(scores, labels):
    """Rank-AUC = P(score_pos > score_neg). O(n log n) via rank-sum."""
    labels = np.asarray(labels, dtype=np.int8)
    n_pos = int(np.sum(labels == 1))
    n_neg = int(np.sum(labels == 0))
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    ranks = np.argsort(np.argsort(scores)) + 1  # 1-indexed
    rank_sum_pos = float(np.sum(ranks[labels == 1]))
    return (rank_sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def _percentile_rank(observed, distribution):
    dist = np.array(distribution)
    if len(dist) == 0: return float("nan")
    return float(np.mean(dist < observed))


# ═══════════════════════════════════════════════════════════════════
# Per-event capture
# ═══════════════════════════════════════════════════════════════════

def _capture_event_rows(core, h_pre, acts_pre, tag_pre, w_pre,
                        seed, arm, event_index, event_step, event_type):
    """Build one row per connection for a single event-pair update."""
    eps = 1e-9
    src_idx = core._source_indices
    tgt_idx = core._target_indices
    positions = core._positions

    h_conn = 0.5 * (h_pre[src_idx] + h_pre[tgt_idx])
    h_max = float(np.max(h_conn))
    h_norm_conn = h_conn / (h_max + eps)
    novelty_factor = 1.0 - h_norm_conn

    phi_conn = 0.5 * (acts_pre[src_idx] + acts_pre[tgt_idx])
    surprise_factor = np.abs(phi_conn - h_norm_conn)
    pos_factor = np.maximum(0.0, phi_conn - h_norm_conn)
    neg_factor = np.maximum(0.0, h_norm_conn - phi_conn)

    tag_after = core._tag_cache.copy()
    tag_delta = tag_after - tag_pre
    tag_presence = (np.abs(tag_delta) > TAG_EPS).astype(np.int8)
    tag_strength = np.abs(tag_delta)

    w_after = core._weight_cache.copy()
    event_pair_dW = w_after - w_pre
    baseline_weight_abs = np.abs(w_pre)

    src_regions = [_unit_region(positions[u]) for u in src_idx]
    tgt_regions = [_unit_region(positions[u]) for u in tgt_idx]

    rows = []
    for i in range(len(src_idx)):
        rows.append({
            "seed": seed, "arm": arm,
            "event_index": event_index, "event_step": event_step,
            "event_type": event_type,
            "connection_id": i,
            "src": int(src_idx[i]), "tgt": int(tgt_idx[i]),
            "src_region": src_regions[i], "tgt_region": tgt_regions[i],
            "subgraph": _subgraph(src_regions[i], tgt_regions[i]),
            "h_conn": round(float(h_conn[i]), 8),
            "h_norm_conn": round(float(h_norm_conn[i]), 8),
            "novelty_factor": round(float(novelty_factor[i]), 8),
            "surprise_factor": round(float(surprise_factor[i]), 8),
            "pos_factor": round(float(pos_factor[i]), 8),
            "neg_factor": round(float(neg_factor[i]), 8),
            "tag_before": round(float(tag_pre[i]), 8),
            "tag_after": round(float(tag_after[i]), 8),
            "tag_delta": round(float(tag_delta[i]), 8),
            "tag_presence": int(tag_presence[i]),
            "tag_strength": round(float(tag_strength[i]), 8),
            "baseline_weight_abs": round(float(baseline_weight_abs[i]), 8),
            "phi_conn": round(float(phi_conn[i]), 8),
            "phi_proxy": True,
            "event_pair_dW": round(float(event_pair_dW[i]), 8),
            "event_pair_dW_available": True,
        })
    return rows


# ═══════════════════════════════════════════════════════════════════
# Summary computation
# ═══════════════════════════════════════════════════════════════════

def _compute_group_summary(rows, seed, arm, event_type, n_shuffles, shuffle_rng):
    """Compute diagnostics for one seed × arm × event_type group."""
    if not rows:
        return None
    novelty = np.array([r["novelty_factor"] for r in rows], dtype=np.float64)
    h_conn = np.array([r["h_conn"] for r in rows], dtype=np.float64)
    surprise = np.array([r["surprise_factor"] for r in rows], dtype=np.float64)
    pos_f = np.array([r["pos_factor"] for r in rows], dtype=np.float64)
    neg_f = np.array([r["neg_factor"] for r in rows], dtype=np.float64)
    presence = np.array([r["tag_presence"] for r in rows], dtype=np.int8)
    strength = np.array([r["tag_strength"] for r in rows], dtype=np.float64)

    n_conn = len(rows)
    n_tagged = int(np.sum(presence))
    tag_rate = n_tagged / n_conn if n_conn > 0 else float("nan")

    tagged_mask = presence == 1
    untagged_mask = ~tagged_mask

    mean_h_tagged = float(np.mean(h_conn[tagged_mask])) if tagged_mask.any() else float("nan")
    mean_h_untagged = float(np.mean(h_conn[untagged_mask])) if untagged_mask.any() else float("nan")
    mean_nv_tagged = float(np.mean(novelty[tagged_mask])) if tagged_mask.any() else float("nan")
    mean_nv_untagged = float(np.mean(novelty[untagged_mask])) if untagged_mask.any() else float("nan")

    h_tag_ratio = (mean_h_tagged / mean_h_untagged
                   if mean_h_untagged and not np.isnan(mean_h_untagged) and mean_h_untagged > 1e-12
                   else float("nan"))
    novelty_tag_ratio = (mean_nv_tagged / mean_nv_untagged
                         if mean_nv_untagged and not np.isnan(mean_nv_untagged) and mean_nv_untagged > 1e-12
                         else float("nan"))

    # AUC: lower h → tagged, so invert h for AUC
    auc_h = _rank_auc(-h_conn, presence)
    auc_novelty = _rank_auc(novelty, presence)
    auc_surprise = _rank_auc(surprise, presence)
    auc_pos = _rank_auc(pos_f, presence)
    auc_neg = _rank_auc(neg_f, presence)

    # Strength correlations (within tagged only)
    if tagged_mask.sum() >= 2:
        corr_h_str = _spearman(h_conn[tagged_mask], strength[tagged_mask])
        corr_nv_str = _spearman(novelty[tagged_mask], strength[tagged_mask])
        corr_sur_str = _spearman(surprise[tagged_mask], strength[tagged_mask])
    else:
        corr_h_str = corr_nv_str = corr_sur_str = float("nan")

    # Shuffle null for novelty and surprise AUC
    shuffle_nv_aucs, shuffle_sur_aucs = [], []
    for _ in range(n_shuffles):
        h_shuf = shuffle_rng.permutation(h_conn)
        nv_shuf = 1.0 - h_shuf / (float(np.max(h_shuf)) + 1e-9)
        sur_shuf = np.abs(np.array([r["phi_conn"] for r in rows]) - h_shuf / (float(np.max(h_shuf)) + 1e-9))
        shuffle_nv_aucs.append(_rank_auc(nv_shuf, presence))
        shuffle_sur_aucs.append(_rank_auc(sur_shuf, presence))
    pct_nv = _percentile_rank(auc_novelty, [v for v in shuffle_nv_aucs if not np.isnan(v)])
    pct_sur = _percentile_rank(auc_surprise, [v for v in shuffle_sur_aucs if not np.isnan(v)])

    aucs = {"h": auc_h, "novelty": auc_novelty, "surprise": auc_surprise,
            "pos": auc_pos, "neg": auc_neg}
    best = max(aucs, key=lambda k: aucs[k] if not np.isnan(aucs[k]) else -1)

    # Topology confound: check if signal holds within any subgraph
    subgraphs = [r["subgraph"] for r in rows]
    unique_sg = set(subgraphs)
    sg_novelty_aucs = {}
    for sg in unique_sg:
        sg_mask = np.array([r["subgraph"] == sg for r in rows])
        if sg_mask.sum() < 4:
            continue
        sg_pres = presence[sg_mask]
        if sg_pres.sum() == 0 or sg_pres.sum() == sg_mask.sum():
            continue
        sg_nv = novelty[sg_mask]
        sg_novelty_aucs[sg] = _rank_auc(sg_nv, sg_pres)
    topology_confound = (bool(auc_novelty > 0.55) and
                         all(v < 0.52 for v in sg_novelty_aucs.values()) and
                         len(sg_novelty_aucs) >= 2)

    def _r(v): return round(v, 6) if not np.isnan(v) else "nan"

    return {
        "seed": seed, "arm": arm, "event_type": event_type,
        "n_connections": n_conn, "n_tagged": n_tagged,
        "tag_rate": _r(tag_rate),
        "h_tag_ratio": _r(h_tag_ratio),
        "novelty_tag_ratio": _r(novelty_tag_ratio),
        "auc_h_inverted": _r(auc_h),
        "auc_novelty": _r(auc_novelty),
        "auc_surprise": _r(auc_surprise),
        "auc_pos": _r(auc_pos),
        "auc_neg": _r(auc_neg),
        "corr_h_tag_strength": _r(corr_h_str),
        "corr_novelty_tag_strength": _r(corr_nv_str),
        "corr_surprise_tag_strength": _r(corr_sur_str),
        "shuffle_percentile_novelty_auc": _r(pct_nv),
        "shuffle_percentile_surprise_auc": _r(pct_sur),
        "topology_confound_flag": topology_confound,
        "best_predictor": best,
        "verdict": _group_verdict(auc_novelty, pct_nv, topology_confound),
    }


def _group_verdict(auc_novelty, pct_nv, topology_confound):
    def _ok(v): return not (isinstance(v, float) and np.isnan(v))
    if topology_confound:
        return "topology_confound"
    if _ok(auc_novelty) and auc_novelty > 0.5 and _ok(pct_nv) and pct_nv > 0.90:
        return "historical_context_influences_tag_formation"
    if _ok(auc_novelty) and auc_novelty > 0.5 and _ok(pct_nv) and pct_nv > 0.75:
        return "weak_signal"
    return "null"


# ═══════════════════════════════════════════════════════════════════
# Scheduler + config helpers
# ═══════════════════════════════════════════════════════════════════

class Scheduler:
    def __init__(self, rng):
        self._rng = rng

    def propose(self, activity_L, activity_R):
        logits = np.array([B_NONE, W * activity_R + B_L,
                           W * activity_L + B_R, B_SIM], dtype=np.float64)
        logits -= np.max(logits)
        exp_l = np.exp(logits / TAU)
        probs = exp_l / np.sum(exp_l)
        u = float(self._rng.random())
        cum = 0.0
        for i, p in enumerate(probs):
            cum += p
            if u < cum:
                return {"chosen": EVENT_SET[i]}
        return {"chosen": EVENT_SET[-1]}


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
# Arm runners
# ═══════════════════════════════════════════════════════════════════

def _run_arm_closed_loop(seed_env, decision_points):
    cfg = _make_cfg(seed_env)
    core = LifeCore(cfg)
    sched_rng = np.random.default_rng(seed_env + 1000)
    scheduler = Scheduler(sched_rng)
    env = Environment()
    phi_cache = _build_phi_cache(core)
    event_rows = []
    event_log = []
    event_index = 0

    _run_warmup_weight_frozen(core, WARMUP_END, env)

    for s in range(WARMUP_END, TOTAL_STEPS):
        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)

        if s in decision_points:
            act_l, act_r = _compute_region_activity(core)
            result = scheduler.propose(act_l, act_r)
            chosen = result["chosen"]
            if chosen != "none":
                phi = phi_cache[chosen]
                # Snapshot before event-pair update
                h_pre = core._historical_context_trace.copy()
                acts_pre = core._activations.copy()
                tag_pre = core._tag_cache.copy() if core._tag_cache is not None else None
                w_pre = core._weight_cache.copy()

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

                if tag_pre is not None:
                    rows = _capture_event_rows(core, h_pre, acts_pre, tag_pre, w_pre,
                                               seed_env, "closed_loop",
                                               event_index, s, chosen)
                    event_rows.extend(rows)
                event_log.append({"t": s, "chosen": chosen,
                                  "phi_hash": hashlib.sha256(phi.tobytes()).hexdigest()[:16]})
                event_index += 1

    return event_rows, event_log


def _run_arm_exact_replay(seed_env, event_log):
    """Mirror control: same warmup, same events, same h trajectory."""
    cfg = _make_cfg(seed_env)
    core = LifeCore(cfg)
    phi_cache = _build_phi_cache(core)
    env = Environment()
    event_rows = []
    hash_mismatches = 0
    replay_idx = 0

    _run_warmup_weight_frozen(core, WARMUP_END, env)

    for s in range(WARMUP_END, TOTAL_STEPS):
        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)

        while replay_idx < len(event_log) and event_log[replay_idx]["t"] == s:
            entry = event_log[replay_idx]
            chosen = entry["chosen"]
            phi = phi_cache[chosen]
            actual_hash = hashlib.sha256(phi.tobytes()).hexdigest()[:16]
            if actual_hash != entry["phi_hash"]:
                hash_mismatches += 1

            h_pre = core._historical_context_trace.copy()
            acts_pre = core._activations.copy()
            tag_pre = core._tag_cache.copy() if core._tag_cache is not None else None
            w_pre = core._weight_cache.copy()

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

            if tag_pre is not None:
                rows = _capture_event_rows(core, h_pre, acts_pre, tag_pre, w_pre,
                                           seed_env, "exact_replay",
                                           replay_idx, s, chosen)
                event_rows.extend(rows)
            replay_idx += 1

    return event_rows, hash_mismatches  # exact_replay end


def _run_arm_divergent(seed_env, event_log):
    """Key test arm: divergent warmup → different h[u] → same events."""
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
    event_rows = []
    hash_mismatches = 0
    replay_idx = 0

    for s in range(WARMUP_END, TOTAL_STEPS):
        influences = env_replay.compute_influences(core_replay.units, s)
        core_replay.step(env_influences=influences if influences else None)

        while replay_idx < len(event_log) and event_log[replay_idx]["t"] == s:
            entry = event_log[replay_idx]
            chosen = entry["chosen"]
            phi = phi_cache[chosen]
            actual_hash = hashlib.sha256(phi.tobytes()).hexdigest()[:16]
            if actual_hash != entry["phi_hash"]:
                hash_mismatches += 1

            h_pre = core_replay._historical_context_trace.copy()
            acts_pre = core_replay._activations.copy()
            tag_pre = (core_replay._tag_cache.copy()
                       if core_replay._tag_cache is not None else None)
            w_pre = core_replay._weight_cache.copy()

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

            if tag_pre is not None:
                rows = _capture_event_rows(core_replay, h_pre, acts_pre, tag_pre, w_pre,
                                           seed_env, "divergent_warmup_replay",
                                           replay_idx, s, chosen)
                event_rows.extend(rows)
            replay_idx += 1

    return event_rows, hash_mismatches  # divergent end


# ═══════════════════════════════════════════════════════════════════
# Output helpers
# ═══════════════════════════════════════════════════════════════════

def _save_csv(rows, path):
    if not rows:
        return
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _build_summaries(all_event_rows, n_shuffles, shuffle_rng):
    from collections import defaultdict
    groups = defaultdict(list)
    for r in all_event_rows:
        key = (r["seed"], r["arm"], r["event_type"])
        groups[key].append(r)
        all_key = (r["seed"], r["arm"], "ALL")
        groups[all_key].append(r)

    summaries = []
    for (seed, arm, etype), rows in sorted(groups.items()):
        s = _compute_group_summary(rows, seed, arm, etype, n_shuffles, shuffle_rng)
        if s is not None:
            summaries.append(s)
    return summaries


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Phase 10E.1 Tag Formation Historical Context Diagnostics")
    parser.add_argument("--seeds", nargs="+", type=int, default=[42, 77])
    parser.add_argument("--dry-run-schedule", action="store_true")
    parser.add_argument("--estimate-only", action="store_true")
    parser.add_argument("--n-shuffles", type=int, default=100)
    parser.add_argument("--events-csv",
                        default="results/phase10E1_tag_formation_events.csv")
    parser.add_argument("--summary-csv",
                        default="results/phase10E1_tag_formation_summary.csv")
    parser.add_argument("--summary-json",
                        default="results/phase10E1_tag_formation_summary.json")
    args = parser.parse_args()

    seeds = args.seeds
    n_shuffles = args.n_shuffles
    decision_points = set(range(WARMUP_END, TOTAL_STEPS, DECISION_INTERVAL))

    print("Phase 10E.1 Tag Formation Historical Context Diagnostics")
    print(f"  seeds={seeds}  n_shuffles={n_shuffles}")
    print(f"  TOTAL_STEPS={TOTAL_STEPS}  WARMUP_END={WARMUP_END}")
    print(f"  decision_points={len(decision_points)}")

    if args.dry_run_schedule:
        print("[dry-run-schedule] config OK, exiting.")
        return 0

    if args.estimate_only:
        steps = (TOTAL_STEPS - WARMUP_END) * 3 * len(seeds)
        est = steps / 500
        n_conn_est = 300 * 300 * 0.05  # rough: 5% connectivity
        n_events_est = len(decision_points) * 0.7  # ~70% non-none
        rows_est = int(n_conn_est * n_events_est * 3 * len(seeds))
        print(f"[estimate] ~{est:.0f}s ({est/60:.1f} min) — "
              f"{len(seeds)} seeds × 3 arms × {TOTAL_STEPS - WARMUP_END} steps")
        print(f"[estimate] ~{rows_est:,} event rows expected")
        return 0

    all_event_rows = []
    seed_meta = []

    for seed in seeds:
        print(f"\n=== seed={seed} ===")
        t0 = time.time()

        print("  [1/3] closed_loop ...")
        cl_rows, event_log = _run_arm_closed_loop(seed, decision_points)
        n_events = len(event_log)
        print(f"    events={n_events}  rows={len(cl_rows)}")
        all_event_rows.extend(cl_rows)

        print("  [2/3] exact_replay ...")
        er_rows, er_mm = _run_arm_exact_replay(seed, event_log)
        print(f"    rows={len(er_rows)}  hash_mismatches={er_mm}")
        all_event_rows.extend(er_rows)

        print("  [3/3] divergent_warmup_replay ...")
        dv_rows, dv_mm = _run_arm_divergent(seed, event_log)
        print(f"    rows={len(dv_rows)}  hash_mismatches={dv_mm}")
        all_event_rows.extend(dv_rows)

        elapsed = time.time() - t0
        print(f"  seed={seed} done in {elapsed:.1f}s")
        seed_meta.append({
            "seed": seed, "n_events": n_events,
            "n_cl_rows": len(cl_rows), "n_er_rows": len(er_rows),
            "n_dv_rows": len(dv_rows),
            "er_hash_mismatches": er_mm, "dv_hash_mismatches": dv_mm,
            "elapsed_s": round(elapsed, 2),
        })

    # Protocol checks
    checks = {}
    for sm in seed_meta:
        s = sm["seed"]
        checks[f"P1_cl_rows_gt0_seed{s}"] = sm["n_cl_rows"] > 0
        checks[f"P2_er_rows_gt0_seed{s}"] = sm["n_er_rows"] > 0
        checks[f"P3_dv_rows_gt0_seed{s}"] = sm["n_dv_rows"] > 0
        checks[f"P4_er_hash_ok_seed{s}"] = sm["er_hash_mismatches"] == 0
        checks[f"P5_dv_hash_ok_seed{s}"] = sm["dv_hash_mismatches"] == 0
        checks[f"P6_cl_er_row_count_match_seed{s}"] = (
            sm["n_cl_rows"] == sm["n_er_rows"])

    all_pass = all(checks.values())
    print("\n=== Protocol Checks ===")
    for k, v in checks.items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")
    print(f"  ALL_PASS: {all_pass}")

    # Build summaries
    print("\nBuilding summaries ...")
    summary_rng = np.random.default_rng(12345)
    summaries = _build_summaries(all_event_rows, n_shuffles, summary_rng)

    # Print key results
    print("\n=== Key Results (closed_loop, ALL events) ===")
    for sm in summaries:
        if sm["arm"] == "closed_loop" and sm["event_type"] == "ALL":
            print(f"  seed={sm['seed']}  n_tagged={sm['n_tagged']}/{sm['n_connections']}"
                  f"  tag_rate={sm['tag_rate']}")
            print(f"    h_tag_ratio={sm['h_tag_ratio']}"
                  f"  novelty_tag_ratio={sm['novelty_tag_ratio']}")
            print(f"    auc_novelty={sm['auc_novelty']}"
                  f"  shuffle_pct={sm['shuffle_percentile_novelty_auc']}")
            print(f"    verdict={sm['verdict']}")

    # Save outputs
    sha = _git_sha()
    ts = int(time.time())
    _save_csv(all_event_rows, args.events_csv)
    _save_csv(summaries, args.summary_csv)

    verdicts = [sm["verdict"] for sm in summaries
                if sm["arm"] == "closed_loop" and sm["event_type"] == "ALL"]
    final_verdict = (verdicts[0] if len(set(verdicts)) == 1
                     else "mixed_" + "_".join(sorted(set(verdicts))))

    output = {
        "experiment": "phase10E1_tag_formation_historical_context_diagnostics",
        "git_sha": sha, "timestamp": ts,
        "seeds": seeds, "n_shuffles": n_shuffles,
        "total_steps": TOTAL_STEPS, "warmup_end": WARMUP_END,
        "tau": HISTORICAL_CONTEXT_TAU,
        "protocol_checks": checks, "all_protocol_pass": all_pass,
        "final_verdict": final_verdict,
        "seed_meta": seed_meta,
        "summaries": summaries,
    }
    with open(args.summary_json, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nSaved: {args.events_csv}")
    print(f"Saved: {args.summary_csv}")
    print(f"Saved: {args.summary_json}")
    print(f"\nFinal verdict: {final_verdict}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
