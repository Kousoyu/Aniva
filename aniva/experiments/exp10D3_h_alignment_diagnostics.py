"""Phase 10D.3 — h[u] Alignment Diagnostics.

Tests whether h[u] (per-unit slow activation history, τ=10000) is structurally
aligned with tag_cache / slow_weight at capture time.

h[u] is strictly read-only: does not affect gate, capture, or slow_weight.

Four-arm structure identical to 10D.2. Adds per-capture diagnostics:
  D1: h-tag alignment (connection-space cosine + tag_weighted_h)
  D2: h-weighted capture signal (Pearson corr h_conn vs |slow_delta|)
  D3: h stability across replay (warmup-end vs final cosine)
  D4: h concentration profile (HHI, effective_support, Gini)
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


def _hash_trace(trace):
    parts = [f"{t}:{e}:{h}" for t, e, h in trace]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


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


def _tag_mass(core):
    if core._tag_cache is None:
        return 0.0
    return float(np.sum(np.abs(core._tag_cache)))


def _n_tagged(core):
    if core._tag_cache is None:
        return 0
    return int(np.sum(core._tag_cache > 0))


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
    """Run warmup with weights frozen every step.
    State (activations, energies, h[u], traces) evolves normally.
    Returns (warmup_weight_delta, nan_hit)."""
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
# Diagnostic helpers (D1-D4)
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


def _gini(arr):
    arr = np.sort(np.abs(arr))
    n = len(arr)
    if n == 0 or arr.sum() < 1e-12:
        return 0.0
    idx = np.arange(1, n + 1, dtype=np.float64)
    return float((2.0 * np.sum(idx * arr) / (n * arr.sum())) - (n + 1.0) / n)


def _h_concentration(h):
    """D4: HHI concentration, effective_support, Gini."""
    h_sum = float(np.sum(h))
    n = len(h)
    if h_sum > 0.0:
        p = h / h_sum
        hhi = float(np.sum(p ** 2))
        eff_support = 1.0 / hhi if hhi > 0.0 else float(n)
    else:
        hhi = 0.0
        eff_support = 0.0
    return hhi, eff_support, _gini(h)


def _h_capture_diag(h_pre, tag_pre, slow_delta, src_idx, tgt_idx,
                    ledger_entry, seed, arm, capture_idx):
    """Compute D1+D2 diagnostics at a single capture event.

    h_pre, tag_pre: per-unit/per-connection snapshots BEFORE the step.
    slow_delta: per-connection slow_weight change in this step.
    """
    # Project h[u] to connection space
    h_conn = 0.5 * (h_pre[src_idx] + h_pre[tgt_idx])

    # D1: h-tag alignment (connection space)
    tag_abs = np.abs(tag_pre)
    tag_sum = float(np.sum(tag_abs))
    h_tag_cosine = _cosine(h_conn, tag_abs)
    tag_weighted_h = (float(np.sum(tag_abs * h_conn)) / tag_sum
                      if tag_sum > 1e-12 else 0.0)
    h_conn_mean = float(np.mean(h_conn))
    tagged_mask = tag_abs > 1e-10
    h_tagged_mean = (float(np.mean(h_conn[tagged_mask]))
                     if tagged_mask.any() else 0.0)
    h_untagged_mean = (float(np.mean(h_conn[~tagged_mask]))
                       if (~tagged_mask).any() else 0.0)
    h_tag_ratio = h_tagged_mean / (h_untagged_mean + 1e-9)

    # D2: h-weighted capture signal
    slow_abs = np.abs(slow_delta)
    h_capture_corr = _pearson(h_conn, slow_abs)
    slow_sum = float(np.sum(slow_abs))
    h_weighted_slow_delta = (float(np.sum(h_conn * slow_abs)) /
                             (float(np.sum(h_conn)) + 1e-9))

    # h concentration at capture
    hhi, eff_support, gini = _h_concentration(h_pre)

    return {
        "seed": seed, "arm": arm, "capture_index": capture_idx,
        "capture_step": ledger_entry.get("capture_step", ""),
        "capture_signal": round(ledger_entry.get("capture_signal", 0.0), 8),
        "tag_mass": round(float(tag_sum), 8),
        "slow_delta_l1": round(float(slow_sum), 8),
        "h_l1": round(float(np.sum(h_pre)), 8),
        "h_mean": round(float(np.mean(h_pre)), 8),
        "h_max": round(float(np.max(h_pre)), 8),
        "h_concentration": round(hhi, 8),
        "h_effective_support": round(eff_support, 4),
        "h_gini": round(gini, 8),
        "h_tag_cosine": round(h_tag_cosine, 8),
        "tag_weighted_h": round(tag_weighted_h, 8),
        "h_tagged_mean": round(h_tagged_mean, 8),
        "h_untagged_mean": round(h_untagged_mean, 8),
        "h_tag_ratio": round(h_tag_ratio, 6),
        "h_capture_corr": round(h_capture_corr, 8),
        "h_weighted_slow_delta": round(h_weighted_slow_delta, 8),
    }


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
        tag_pre = core._tag_cache.copy() if core._tag_cache is not None else None
        slow_pre = core._slow_weight_cache.copy() if core._slow_weight_cache is not None else None

        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)
        if not nan_hit and np.any(np.isnan(core._activations)):
            nan_hit = True

        if (tag_pre is not None and slow_pre is not None and
                len(core._consolidation_ledger) > ledger_before):
            slow_delta = core._slow_weight_cache - slow_pre
            diag = _h_capture_diag(h_pre, tag_pre, slow_delta,
                                   core._source_indices, core._target_indices,
                                   core._consolidation_ledger[-1],
                                   seed_env, "closed_loop", len(capture_diags))
            capture_diags.append(diag)

        if s in decision_points:
            act_l, act_r = _compute_region_activity(core)
            result = scheduler.propose(act_l, act_r)
            chosen = result["chosen"]
            row = {"run_id": f"phase10D3_closed_seed{seed_env}",
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
    hhi_f, eff_f, gini_f = _h_concentration(h_final)
    hhi_w, eff_w, gini_w = _h_concentration(h_warmup_end)
    h3_cosine = _cosine(h_warmup_end, h_final)
    h3_l1 = float(np.sum(np.abs(h_warmup_end - h_final)))
    h_wu_l1 = float(np.sum(h_warmup_end))
    h_fin_l1 = float(np.sum(h_final))
    h_decay_ratio = h_fin_l1 / h_wu_l1 if h_wu_l1 > 1e-12 else 0.0

    mean_h_tag_cosine = (float(np.mean([d["h_tag_cosine"] for d in capture_diags]))
                         if capture_diags else float("nan"))
    mean_tag_weighted_h = (float(np.mean([d["tag_weighted_h"] for d in capture_diags]))
                           if capture_diags else float("nan"))
    mean_h_capture_corr = (float(np.mean([d["h_capture_corr"] for d in capture_diags]))
                           if capture_diags else float("nan"))
    mean_h_tag_ratio = (float(np.mean([d["h_tag_ratio"] for d in capture_diags]))
                        if capture_diags else float("nan"))

    summary = {
        "arm": "closed_loop", "seed_env": seed_env, "event_count": n_ev,
        "L_count": sum(1 for d in event_log if d["chosen_event"] == "L"),
        "R_count": sum(1 for d in event_log if d["chosen_event"] == "R"),
        "simultaneous_count": sum(1 for d in event_log
                                  if d["chosen_event"] == "simultaneous"),
        "fast_weight_l1": round(_fast_weight_l1(core), 8),
        "slow_weight_l1": round(_slow_weight_l1(core), 8),
        "capture_count": len(ledger),
        "warmup_weight_delta_l1": round(warmup_weight_delta, 8),
        "h_l1_warmup_end": round(h_wu_l1, 8),
        "h_l1_final": round(h_fin_l1, 8),
        "h_mean_final": round(float(np.mean(h_final)), 8),
        "h_max_final": round(float(np.max(h_final)), 8),
        "h_concentration_final": round(hhi_f, 8),
        "h_effective_support_final": round(eff_f, 4),
        "h_gini_final": round(gini_f, 8),
        "h_warmup_final_cosine": round(h3_cosine, 8),
        "h_warmup_final_l1": round(h3_l1, 8),
        "h_decay_ratio": round(h_decay_ratio, 6),
        "mean_h_tag_cosine": round(mean_h_tag_cosine, 8) if not np.isnan(mean_h_tag_cosine) else "nan",
        "mean_tag_weighted_h": round(mean_tag_weighted_h, 8) if not np.isnan(mean_tag_weighted_h) else "nan",
        "mean_h_capture_corr": round(mean_h_capture_corr, 8) if not np.isnan(mean_h_capture_corr) else "nan",
        "mean_h_tag_ratio": round(mean_h_tag_ratio, 6) if not np.isnan(mean_h_tag_ratio) else "nan",
        "nan_hit": nan_hit,
    }
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
        tag_pre = core._tag_cache.copy() if core._tag_cache is not None else None
        slow_pre = core._slow_weight_cache.copy() if core._slow_weight_cache is not None else None

        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)
        if not nan_hit and np.any(np.isnan(core._activations)):
            nan_hit = True

        if (tag_pre is not None and slow_pre is not None and
                len(core._consolidation_ledger) > ledger_before):
            slow_delta = core._slow_weight_cache - slow_pre
            diag = _h_capture_diag(h_pre, tag_pre, slow_delta,
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
            event_log.append({"run_id": f"phase10D3_exact_seed{seed_env}",
                               "arm": "exact_replay", "seed_env": seed_env,
                               "code_sha": code_sha, "config_sha": config_sha,
                               "t_decision": s, "chosen_event": chosen,
                               "payload_hash": actual_hash,
                               "expected_payload_hash": exp_hash,
                               "hash_match": actual_hash == exp_hash})
            replay_idx += 1

    h_final = core._historical_context_trace.copy()
    ledger = core._consolidation_ledger if core._consolidation_ledger else []
    hhi_f, eff_f, gini_f = _h_concentration(h_final)
    h3_cosine = _cosine(h_warmup_end, h_final)
    h3_l1 = float(np.sum(np.abs(h_warmup_end - h_final)))
    h_wu_l1 = float(np.sum(h_warmup_end))
    h_fin_l1 = float(np.sum(h_final))
    h_decay_ratio = h_fin_l1 / h_wu_l1 if h_wu_l1 > 1e-12 else 0.0
    mean_h_tag_cosine = (float(np.mean([d["h_tag_cosine"] for d in capture_diags]))
                         if capture_diags else float("nan"))
    mean_tag_weighted_h = (float(np.mean([d["tag_weighted_h"] for d in capture_diags]))
                           if capture_diags else float("nan"))
    mean_h_capture_corr = (float(np.mean([d["h_capture_corr"] for d in capture_diags]))
                           if capture_diags else float("nan"))
    mean_h_tag_ratio = (float(np.mean([d["h_tag_ratio"] for d in capture_diags]))
                        if capture_diags else float("nan"))
    summary = {
        "arm": "exact_replay", "seed_env": seed_env,
        "n_expected": n_expected, "n_replayed": replay_idx,
        "hash_mismatches": hash_mismatches,
        "warmup_weight_delta_l1": round(warmup_weight_delta, 8),
        "fast_weight_l1": round(_fast_weight_l1(core), 8),
        "slow_weight_l1": round(_slow_weight_l1(core), 8),
        "capture_count": len(ledger),
        "h_l1_warmup_end": round(h_wu_l1, 8),
        "h_l1_final": round(h_fin_l1, 8),
        "h_mean_final": round(float(np.mean(h_final)), 8),
        "h_max_final": round(float(np.max(h_final)), 8),
        "h_concentration_final": round(hhi_f, 8),
        "h_effective_support_final": round(eff_f, 4),
        "h_gini_final": round(gini_f, 8),
        "h_warmup_final_cosine": round(h3_cosine, 8),
        "h_warmup_final_l1": round(h3_l1, 8),
        "h_decay_ratio": round(h_decay_ratio, 6),
        "mean_h_tag_cosine": round(mean_h_tag_cosine, 8) if not np.isnan(mean_h_tag_cosine) else "nan",
        "mean_tag_weighted_h": round(mean_tag_weighted_h, 8) if not np.isnan(mean_tag_weighted_h) else "nan",
        "mean_h_capture_corr": round(mean_h_capture_corr, 8) if not np.isnan(mean_h_capture_corr) else "nan",
        "mean_h_tag_ratio": round(mean_h_tag_ratio, 6) if not np.isnan(mean_h_tag_ratio) else "nan",
        "nan_hit": nan_hit,
    }
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

    assert np.allclose(core_div._positions, core_ref._positions)
    assert np.allclose(core_div._weight_cache, core_ref._weight_cache)

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
            diag = _h_capture_diag(h_pre, tag_pre, slow_delta,
                                   core_replay._source_indices,
                                   core_replay._target_indices,
                                   core_replay._consolidation_ledger[-1],
                                   seed_env, "divergent_warmup_replay",
                                   len(capture_diags))
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
            event_log.append({"run_id": f"phase10D3_divergent_seed{seed_env}",
                               "arm": "divergent_warmup_replay",
                               "seed_env": seed_env, "code_sha": code_sha,
                               "t_decision": s, "chosen_event": chosen,
                               "payload_hash": actual_hash,
                               "expected_payload_hash": exp_hash,
                               "hash_match": actual_hash == exp_hash})
            replay_idx += 1

    h_final = core_replay._historical_context_trace.copy()
    ledger = core_replay._consolidation_ledger if core_replay._consolidation_ledger else []
    hhi_f, eff_f, gini_f = _h_concentration(h_final)
    h3_cosine = _cosine(h_warmup_end, h_final)
    h3_l1 = float(np.sum(np.abs(h_warmup_end - h_final)))
    h_wu_l1 = float(np.sum(h_warmup_end))
    h_fin_l1 = float(np.sum(h_final))
    h_decay_ratio = h_fin_l1 / h_wu_l1 if h_wu_l1 > 1e-12 else 0.0
    mean_h_tag_cosine = (float(np.mean([d["h_tag_cosine"] for d in capture_diags]))
                         if capture_diags else float("nan"))
    mean_tag_weighted_h = (float(np.mean([d["tag_weighted_h"] for d in capture_diags]))
                           if capture_diags else float("nan"))
    mean_h_capture_corr = (float(np.mean([d["h_capture_corr"] for d in capture_diags]))
                           if capture_diags else float("nan"))
    mean_h_tag_ratio = (float(np.mean([d["h_tag_ratio"] for d in capture_diags]))
                        if capture_diags else float("nan"))
    summary = {
        "arm": "divergent_warmup_replay", "seed_env": seed_env,
        "n_expected": n_expected, "n_replayed": replay_idx,
        "hash_mismatches": hash_mismatches,
        "warmup_act_div": round(warmup_act_div, 8),
        "warmup_weight_delta_l1": round(warmup_weight_delta, 8),
        "fast_weight_l1": round(_fast_weight_l1(core_replay), 8),
        "slow_weight_l1": round(_slow_weight_l1(core_replay), 8),
        "capture_count": len(ledger),
        "h_l1_warmup_end": round(h_wu_l1, 8),
        "h_l1_final": round(h_fin_l1, 8),
        "h_mean_final": round(float(np.mean(h_final)), 8),
        "h_max_final": round(float(np.max(h_final)), 8),
        "h_concentration_final": round(hhi_f, 8),
        "h_effective_support_final": round(eff_f, 4),
        "h_gini_final": round(gini_f, 8),
        "h_warmup_final_cosine": round(h3_cosine, 8),
        "h_warmup_final_l1": round(h3_l1, 8),
        "h_decay_ratio": round(h_decay_ratio, 6),
        "mean_h_tag_cosine": round(mean_h_tag_cosine, 8) if not np.isnan(mean_h_tag_cosine) else "nan",
        "mean_tag_weighted_h": round(mean_tag_weighted_h, 8) if not np.isnan(mean_tag_weighted_h) else "nan",
        "mean_h_capture_corr": round(mean_h_capture_corr, 8) if not np.isnan(mean_h_capture_corr) else "nan",
        "mean_h_tag_ratio": round(mean_h_tag_ratio, 6) if not np.isnan(mean_h_tag_ratio) else "nan",
        "nan_hit": nan_hit,
    }
    return event_log, summary, ledger, h_warmup_end, h_final, capture_diags


# ═══════════════════════════════════════════════════════════════════
# Arm 4: matched_warmup_control
# ═══════════════════════════════════════════════════════════════════

def run_matched_warmup_control(seed_env, pulse_dur, code_sha):
    """Same divergent warmup as arm 3, no event replay after t=2000."""
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
            diag = _h_capture_diag(h_pre, tag_pre, slow_delta,
                                   core_replay._source_indices,
                                   core_replay._target_indices,
                                   core_replay._consolidation_ledger[-1],
                                   seed_env, "matched_warmup_control",
                                   len(capture_diags))
            capture_diags.append(diag)

    h_final = core_replay._historical_context_trace.copy()
    ledger = core_replay._consolidation_ledger if core_replay._consolidation_ledger else []
    hhi_f, eff_f, gini_f = _h_concentration(h_final)
    h3_cosine = _cosine(h_warmup_end, h_final)
    h3_l1 = float(np.sum(np.abs(h_warmup_end - h_final)))
    h_wu_l1 = float(np.sum(h_warmup_end))
    h_fin_l1 = float(np.sum(h_final))
    h_decay_ratio = h_fin_l1 / h_wu_l1 if h_wu_l1 > 1e-12 else 0.0
    mean_h_tag_cosine = (float(np.mean([d["h_tag_cosine"] for d in capture_diags]))
                         if capture_diags else float("nan"))
    mean_tag_weighted_h = (float(np.mean([d["tag_weighted_h"] for d in capture_diags]))
                           if capture_diags else float("nan"))
    mean_h_capture_corr = (float(np.mean([d["h_capture_corr"] for d in capture_diags]))
                           if capture_diags else float("nan"))
    mean_h_tag_ratio = (float(np.mean([d["h_tag_ratio"] for d in capture_diags]))
                        if capture_diags else float("nan"))
    summary = {
        "arm": "matched_warmup_control", "seed_env": seed_env,
        "warmup_act_div": round(warmup_act_div, 8),
        "warmup_weight_delta_l1": round(warmup_weight_delta, 8),
        "fast_weight_l1": round(_fast_weight_l1(core_replay), 8),
        "slow_weight_l1": round(_slow_weight_l1(core_replay), 8),
        "capture_count": len(ledger),
        "h_l1_warmup_end": round(h_wu_l1, 8),
        "h_l1_final": round(h_fin_l1, 8),
        "h_mean_final": round(float(np.mean(h_final)), 8),
        "h_max_final": round(float(np.max(h_final)), 8),
        "h_concentration_final": round(hhi_f, 8),
        "h_effective_support_final": round(eff_f, 4),
        "h_gini_final": round(gini_f, 8),
        "h_warmup_final_cosine": round(h3_cosine, 8),
        "h_warmup_final_l1": round(h3_l1, 8),
        "h_decay_ratio": round(h_decay_ratio, 6),
        "mean_h_tag_cosine": round(mean_h_tag_cosine, 8) if not np.isnan(mean_h_tag_cosine) else "nan",
        "mean_tag_weighted_h": round(mean_tag_weighted_h, 8) if not np.isnan(mean_tag_weighted_h) else "nan",
        "mean_h_capture_corr": round(mean_h_capture_corr, 8) if not np.isnan(mean_h_capture_corr) else "nan",
        "mean_h_tag_ratio": round(mean_h_tag_ratio, 6) if not np.isnan(mean_h_tag_ratio) else "nan",
        "nan_hit": nan_hit,
    }
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
        description="Phase 10D.3 — h[u] Alignment Diagnostics")
    p.add_argument("--seeds", type=int, nargs="+", default=[42, 77])
    p.add_argument("--estimate-only", action="store_true")
    p.add_argument("--dry-run-schedule", action="store_true")
    p.add_argument("--captures-csv", type=str,
                   default="results/phase10D3_h_alignment_captures.csv")
    p.add_argument("--summary-csv", type=str,
                   default="results/phase10D3_h_alignment_summary.csv")
    p.add_argument("--summary-json", type=str,
                   default="results/phase10D3_h_alignment_summary.json")
    args = p.parse_args(argv)

    decision_points = set(range(WARMUP_END, TOTAL_STEPS, DECISION_INTERVAL))
    n_decisions = len(decision_points)

    print("Phase 10D.3 — h[u] Alignment Diagnostics")
    print(f"  seeds={args.seeds}  unit_count=300  steps={TOTAL_STEPS}"
          f"  warmup={WARMUP_END}")
    print(f"  decision_points={n_decisions}  interval={DECISION_INTERVAL}")
    print(f"  historical_context_tau={HISTORICAL_CONTEXT_TAU}  clip=True")
    print(f"  h[u] read-only: does NOT affect gate / capture / slow_weight")
    print(f"  diagnostics: D1 h-tag alignment, D2 h-capture corr,"
          f" D3 h-stability, D4 h-concentration")
    print()

    if args.dry_run_schedule:
        dp_list = sorted(decision_points)
        print(f"  Arms: closed_loop, exact_replay,"
              f" divergent_warmup_replay, matched_warmup_control")
        print(f"  Decision points (first 5): {dp_list[:5]}...")
        print(f"  Decision points (last 5): ...{dp_list[-5:]}")
        print(f"  Warmup: 0–{WARMUP_END-1} (weights frozen)")
        print(f"  Replay: {WARMUP_END}–{TOTAL_STEPS-1} (9C+9D ON)")
        print(f"  Per-step capture monitoring: h_pre + tag_pre + slow_pre snapshots")
        print(f"  Estimated per seed: ~5-8 min (slightly slower than 10D.2)")
        print(f"  Total: ~10-16 min for 2 seeds  ← ECS recommended")
        print()
        return 0

    code_sha = _git_sha()
    all_event_rows = []
    all_summaries = []
    all_capture_rows = []
    h_snapshots = {}

    if args.estimate_only:
        for seed in args.seeds:
            print(f"── Seed {seed} (estimate) ──")
            cfg = _make_cfg(seed)
            config_sha = hashlib.sha256(
                json.dumps({k: v for k, v in cfg.__dict__.items()
                            if not k.startswith("_")},
                           sort_keys=True, default=str).encode()
            ).hexdigest()[:16]
            print(f"  Sampling closed_loop...", end=" ", flush=True)
            t0 = time.time()
            el, s_info, _, _, _, _ = run_closed_loop(
                cfg, seed_env=seed, seed_sched=seed + 1000,
                decision_points=decision_points, pulse_dur=PULSE_DURATION,
                code_sha=code_sha, config_sha=config_sha)
            wall = time.time() - t0
            n_events = s_info["event_count"]
            print(f"{wall:.0f}s  events={n_events}"
                  f"  captures={s_info['capture_count']}")
            est_total = wall * 4.5
            print(f"    Estimated per seed: ~{est_total:.0f}s = ~{est_total/60:.1f} min")
        total = est_total * len(args.seeds)
        print(f"\n  Total estimate: ~{total:.0f}s = ~{total/60:.1f} min")
        if total > 900:
            print(f"  ← ECS recommended (>15 min)")
        else:
            print(f"  ← OK for local")
        return 0

    # ── Full run ──
    for seed in args.seeds:
        print(f"══ Seed {seed} ══")
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
        all_event_rows.extend(el_cl)
        all_summaries.append(s_cl)
        all_capture_rows.extend(cap_cl)
        print(f"{wall:.0f}s  events={s_cl['event_count']}"
              f"  captures={s_cl['capture_count']}"
              f"  h_l1={s_cl['h_l1_final']:.4f}"
              f"  h_tag_cos={s_cl.get('mean_h_tag_cosine', 'nan')}"
              f"  h_cap_corr={s_cl.get('mean_h_capture_corr', 'nan')}")

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
        all_event_rows.extend(el_ex)
        all_summaries.append(s_ex)
        all_capture_rows.extend(cap_ex)
        status = "EXACT" if replay_exact else "MISMATCH"
        print(f"{wall:.0f}s  replayed={s_ex['n_replayed']}"
              f"  captures={s_ex['capture_count']}"
              f"  w_delta={s_ex['warmup_weight_delta_l1']:.6f}"
              f"  h_tag_cos={s_ex.get('mean_h_tag_cosine', 'nan')}"
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
        all_event_rows.extend(el_dv)
        all_summaries.append(s_dv)
        all_capture_rows.extend(cap_dv)
        p6_ok = s_dv.get("warmup_act_div", 0.0) > 1e-8
        print(f"{wall:.0f}s  replayed={s_dv['n_replayed']}"
              f"  captures={s_dv['capture_count']}"
              f"  act_div={s_dv.get('warmup_act_div', 0):.6f}"
              f"  h_tag_cos={s_dv.get('mean_h_tag_cosine', 'nan')}"
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
              f"  h_l1={s_mc['h_l1_final']:.4f}"
              f"  w_delta={s_mc['warmup_weight_delta_l1']:.6f}")

    # ── Cross-arm h comparison ──
    print()
    print("══ h[u] Alignment Summary ══")
    for seed in args.seeds:
        h_wu_cl, h_fin_cl = h_snapshots.get((seed, "closed_loop"), (None, None))
        h_wu_ex, h_fin_ex = h_snapshots.get((seed, "exact_replay"), (None, None))
        h_wu_dv, h_fin_dv = h_snapshots.get((seed, "divergent_warmup_replay"),
                                             (None, None))
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

        seed_sums = [s for s in all_summaries if s["seed_env"] == seed]
        by_arm = {s["arm"]: s for s in seed_sums}
        ex_wd = by_arm.get("exact_replay", {}).get("warmup_weight_delta_l1", float("nan"))
        dv_wd = by_arm.get("divergent_warmup_replay", {}).get("warmup_weight_delta_l1",
                                                               float("nan"))
        p7_pass = (ex_wd < 1e-6 and dv_wd < 1e-6)

        cl_h_tag = by_arm.get("closed_loop", {}).get("mean_h_tag_cosine", "nan")
        cl_h_corr = by_arm.get("closed_loop", {}).get("mean_h_capture_corr", "nan")
        cl_h_ratio = by_arm.get("closed_loop", {}).get("mean_h_tag_ratio", "nan")
        dv_h_tag = by_arm.get("divergent_warmup_replay", {}).get("mean_h_tag_cosine", "nan")

        try:
            h1_d1 = float(cl_h_tag) > 0.05 if cl_h_tag != "nan" else False
            h1_d2 = float(cl_h_corr) > 0.05 if cl_h_corr != "nan" else False
        except (ValueError, TypeError):
            h1_d1 = h1_d2 = False

        print(f"  Seed {seed}:")
        print(f"    closed_vs_exact_h_l1     = {cl_vs_ex_l1:.8f}"
              f"  {'← P5 OK' if p5_pass else '← P5 FAIL'}")
        print(f"    closed_vs_divergent_h_l1 = {cl_vs_dv_l1:.8f}"
              f"  (H1 threshold={h1_threshold:.4f})"
              f"  {'← H1 PASS' if h1_pass else '← H1 FAIL'}")
        print(f"    P7 warmup_weight_delta   = ex={ex_wd:.6f} dv={dv_wd:.6f}"
              f"  {'← P7 OK' if p7_pass else '← P7 FAIL'}")
        print(f"    D1 mean_h_tag_cosine     = {cl_h_tag}"
              f"  (closed)  {dv_h_tag} (divergent)"
              f"  {'← H1-D1 PASS' if h1_d1 else '← H1-D1 FAIL/NULL'}")
        print(f"    D2 mean_h_capture_corr   = {cl_h_corr}"
              f"  {'← H1-D2 PASS' if h1_d2 else '← H1-D2 FAIL/NULL'}")
        print(f"    D1 mean_h_tag_ratio      = {cl_h_ratio}"
              f"  (>1.0 = tagged units have higher h)")

        for s in all_summaries:
            if s["seed_env"] != seed:
                continue
            s["closed_vs_exact_h_l1"] = round(cl_vs_ex_l1, 8)
            s["closed_vs_divergent_h_l1"] = round(cl_vs_dv_l1, 8)
            s["h1_threshold"] = round(h1_threshold, 8)
            s["h1_pass"] = h1_pass
            s["p5_pass"] = p5_pass
            s["p7_pass"] = p7_pass
            s["h1_d1_pass"] = h1_d1
            s["h1_d2_pass"] = h1_d2

    # ── Protocol verdict ──
    print()
    print("══ Protocol Checks ══")
    all_pass = True
    for seed in args.seeds:
        by_arm = {s["arm"]: s for s in all_summaries if s["seed_env"] == seed}
        cl = by_arm.get("closed_loop", {})
        ex = by_arm.get("exact_replay", {})
        dv = by_arm.get("divergent_warmup_replay", {})

        p1 = cl.get("n_replayed", 0) == cl.get("n_expected", -1)
        p2 = ex.get("n_replayed", 0) == ex.get("n_expected", -1)
        p3 = ex.get("hash_mismatches", 1) == 0
        p4 = cl.get("capture_count", 0) > 0
        p5 = bool(cl.get("p5_pass", False))
        p6 = dv.get("warmup_act_div", 0.0) > 1e-8
        p7 = bool(cl.get("p7_pass", False))
        h1 = bool(cl.get("h1_pass", False))
        h1d1 = bool(cl.get("h1_d1_pass", False))
        h1d2 = bool(cl.get("h1_d2_pass", False))

        ok = lambda v: "OK" if v else "FAIL"
        checks = [p1, p2, p3, p4, p5, p6, p7]
        seed_pass = all(checks)
        all_pass = all_pass and seed_pass

        verdict = "PASS" if seed_pass else "FAIL"
        print(f"  Seed {seed}: P1={ok(p1)} P2={ok(p2)} P3={ok(p3)}"
              f" P4={ok(p4)} P5={ok(p5)} P6={ok(p6)} P7={ok(p7)}"
              f" | H1={ok(h1)} D1={ok(h1d1)} D2={ok(h1d2)}"
              f" → {verdict}")

    print()
    print(f"Overall: {'ALL PASS' if all_pass else 'SOME FAIL'}")

    # ── Save outputs ──
    _save_csv(all_capture_rows, args.captures_csv)
    _save_csv(all_summaries, args.summary_csv)

    with open(args.summary_json, "w", encoding="utf-8") as fj:
        json.dump(all_summaries, fj, indent=2, default=str)

    print()
    print(f"captures  → {args.captures_csv}")
    print(f"summary   → {args.summary_csv}")
    print(f"summary   → {args.summary_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
