"""Phase 10D.2 — Historical Context Trace Smoke.

Tests whether h[u] (per-unit slow activation history, τ=10000) captures
warmup-history differences that event_trace and tag_cache cannot see.

Four-arm structure identical to 10A.2C / 10C.2.
h[u] is strictly read-only: does not affect gate, capture, or slow_weight.

Success criterion H1: closed_vs_divergent_h_l1 > 0.01 · h_l1_final
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


def _saturation_frac(core):
    if core._slow_weight_cache is None:
        return 0.0
    eff = core._weight_cache + core._slow_weight_cache
    np.clip(eff, -1.0, 1.0, out=eff)
    return float(np.mean(np.abs(eff) >= 0.999))


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


def _git_sha():
    import subprocess
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


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
    h_warmup_end = None

    for s in range(TOTAL_STEPS):
        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)
        if not nan_hit and np.any(np.isnan(core._activations)):
            nan_hit = True
        if s == WARMUP_END - 1:
            h_warmup_end = core._historical_context_trace.copy()
        if s in decision_points:
            act_l, act_r = _compute_region_activity(core)
            result = scheduler.propose(act_l, act_r)
            chosen = result["chosen"]
            row = {"run_id": f"phase10D2_closed_seed{seed_env}",
                   "arm": "closed_loop", "seed_env": seed_env,
                   "code_sha": code_sha, "config_sha": config_sha,
                   "t_decision": s, "chosen_event": chosen, "payload_hash": ""}
            if chosen != "none":
                phi = phi_cache[chosen]
                row["payload_hash"] = _hash_payload(phi)
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
    summary = {
        "arm": "closed_loop", "seed_env": seed_env, "event_count": n_ev,
        "L_count": sum(1 for d in event_log if d["chosen_event"] == "L"),
        "R_count": sum(1 for d in event_log if d["chosen_event"] == "R"),
        "simultaneous_count": sum(1 for d in event_log
                                  if d["chosen_event"] == "simultaneous"),
        "fast_weight_l1": round(_fast_weight_l1(core), 8),
        "slow_weight_l1": round(_slow_weight_l1(core), 8),
        "capture_count": len(ledger),
        "tag_mass_final": round(_tag_mass(core), 8),
        "n_tagged_connections": _n_tagged(core),
        "saturation_frac": round(_saturation_frac(core), 8),
        "max_abs_weight": round(float(np.max(np.abs(core._weight_cache))), 8)
            if len(core._weight_cache) > 0 else 0.0,
        "h_l1_final": round(float(np.sum(h_final)), 8),
        "h_mean_final": round(float(np.mean(h_final)), 8),
        "h_max_final": round(float(np.max(h_final)), 8),
        "nan_hit": nan_hit,
    }
    return event_log, summary, ledger, h_warmup_end, h_final


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
    h_warmup_end = None
    warmup_weight_delta = 0.0
    w0 = core._weight_cache.copy()

    for s in range(TOTAL_STEPS):
        if s == WARMUP_END:
            warmup_weight_delta = float(np.sum(np.abs(core._weight_cache - w0)))
            core._weight_cache[:] = w0
            for i, conn in enumerate(core.connections):
                conn.weight = float(w0[i])
            core.config.event_pair_plasticity_enabled = True
            core.config.consolidation_enabled = True
            if core._tag_cache is None:
                core._init_consolidation()
        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)
        if not nan_hit and np.any(np.isnan(core._activations)):
            nan_hit = True
        if s == WARMUP_END - 1:
            h_warmup_end = core._historical_context_trace.copy()
        while replay_idx < n_expected and event_trace[replay_idx][0] == s:
            t_dec, chosen, exp_hash = event_trace[replay_idx]
            phi = phi_cache[chosen]
            actual_hash = _hash_payload(phi)
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
            event_log.append({"run_id": f"phase10D2_exact_seed{seed_env}",
                               "arm": "exact_replay", "seed_env": seed_env,
                               "code_sha": code_sha, "config_sha": config_sha,
                               "t_decision": s, "chosen_event": chosen,
                               "payload_hash": actual_hash,
                               "expected_payload_hash": exp_hash,
                               "hash_match": actual_hash == exp_hash})
            replay_idx += 1

    h_final = core._historical_context_trace.copy()
    ledger = core._consolidation_ledger if core._consolidation_ledger else []
    summary = {
        "arm": "exact_replay", "seed_env": seed_env,
        "n_expected": n_expected, "n_replayed": replay_idx,
        "hash_mismatches": hash_mismatches,
        "warmup_weight_delta_l1": round(warmup_weight_delta, 8),
        "fast_weight_l1": round(_fast_weight_l1(core), 8),
        "slow_weight_l1": round(_slow_weight_l1(core), 8),
        "capture_count": len(ledger),
        "tag_mass_final": round(_tag_mass(core), 8),
        "n_tagged_connections": _n_tagged(core),
        "saturation_frac": round(_saturation_frac(core), 8),
        "max_abs_weight": round(float(np.max(np.abs(core._weight_cache))), 8)
            if len(core._weight_cache) > 0 else 0.0,
        "h_l1_final": round(float(np.sum(h_final)), 8),
        "h_mean_final": round(float(np.mean(h_final)), 8),
        "h_max_final": round(float(np.max(h_final)), 8),
        "nan_hit": nan_hit,
    }
    return event_log, summary, ledger, h_warmup_end, h_final


# ═══════════════════════════════════════════════════════════════════
# Arm 3: divergent_warmup_replay
# ═══════════════════════════════════════════════════════════════════

def run_divergent_warmup_replay(seed_env, event_trace, pulse_dur, code_sha):
    """Primary test arm. h[u] accumulates divergent warmup history,
    then is carried into the replay core."""
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
    w0_div = core_div._weight_cache.copy()
    for s in range(WARMUP_END):
        influences = env_div.compute_influences(core_div.units, s)
        core_div.step(env_influences=influences if influences else None)

    core_div._weight_cache[:] = w0_div
    for i, conn in enumerate(core_div.connections):
        conn.weight = float(w0_div[i])
    warmup_weight_delta = float(np.sum(np.abs(core_div._weight_cache - w0_div)))
    h_warmup_end = core_div._historical_context_trace.copy()

    div_state = {
        "activations": core_div._activations.copy(),
        "energies": core_div._energies.copy(),
        "traces": core_div._traces.copy(),
        "event_trace": core_div._event_trace.copy(),
        "weight_cache": core_div._weight_cache.copy(),
        "h_trace": core_div._historical_context_trace.copy(),
    }

    # Run ref warmup for activation divergence comparison
    env_ref = Environment()
    w0_ref = core_ref._weight_cache.copy()
    for s in range(WARMUP_END):
        influences = env_ref.compute_influences(core_ref.units, s)
        core_ref.step(env_influences=influences if influences else None)
    core_ref._weight_cache[:] = w0_ref
    for i, conn in enumerate(core_ref.connections):
        conn.weight = float(w0_ref[i])
    warmup_act_div = _activation_divergence(core_div._activations, core_ref._activations)
    warmup_energy_div = abs(float(np.mean(core_div._energies)) -
                            float(np.mean(core_ref._energies)))

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

    for s in range(WARMUP_END, TOTAL_STEPS):
        influences = env_replay.compute_influences(core_replay.units, s)
        core_replay.step(env_influences=influences if influences else None)
        if not nan_hit and np.any(np.isnan(core_replay._activations)):
            nan_hit = True
        while replay_idx < n_expected and event_trace[replay_idx][0] == s:
            t_dec, chosen, exp_hash = event_trace[replay_idx]
            phi = phi_cache_replay[chosen]
            actual_hash = _hash_payload(phi)
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
            event_log.append({"run_id": f"phase10D2_divergent_seed{seed_env}",
                               "arm": "divergent_warmup_replay",
                               "seed_env": seed_env, "code_sha": code_sha,
                               "t_decision": s, "chosen_event": chosen,
                               "payload_hash": actual_hash,
                               "expected_payload_hash": exp_hash,
                               "hash_match": actual_hash == exp_hash})
            replay_idx += 1

    h_final = core_replay._historical_context_trace.copy()
    ledger = core_replay._consolidation_ledger if core_replay._consolidation_ledger else []
    summary = {
        "arm": "divergent_warmup_replay", "seed_env": seed_env,
        "n_expected": n_expected, "n_replayed": replay_idx,
        "hash_mismatches": hash_mismatches,
        "warmup_act_div": round(warmup_act_div, 8),
        "warmup_energy_div": round(warmup_energy_div, 8),
        "warmup_weight_delta_l1": round(warmup_weight_delta, 8),
        "fast_weight_l1": round(_fast_weight_l1(core_replay), 8),
        "slow_weight_l1": round(_slow_weight_l1(core_replay), 8),
        "capture_count": len(ledger),
        "tag_mass_final": round(_tag_mass(core_replay), 8),
        "n_tagged_connections": _n_tagged(core_replay),
        "saturation_frac": round(_saturation_frac(core_replay), 8),
        "max_abs_weight": round(float(np.max(np.abs(core_replay._weight_cache))), 8)
            if len(core_replay._weight_cache) > 0 else 0.0,
        "h_l1_final": round(float(np.sum(h_final)), 8),
        "h_mean_final": round(float(np.mean(h_final)), 8),
        "h_max_final": round(float(np.max(h_final)), 8),
        "nan_hit": nan_hit,
    }
    return event_log, summary, ledger, h_warmup_end, h_final


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
    w0_div = core_div._weight_cache.copy()
    for s in range(WARMUP_END):
        influences = env_div.compute_influences(core_div.units, s)
        core_div.step(env_influences=influences if influences else None)
    core_div._weight_cache[:] = w0_div
    for i, conn in enumerate(core_div.connections):
        conn.weight = float(w0_div[i])
    warmup_weight_delta = float(np.sum(np.abs(core_div._weight_cache - w0_div)))
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
    for s in range(WARMUP_END, TOTAL_STEPS):
        influences = env_replay.compute_influences(core_replay.units, s)
        core_replay.step(env_influences=influences if influences else None)
        if not nan_hit and np.any(np.isnan(core_replay._activations)):
            nan_hit = True

    h_final = core_replay._historical_context_trace.copy()
    ledger = core_replay._consolidation_ledger if core_replay._consolidation_ledger else []
    summary = {
        "arm": "matched_warmup_control", "seed_env": seed_env,
        "warmup_act_div": round(warmup_act_div, 8),
        "warmup_weight_delta_l1": round(warmup_weight_delta, 8),
        "fast_weight_l1": round(_fast_weight_l1(core_replay), 8),
        "slow_weight_l1": round(_slow_weight_l1(core_replay), 8),
        "capture_count": len(ledger),
        "tag_mass_final": round(_tag_mass(core_replay), 8),
        "n_tagged_connections": _n_tagged(core_replay),
        "saturation_frac": round(_saturation_frac(core_replay), 8),
        "max_abs_weight": round(float(np.max(np.abs(core_replay._weight_cache))), 8)
            if len(core_replay._weight_cache) > 0 else 0.0,
        "h_l1_final": round(float(np.sum(h_final)), 8),
        "h_mean_final": round(float(np.mean(h_final)), 8),
        "h_max_final": round(float(np.max(h_final)), 8),
        "nan_hit": nan_hit,
    }
    return [], summary, ledger, h_warmup_end, h_final


# ═══════════════════════════════════════════════════════════════════
# Output helpers
# ═══════════════════════════════════════════════════════════════════

def _extract_capture_rows(seed, arm, ledger):
    rows = []
    for idx, entry in enumerate(ledger):
        row = {
            "seed": seed, "arm": arm,
            "capture_index": idx,
            "capture_step": entry.get("capture_step", ""),
            "capture_signal": entry.get("capture_signal", ""),
            "slow_weight_delta_l1": entry.get("slow_weight_delta_l1", ""),
            "capture_count_so_far": idx + 1,
            "historical_context_l1": entry.get("historical_context_l1", ""),
            "historical_context_mean": entry.get("historical_context_mean", ""),
            "historical_context_max": entry.get("historical_context_max", ""),
            "historical_context_concentration": entry.get(
                "historical_context_concentration", ""),
            "historical_context_effective_support": entry.get(
                "historical_context_effective_support", ""),
        }
        rows.append(row)
    return rows


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
        description="Phase 10D.2 — Historical Context Trace Smoke")
    p.add_argument("--seeds", type=int, nargs="+", default=[42, 77])
    p.add_argument("--estimate-only", action="store_true")
    p.add_argument("--dry-run-schedule", action="store_true")
    p.add_argument("--summary-csv", type=str,
                   default="results/phase10D2_historical_context_trace_summary.csv")
    p.add_argument("--events-csv", type=str,
                   default="results/phase10D2_historical_context_trace_events.csv")
    p.add_argument("--captures-csv", type=str,
                   default="results/phase10D2_hctrace_captures.csv")
    p.add_argument("--summary-json", type=str,
                   default="results/phase10D2_historical_context_trace_summary.json")
    args = p.parse_args(argv)

    decision_points = set(range(WARMUP_END, TOTAL_STEPS, DECISION_INTERVAL))
    n_decisions = len(decision_points)

    print("Phase 10D.2 — Historical Context Trace Smoke")
    print(f"  seeds={args.seeds}  unit_count=300  steps={TOTAL_STEPS}"
          f"  warmup={WARMUP_END}")
    print(f"  decision_points={n_decisions}  interval={DECISION_INTERVAL}")
    print(f"  scheduler θ: w={W} b_none={B_NONE} b_L={B_L} b_R={B_R}"
          f"  b_sim={B_SIM} tau={TAU}")
    print(f"  divergent noise offset: +{DIVERGENT_NOISE_OFFSET}")
    print(f"  historical_context_tau={HISTORICAL_CONTEXT_TAU}  clip=True")
    print(f"  h[u] starts at t=0 (includes warmup)")
    print(f"  h[u] does NOT affect gate / capture / slow_weight")
    print()

    if args.dry_run_schedule:
        dp_list = sorted(decision_points)
        print(f"  Arms: closed_loop, exact_replay,"
              f" divergent_warmup_replay, matched_warmup_control")
        print(f"  Decision points (first 5): {dp_list[:5]}...")
        print(f"  Decision points (last 5): ...{dp_list[-5:]}")
        print(f"  Warmup: 0–{WARMUP_END-1} (2000 steps), plasticity OFF")
        print(f"  Replay: {WARMUP_END}–{TOTAL_STEPS-1} (5500 steps), 9C+9D ON")
        print(f"  h[u] carried from warmup into replay core (arm 3 & 4)")
        print(f"  Estimated per seed: ~5-7 min")
        print(f"  Total: ~10-14 min for 2 seeds  ← ECS recommended")
        print()
        return 0

    code_sha = _git_sha()
    all_event_rows = []
    all_summaries = []
    all_capture_rows = []

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
            el, s_info, _, _, _ = run_closed_loop(
                cfg, seed_env=seed, seed_sched=seed + 1000,
                decision_points=decision_points, pulse_dur=PULSE_DURATION,
                code_sha=code_sha, config_sha=config_sha)
            wall = time.time() - t0
            n_events = s_info["event_count"]
            print(f"{wall:.0f}s  events={n_events}")
            est_div = wall * 2.5
            est_matched = wall * 2.2
            per_seed = wall * 1.0 + wall * 1.0 + est_div + est_matched
            print(f"    Estimated per seed: ~{per_seed:.0f}s"
                  f"  (closed: {wall:.0f}s, exact: ~{wall:.0f}s,"
                  f" divergent: ~{est_div:.0f}s, matched: ~{est_matched:.0f}s)")
        total = per_seed * len(args.seeds)
        print(f"\n  Total estimate: ~{total:.0f}s = ~{total/60:.1f} min")
        if total > 900:
            print(f"  ← ECS recommended (>15 min)")
        else:
            print(f"  ← OK for local")
        return 0

    # ── Full run ──
    h_snapshots = {}  # {(seed, arm): (h_warmup_end, h_final)}

    for seed in args.seeds:
        print(f"══ Seed {seed} ══")
        cfg_9c_9d = _make_cfg(seed, event_pair_on=True, consolidation_on=True)
        config_sha = hashlib.sha256(
            json.dumps({k: v for k, v in cfg_9c_9d.__dict__.items()
                        if not k.startswith("_")},
                       sort_keys=True, default=str).encode()
        ).hexdigest()[:16]

        # ── Arm 1: closed_loop ──
        print(f"  [1/4] closed_loop ...", end=" ", flush=True)
        t0 = time.time()
        el_cl, s_cl, led_cl, h_wu_cl, h_fin_cl = run_closed_loop(
            cfg_9c_9d, seed_env=seed, seed_sched=seed + 1000,
            decision_points=decision_points, pulse_dur=PULSE_DURATION,
            code_sha=code_sha, config_sha=config_sha)
        wall = time.time() - t0
        h_snapshots[(seed, "closed_loop")] = (h_wu_cl, h_fin_cl)

        event_trace = [(d["t_decision"], d["chosen_event"], d["payload_hash"])
                       for d in el_cl if d["chosen_event"] != "none"]
        trace_hash = _hash_trace(event_trace)
        s_cl.update({"trace_hash": trace_hash, "wall_time_s": round(wall, 1)})
        all_event_rows.extend(el_cl)
        all_summaries.append(s_cl)
        all_capture_rows.extend(_extract_capture_rows(seed, "closed_loop", led_cl))

        print(f"{wall:.0f}s  events={s_cl['event_count']}"
              f"  L={s_cl['L_count']} R={s_cl['R_count']}"
              f"  sim={s_cl['simultaneous_count']}"
              f"  captures={s_cl['capture_count']}"
              f"  slow_l1={s_cl['slow_weight_l1']:.6f}"
              f"  h_l1={s_cl['h_l1_final']:.4f}")

        # ── Arm 2: exact_replay ──
        print(f"  [2/4] exact_replay ...", end=" ", flush=True)
        t0 = time.time()
        cfg_exact = _make_cfg(seed, event_pair_on=True, consolidation_on=True)
        el_ex, s_ex, led_ex, h_wu_ex, h_fin_ex = run_exact_replay(
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
        all_capture_rows.extend(_extract_capture_rows(seed, "exact_replay", led_ex))

        status = "EXACT" if replay_exact else "MISMATCH"
        print(f"{wall:.0f}s  replayed={s_ex['n_replayed']}"
              f"  captures={s_ex['capture_count']}"
              f"  slow_l1={s_ex['slow_weight_l1']:.6f}"
              f"  h_l1={s_ex['h_l1_final']:.4f}"
              f"  w_delta={s_ex['warmup_weight_delta_l1']:.6f}"
              f"  [{status}]")

        # ── Arm 3: divergent_warmup_replay ──
        print(f"  [3/4] divergent_warmup_replay ...", end=" ", flush=True)
        t0 = time.time()
        el_dv, s_dv, led_dv, h_wu_dv, h_fin_dv = run_divergent_warmup_replay(
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
        all_capture_rows.extend(_extract_capture_rows(seed, "divergent_warmup_replay",
                                                      led_dv))

        p6_ok = s_dv.get("warmup_act_div", 0.0) > 1e-8
        print(f"{wall:.0f}s  replayed={s_dv['n_replayed']}"
              f"  captures={s_dv['capture_count']}"
              f"  slow_l1={s_dv['slow_weight_l1']:.6f}"
              f"  h_l1={s_dv['h_l1_final']:.4f}"
              f"  act_div={s_dv.get('warmup_act_div', 0):.6f}"
              f"  [P6={'OK' if p6_ok else 'FAIL'}]")

        # ── Arm 4: matched_warmup_control ──
        print(f"  [4/4] matched_warmup_control ...", end=" ", flush=True)
        t0 = time.time()
        _, s_mc, led_mc, h_wu_mc, h_fin_mc = run_matched_warmup_control(
            seed_env=seed, pulse_dur=PULSE_DURATION, code_sha=code_sha)
        wall = time.time() - t0
        h_snapshots[(seed, "matched_warmup_control")] = (h_wu_mc, h_fin_mc)

        s_mc["wall_time_s"] = round(wall, 1)
        all_summaries.append(s_mc)
        all_capture_rows.extend(_extract_capture_rows(seed, "matched_warmup_control",
                                                      led_mc))

        print(f"{wall:.0f}s  captures={s_mc['capture_count']}"
              f"  slow_l1={s_mc['slow_weight_l1']:.6f}"
              f"  h_l1={s_mc['h_l1_final']:.4f}"
              f"  w_delta={s_mc['warmup_weight_delta_l1']:.6f}")

    # ── Cross-arm h comparison ──
    print()
    print("══ Historical Context Trace Comparison ══")
    for seed in args.seeds:
        h_wu_cl, h_fin_cl = h_snapshots.get((seed, "closed_loop"), (None, None))
        h_wu_ex, h_fin_ex = h_snapshots.get((seed, "exact_replay"), (None, None))
        h_wu_dv, h_fin_dv = h_snapshots.get((seed, "divergent_warmup_replay"),
                                             (None, None))
        h_wu_mc, h_fin_mc = h_snapshots.get((seed, "matched_warmup_control"),
                                             (None, None))

        if h_fin_cl is None:
            continue

        h_div_warmup = (float(np.mean(np.abs(h_wu_dv - h_wu_cl)))
                        if h_wu_dv is not None and h_wu_cl is not None else float("nan"))
        h_div_final = (float(np.mean(np.abs(h_fin_dv - h_fin_cl)))
                       if h_fin_dv is not None else float("nan"))
        cl_vs_ex_l1 = (float(np.sum(np.abs(h_fin_cl - h_fin_ex)))
                       if h_fin_ex is not None else float("nan"))
        cl_vs_dv_l1 = (float(np.sum(np.abs(h_fin_cl - h_fin_dv)))
                       if h_fin_dv is not None else float("nan"))
        dv_vs_mc_l1 = (float(np.sum(np.abs(h_fin_dv - h_fin_mc)))
                       if h_fin_dv is not None and h_fin_mc is not None
                       else float("nan"))

        h_l1_ref = float(np.sum(h_fin_cl))
        h1_threshold = 0.01 * h_l1_ref
        h1_pass = cl_vs_dv_l1 > h1_threshold if not np.isnan(cl_vs_dv_l1) else False

        print(f"  Seed {seed}:")
        print(f"    h_l1_final:  closed={h_l1_ref:.6f}"
              f"  exact={float(np.sum(h_fin_ex)) if h_fin_ex is not None else 'N/A':.6f}"
              f"  divergent={float(np.sum(h_fin_dv)) if h_fin_dv is not None else 'N/A':.6f}"
              f"  matched_ctrl={float(np.sum(h_fin_mc)) if h_fin_mc is not None else 'N/A':.6f}")
        print(f"    h_divergence_at_warmup_end  = {h_div_warmup:.8f}")
        print(f"    h_divergence_at_final       = {h_div_final:.8f}")
        print(f"    closed_vs_exact_h_l1        = {cl_vs_ex_l1:.8f}"
              f"  {'← P5 OK' if cl_vs_ex_l1 < 1e-6 else '← P5 FAIL (protocol bug)'}")
        print(f"    closed_vs_divergent_h_l1    = {cl_vs_dv_l1:.8f}"
              f"  (H1 threshold={h1_threshold:.6f})"
              f"  {'← H1 PASS' if h1_pass else '← H1 FAIL'}")
        print(f"    divergent_vs_matched_h_l1   = {dv_vs_mc_l1:.8f}"
              f"  (event effect on h)")

        # Store cross-arm metrics in summaries
        for s in all_summaries:
            if s["seed_env"] != seed:
                continue
            arm = s["arm"]
            s["h_divergence_at_warmup_end"] = round(h_div_warmup, 8)
            s["h_divergence_at_final"] = round(h_div_final, 8)
            s["closed_vs_exact_h_l1"] = round(cl_vs_ex_l1, 8)
            s["closed_vs_divergent_h_l1"] = round(cl_vs_dv_l1, 8)
            s["divergent_vs_matched_ctrl_h_l1"] = round(dv_vs_mc_l1, 8)
            s["h1_threshold"] = round(h1_threshold, 8)
            s["h1_pass"] = h1_pass

    # ── Protocol checks ──
    print()
    print("══ Protocol Checks ══")
    n_hard_ok = 0
    for seed in args.seeds:
        seed_sums = [s for s in all_summaries if s["seed_env"] == seed]
        by_arm = {s["arm"]: s for s in seed_sums}

        p1 = not any(s.get("nan_hit", False) for s in seed_sums)
        p2 = all(s.get("max_abs_weight", 0.0) < 10.0 for s in seed_sums)
        p3 = all(s.get("hash_mismatches", 0) == 0 for s in seed_sums
                 if s["arm"] not in ("closed_loop", "matched_warmup_control"))

        cl_ev = by_arm.get("closed_loop", {}).get("event_count", -1)
        ex_ev = by_arm.get("exact_replay", {}).get("n_replayed", -1)
        dv_ev = by_arm.get("divergent_warmup_replay", {}).get("n_replayed", -1)
        p4 = (cl_ev == ex_ev == dv_ev) and cl_ev >= 0

        cl_vs_ex = by_arm.get("closed_loop", {}).get("closed_vs_exact_h_l1",
                                                      float("nan"))
        p5 = cl_vs_ex < 1e-6 if not np.isnan(cl_vs_ex) else False

        p6 = by_arm.get("divergent_warmup_replay", {}).get("warmup_act_div", 0.0) > 1e-8

        ex_wd = by_arm.get("exact_replay", {}).get("warmup_weight_delta_l1",
                                                    float("nan"))
        dv_wd = by_arm.get("divergent_warmup_replay", {}).get("warmup_weight_delta_l1",
                                                               float("nan"))
        p7 = (ex_wd < 1e-6 and dv_wd < 1e-6)

        h1_pass = by_arm.get("closed_loop", {}).get("h1_pass", False)

        seed_ok = p1 and p2 and p3 and p4 and p5 and p6 and p7
        if seed_ok:
            n_hard_ok += 1

        checks = [f"P{i+1}={'OK' if v else 'FAIL'}"
                  for i, v in enumerate([p1, p2, p3, p4, p5, p6, p7])]
        h1_str = f"H1={'PASS' if h1_pass else 'FAIL'}"
        print(f"  Seed {seed}: {'  '.join(checks)}  {h1_str}"
              f"  → {'PASS' if seed_ok else 'FAIL'}")

        if not p6:
            print(f"    ⚠ P6 FAIL: warmup divergence absent."
                  f" act_div={by_arm.get('divergent_warmup_replay', {}).get('warmup_act_div', 0)}")
        if not p7:
            print(f"    ⚠ P7 FAIL: weights changed during warmup."
                  f" ex_wd={ex_wd}  dv_wd={dv_wd}")
        if not h1_pass:
            cl_vs_dv = by_arm.get("closed_loop", {}).get("closed_vs_divergent_h_l1", 0)
            h1_thr = by_arm.get("closed_loop", {}).get("h1_threshold", 0)
            print(f"    ⚠ H1 FAIL: h does not capture warmup history."
                  f" cl_vs_dv={cl_vs_dv:.8f}  threshold={h1_thr:.6f}")

        # Verdict
        if seed_ok and h1_pass:
            verdict = "TARGET_OUTCOME: h stores warmup history; capture still blind"
        elif seed_ok and not h1_pass:
            verdict = "H1_FAIL: h too weak; adjust tau or signal before 10D.3"
        else:
            verdict = "PROTOCOL_FAIL: check P-checks above"
        print(f"    Verdict: {verdict}")

        for s in all_summaries:
            if s["seed_env"] == seed:
                s["hard_pass"] = seed_ok
                s["verdict"] = verdict

    print(f"\n  Hard pass: {n_hard_ok}/{len(args.seeds)}")
    print()

    # ── Save outputs ──
    if args.events_csv and all_event_rows:
        _save_csv(all_event_rows, args.events_csv)
        print(f"  Events CSV: {args.events_csv} ({len(all_event_rows)} rows)")

    if args.captures_csv and all_capture_rows:
        _save_csv(all_capture_rows, args.captures_csv)
        print(f"  Captures CSV: {args.captures_csv} ({len(all_capture_rows)} rows)")

    if args.summary_csv and all_summaries:
        all_sf, seen_sf = [], set()
        for s in all_summaries:
            for k in s:
                if k not in seen_sf and not isinstance(s[k], (np.ndarray, list, dict)):
                    all_sf.append(k)
                    seen_sf.add(k)
        with open(args.summary_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=all_sf, extrasaction="ignore")
            w.writeheader()
            w.writerows(all_summaries)
        print(f"  Summary CSV: {args.summary_csv}")

    if args.summary_json:
        json_sums = []
        for s in all_summaries:
            js = {}
            for k, v in s.items():
                if isinstance(v, (np.ndarray, list)):
                    js[k] = str(v)
                elif isinstance(v, (np.floating, np.integer)):
                    js[k] = float(v)
                else:
                    js[k] = v
            json_sums.append(js)
        with open(args.summary_json, "w", encoding="utf-8") as f:
            json.dump({
                "experiment": "phase10D2_historical_context_trace_smoke",
                "frozen_params": {
                    "w": W, "b_none": B_NONE, "b_L": B_L, "b_R": B_R,
                    "b_sim": B_SIM, "tau": TAU,
                    "total_steps": TOTAL_STEPS, "warmup_end": WARMUP_END,
                    "decision_interval": DECISION_INTERVAL,
                    "pulse_duration": PULSE_DURATION,
                    "divergent_noise_offset": DIVERGENT_NOISE_OFFSET,
                    "historical_context_tau": HISTORICAL_CONTEXT_TAU,
                    "historical_context_clip": True,
                    "h_starts_at": "t=0 (includes warmup)",
                    "h_affects_gate": False,
                    "warmup_plasticity": "OFF (snapshot/restore)",
                    "9C_enabled": True, "9D_enabled": True,
                },
                "summaries": json_sums,
                "n_hard_pass": n_hard_ok,
                "n_seeds": len(args.seeds),
            }, f, indent=2, ensure_ascii=False)
        print(f"  JSON: {args.summary_json}")

    if n_hard_ok != len(args.seeds):
        print("\n  ⚠ Some seeds FAILED hard protocol."
              " Check P-checks before interpreting H1.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
