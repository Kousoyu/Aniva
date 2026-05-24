"""Phase 10C.2 — Capture Diagnostics Smoke.

Reuses the 10A.2C four-arm structure with consolidation_diagnostics_enabled=True.
Outputs per-capture diagnostic metrics to reveal context differences invisible
to the gate (which only sees scalar signal).

Gate logic, capture signal, and slow_weight transfer are UNCHANGED.
Baseline slow_l1 must match 10A.2C: seed42≈0.00039344, seed77≈0.00044013.
"""

import argparse, csv, hashlib, json, sys, time
import numpy as np

from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.environment.environment import Stimulus, StimulusEvent, Environment

# ── Frozen from 10A.0 / 10A.1B ──
L_STIM = Stimulus(position=(-0.5, 0.0, 0.0), intensity=0.02, radius=0.5)
R_STIM = Stimulus(position=(0.5, 0.0, 0.0), intensity=0.02, radius=0.5)
STIM_MAP = {"L": L_STIM, "R": R_STIM}

TOTAL_STEPS = 7500
WARMUP_END = 2000
DECISION_INTERVAL = 250
PULSE_DURATION = 80

# Scheduler θ (FROZEN)
W = 5.0
B_NONE = +1.0
B_L = -1.5
B_R = -1.5
B_SIM = -3.0
TAU = 1.0

# Divergent warmup (FROZEN)
DIVERGENT_NOISE_OFFSET = 5000

EVENT_SET = ["none", "L", "R", "simultaneous"]

# Baseline slow_l1 from 10A.2C (gate-invariance check)
BASELINE_SLOW_L1 = {42: 0.00039344, 77: 0.00044013}
BASELINE_TOL = 1e-6

DIAG_FIELDS = [
    "tag_trace_alignment",
    "tag_weighted_energy",
    "tag_concentration",
    "tag_effective_support",
    "trace_concentration",
    "trace_effective_support",
]

CAPTURE_CSV_FIELDS = [
    "seed", "arm", "capture_index", "capture_step",
    "capture_signal", "mean_energy", "trace_mass_at_capture",
    "tag_mass", "n_tagged_connections", "slow_weight_delta_l1",
] + DIAG_FIELDS


def _unit_region(pos):
    x = pos[0]
    if x < -0.1: return "L"
    elif x > 0.1: return "R"
    return "M"


def _hash_obs(act_l, act_r):
    return hashlib.sha256(f"{act_l:.6f},{act_r:.6f}".encode()).hexdigest()[:16]


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
    def __init__(self, rng: np.random.Generator):
        self._rng = rng

    def propose(self, activity_L: float, activity_R: float):
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
        return {
            "logits": {"none": float(logit_none), "L": float(logit_L),
                       "R": float(logit_R), "simultaneous": float(logit_sim)},
            "probs": {"none": float(probs[0]), "L": float(probs[1]),
                      "R": float(probs[2]), "simultaneous": float(probs[3])},
            "u_draw": u,
            "chosen": EVENT_SET[chosen_idx],
        }


def _build_phi_cache(core):
    n_units = core.unit_count
    phi_l = np.array([L_STIM.influence_at(tuple(core._positions[uid]))
                      for uid in range(n_units)], dtype=np.float64)
    phi_r = np.array([R_STIM.influence_at(tuple(core._positions[uid]))
                      for uid in range(n_units)], dtype=np.float64)
    phi_sim = phi_l + phi_r
    return {"L": phi_l, "R": phi_r, "simultaneous": phi_sim}


def _git_sha():
    import subprocess
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


def _make_cfg(seed, event_pair_on=True, consolidation_on=True):
    return AnivaConfig(
        unit_count=300,
        seed=seed,
        event_pair_plasticity_enabled=event_pair_on,
        event_pair_ledger_enabled=event_pair_on,
        consolidation_enabled=consolidation_on,
        consolidation_ledger_enabled=consolidation_on,
        consolidation_diagnostics_enabled=consolidation_on,  # 10C.1
    )


def _extract_capture_rows(seed, arm, ledger):
    """Build per-capture CSV rows from a consolidation ledger."""
    rows = []
    for idx, entry in enumerate(ledger):
        row = {
            "seed": seed,
            "arm": arm,
            "capture_index": idx,
            "capture_step": entry.get("capture_step", ""),
            "capture_signal": entry.get("capture_signal", ""),
            "mean_energy": entry.get("mean_energy", ""),
            "trace_mass_at_capture": entry.get("trace_mass_at_capture", ""),
            "tag_mass": entry.get("tag_mass", ""),
            "n_tagged_connections": entry.get("n_tagged_connections", ""),
            "slow_weight_delta_l1": entry.get("slow_weight_delta_l1", ""),
        }
        for f in DIAG_FIELDS:
            row[f] = entry.get(f, 0.0)
        rows.append(row)
    return rows


def _arm_diag_stats(ledger):
    """Compute mean/std/min/max for each diagnostic field across all captures."""
    stats = {}
    for f in DIAG_FIELDS:
        vals = [e.get(f, 0.0) for e in ledger]
        if vals:
            arr = np.array(vals, dtype=np.float64)
            stats[f"{f}_mean"] = float(np.mean(arr))
            stats[f"{f}_std"] = float(np.std(arr))
            stats[f"{f}_min"] = float(np.min(arr))
            stats[f"{f}_max"] = float(np.max(arr))
        else:
            for suffix in ("mean", "std", "min", "max"):
                stats[f"{f}_{suffix}"] = float("nan")
    return stats


# ═══════════════════════════════════════════════════════════════════
# Arm runners — identical to 10A.2C except _make_cfg adds diagnostics
# and each runner returns (event_log, summary, ledger)
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

    for s in range(TOTAL_STEPS):
        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)
        if not nan_hit and np.any(np.isnan(core._activations)):
            nan_hit = True
        if s in decision_points:
            act_l, act_r = _compute_region_activity(core)
            result = scheduler.propose(act_l, act_r)
            chosen = result["chosen"]
            row = {
                "run_id": f"phase10C2_closed_seed{seed_env}",
                "arm": "closed_loop", "seed_env": seed_env,
                "code_sha": code_sha, "config_sha": config_sha,
                "t_decision": s, "chosen_event": chosen, "payload_hash": "",
            }
            if chosen != "none":
                phi = phi_cache[chosen]
                row["payload_hash"] = _hash_payload(phi)
                stim = STIM_MAP.get(chosen)
                if stim is None:
                    env.add_event(StimulusEvent(stimulus=L_STIM, start_step=s, duration_steps=pulse_dur))
                    env.add_event(StimulusEvent(stimulus=R_STIM, start_step=s, duration_steps=pulse_dur))
                else:
                    env.add_event(StimulusEvent(stimulus=stim, start_step=s, duration_steps=pulse_dur))
                core.apply_event_pair_phi(phi)
            event_log.append(row)

    captures = core._consolidation_ledger if core._consolidation_ledger else []
    summary = {
        "arm": "closed_loop", "seed_env": seed_env,
        "fast_weight_l1": round(_fast_weight_l1(core), 8),
        "slow_weight_l1": round(_slow_weight_l1(core), 8),
        "capture_count": len(captures),
        "tag_mass_final": round(_tag_mass(core), 8),
        "n_tagged_connections": _n_tagged(core),
        "saturation_frac": round(_saturation_frac(core), 8),
        "max_abs_weight": round(float(np.max(np.abs(core._weight_cache))), 8)
            if len(core._weight_cache) > 0 else 0.0,
        "nan_hit": nan_hit,
    }
    return event_log, summary, captures


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
    w0 = core._weight_cache.copy()
    warmup_weight_delta = 0.0

    for s in range(TOTAL_STEPS):
        if s == WARMUP_END:
            core._weight_cache[:] = w0
            for i, conn in enumerate(core.connections):
                conn.weight = float(w0[i])
            warmup_weight_delta = float(np.sum(np.abs(core._weight_cache - w0)))
            core.config.event_pair_plasticity_enabled = True
            core.config.consolidation_enabled = True
            if core._tag_cache is None:
                core._init_consolidation()
        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)
        if not nan_hit and np.any(np.isnan(core._activations)):
            nan_hit = True
        while replay_idx < n_expected and event_trace[replay_idx][0] == s:
            t_dec, chosen, exp_hash = event_trace[replay_idx]
            phi = phi_cache[chosen]
            actual_hash = _hash_payload(phi)
            if actual_hash != exp_hash:
                hash_mismatches += 1
            stim = STIM_MAP.get(chosen)
            if stim is None:
                env.add_event(StimulusEvent(stimulus=L_STIM, start_step=s, duration_steps=pulse_dur))
                env.add_event(StimulusEvent(stimulus=R_STIM, start_step=s, duration_steps=pulse_dur))
            else:
                env.add_event(StimulusEvent(stimulus=stim, start_step=s, duration_steps=pulse_dur))
            core.apply_event_pair_phi(phi)
            event_log.append({
                "run_id": f"phase10C2_exact_seed{seed_env}",
                "arm": "exact_replay", "seed_env": seed_env,
                "code_sha": code_sha, "config_sha": config_sha,
                "t_decision": s, "chosen_event": chosen,
                "payload_hash": actual_hash, "expected_payload_hash": exp_hash,
                "hash_match": actual_hash == exp_hash,
            })
            replay_idx += 1

    captures = core._consolidation_ledger if core._consolidation_ledger else []
    summary = {
        "arm": "exact_replay", "seed_env": seed_env,
        "n_expected": n_expected, "n_replayed": replay_idx,
        "hash_mismatches": hash_mismatches,
        "warmup_weight_delta_l1": round(warmup_weight_delta, 8),
        "fast_weight_l1": round(_fast_weight_l1(core), 8),
        "slow_weight_l1": round(_slow_weight_l1(core), 8),
        "capture_count": len(captures),
        "tag_mass_final": round(_tag_mass(core), 8),
        "n_tagged_connections": _n_tagged(core),
        "saturation_frac": round(_saturation_frac(core), 8),
        "max_abs_weight": round(float(np.max(np.abs(core._weight_cache))), 8)
            if len(core._weight_cache) > 0 else 0.0,
        "nan_hit": nan_hit,
    }
    return event_log, summary, captures


def run_divergent_warmup_replay(seed_env, event_trace, pulse_dur, code_sha):
    cfg_ref = AnivaConfig(unit_count=300, seed=seed_env,
                          event_pair_plasticity_enabled=False,
                          consolidation_enabled=False)
    core_ref = LifeCore(cfg_ref)
    ref_snap = _snapshot_core_state(core_ref)

    cfg_div = AnivaConfig(unit_count=300, seed=seed_env + DIVERGENT_NOISE_OFFSET,
                          event_pair_plasticity_enabled=False,
                          consolidation_enabled=False)
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

    env_ref = Environment()
    w0_ref = core_ref._weight_cache.copy()
    for s in range(WARMUP_END):
        influences = env_ref.compute_influences(core_ref.units, s)
        core_ref.step(env_influences=influences if influences else None)
    core_ref._weight_cache[:] = w0_ref
    for i, conn in enumerate(core_ref.connections):
        conn.weight = float(w0_ref[i])

    warmup_act_div = _activation_divergence(core_div._activations, core_ref._activations)
    warmup_energy_div = abs(float(np.mean(core_div._energies)) - float(np.mean(core_ref._energies)))

    div_state = {
        "activations": core_div._activations.copy(),
        "energies": core_div._energies.copy(),
        "traces": core_div._traces.copy(),
        "event_trace": core_div._event_trace.copy(),
        "weight_cache": core_div._weight_cache.copy(),
    }

    cfg_replay = _make_cfg(seed_env, event_pair_on=True, consolidation_on=True)
    core_replay = LifeCore(cfg_replay)
    core_replay._activations[:] = div_state["activations"]
    core_replay._energies[:] = div_state["energies"]
    core_replay._traces[:] = div_state["traces"]
    core_replay._event_trace[:] = div_state["event_trace"]
    core_replay._weight_cache[:] = div_state["weight_cache"]
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
                env_replay.add_event(StimulusEvent(stimulus=L_STIM, start_step=s, duration_steps=pulse_dur))
                env_replay.add_event(StimulusEvent(stimulus=R_STIM, start_step=s, duration_steps=pulse_dur))
            else:
                env_replay.add_event(StimulusEvent(stimulus=stim, start_step=s, duration_steps=pulse_dur))
            core_replay.apply_event_pair_phi(phi)
            event_log.append({
                "run_id": f"phase10C2_divergent_seed{seed_env}",
                "arm": "divergent_warmup_replay", "seed_env": seed_env,
                "code_sha": code_sha,
                "t_decision": s, "chosen_event": chosen,
                "payload_hash": actual_hash, "expected_payload_hash": exp_hash,
                "hash_match": actual_hash == exp_hash,
            })
            replay_idx += 1

    captures = core_replay._consolidation_ledger if core_replay._consolidation_ledger else []
    summary = {
        "arm": "divergent_warmup_replay", "seed_env": seed_env,
        "n_expected": n_expected, "n_replayed": replay_idx,
        "hash_mismatches": hash_mismatches,
        "warmup_act_div": round(warmup_act_div, 8),
        "warmup_energy_div": round(warmup_energy_div, 8),
        "warmup_weight_delta_l1": round(warmup_weight_delta, 8),
        "fast_weight_l1": round(_fast_weight_l1(core_replay), 8),
        "slow_weight_l1": round(_slow_weight_l1(core_replay), 8),
        "capture_count": len(captures),
        "tag_mass_final": round(_tag_mass(core_replay), 8),
        "n_tagged_connections": _n_tagged(core_replay),
        "saturation_frac": round(_saturation_frac(core_replay), 8),
        "max_abs_weight": round(float(np.max(np.abs(core_replay._weight_cache))), 8)
            if len(core_replay._weight_cache) > 0 else 0.0,
        "nan_hit": nan_hit,
    }
    return event_log, summary, captures


def run_matched_warmup_control(seed_env, pulse_dur, code_sha):
    cfg_ref = AnivaConfig(unit_count=300, seed=seed_env,
                          event_pair_plasticity_enabled=False,
                          consolidation_enabled=False)
    core_ref = LifeCore(cfg_ref)
    ref_snap = _snapshot_core_state(core_ref)

    cfg_div = AnivaConfig(unit_count=300, seed=seed_env + DIVERGENT_NOISE_OFFSET,
                          event_pair_plasticity_enabled=False,
                          consolidation_enabled=False)
    core_div = LifeCore(cfg_div)
    _restore_core_state(core_div, ref_snap)

    env_div = Environment()
    w0_div = core_div._weight_cache.copy()

    for s in range(WARMUP_END):
        influences = env_div.compute_influences(core_div.units, s)
        core_div.step(env_influences=influences if influences else None)

    core_div._weight_cache[:] = w0_div
    for i, conn in enumerate(core_div.connections):
        conn.weight = float(w0_div[i])
    warmup_weight_delta = float(np.sum(np.abs(core_div._weight_cache - w0_div)))
    warmup_act_div = _activation_divergence(core_div._activations, ref_snap["activations"])

    cfg_replay = _make_cfg(seed_env, event_pair_on=True, consolidation_on=True)
    core_replay = LifeCore(cfg_replay)
    core_replay._activations[:] = core_div._activations
    core_replay._energies[:] = core_div._energies
    core_replay._traces[:] = core_div._traces
    core_replay._event_trace[:] = core_div._event_trace
    core_replay._weight_cache[:] = core_div._weight_cache
    for i, conn in enumerate(core_replay.connections):
        conn.weight = float(core_div._weight_cache[i])

    env_replay = Environment()
    nan_hit = False

    for s in range(WARMUP_END, TOTAL_STEPS):
        influences = env_replay.compute_influences(core_replay.units, s)
        core_replay.step(env_influences=influences if influences else None)
        if not nan_hit and np.any(np.isnan(core_replay._activations)):
            nan_hit = True

    captures = core_replay._consolidation_ledger if core_replay._consolidation_ledger else []
    summary = {
        "arm": "matched_warmup_control", "seed_env": seed_env,
        "warmup_act_div": round(warmup_act_div, 8),
        "warmup_weight_delta_l1": round(warmup_weight_delta, 8),
        "fast_weight_l1": round(_fast_weight_l1(core_replay), 8),
        "slow_weight_l1": round(_slow_weight_l1(core_replay), 8),
        "capture_count": len(captures),
        "tag_mass_final": round(_tag_mass(core_replay), 8),
        "n_tagged_connections": _n_tagged(core_replay),
        "saturation_frac": round(_saturation_frac(core_replay), 8),
        "max_abs_weight": round(float(np.max(np.abs(core_replay._weight_cache))), 8)
            if len(core_replay._weight_cache) > 0 else 0.0,
        "nan_hit": nan_hit,
    }
    return [], summary, captures


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def main(argv=None):
    p = argparse.ArgumentParser(description="Phase 10C.2 — Capture Diagnostics Smoke")
    p.add_argument("--seeds", type=int, nargs="+", default=[42, 77])
    p.add_argument("--total-steps", type=int, default=TOTAL_STEPS)
    p.add_argument("--decision-interval", type=int, default=DECISION_INTERVAL)
    p.add_argument("--estimate-only", action="store_true")
    p.add_argument("--dry-run-schedule", action="store_true")
    p.add_argument("--captures-csv", type=str,
                   default="results/phase10C2_capture_diagnostics_captures.csv")
    p.add_argument("--summary-csv", type=str,
                   default="results/phase10C2_capture_diagnostics_summary.csv")
    p.add_argument("--summary-json", type=str,
                   default="results/phase10C2_capture_diagnostics_summary.json")
    args = p.parse_args(argv)

    decision_points = list(range(WARMUP_END, args.total_steps, args.decision_interval))
    n_decisions = len(decision_points)

    print("Phase 10C.2 — Capture Diagnostics Smoke")
    print(f"  seeds={args.seeds}  unit_count=300"
          f"  steps={args.total_steps}  warmup={WARMUP_END}")
    print(f"  decision_points={n_decisions}  interval={args.decision_interval}")
    print(f"  diagnostics: consolidation_diagnostics_enabled=True")
    print(f"  gate logic: UNCHANGED from 10A.2C")
    print()

    if args.dry_run_schedule:
        print(f"  Arms: closed_loop, exact_replay,"
              f" divergent_warmup_replay, matched_warmup_control")
        print(f"  Decision points (first 5): {decision_points[:5]}...")
        print(f"  Decision points (last 5): ...{decision_points[-5:]}")
        print(f"  Warmup: 0–{WARMUP_END-1} (2000 steps), plasticity OFF, no events")
        print(f"  Replay: {WARMUP_END}–{args.total_steps-1} (5500 steps), 9C+9D ON")
        print(f"  Diagnostics: 6 per-capture metrics (tag_trace_alignment, HHI, etc.)")
        print(f"  Baseline check: seed42≈{BASELINE_SLOW_L1[42]}, seed77≈{BASELINE_SLOW_L1[77]}")
        print(f"  Estimated per seed: ~5-7 min")
        print(f"  Total: ~10-14 min for 2 seeds")
        print()
        return 0

    code_sha = _git_sha()
    all_capture_rows = []
    all_summaries = []
    all_arm_diag = []

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
            el, s_info, _ = run_closed_loop(
                cfg, seed_env=seed, seed_sched=seed + 1000,
                decision_points=decision_points, pulse_dur=PULSE_DURATION,
                code_sha=code_sha, config_sha=config_sha)
            wall = time.time() - t0
            n_events = sum(1 for d in el if d["chosen_event"] != "none")
            print(f"{wall:.0f}s  events={n_events}")
            est_div = wall * 2.5
            est_matched = wall * 2.2
            per_seed = wall * 1.0 + wall * 1.0 + est_div + est_matched
            print(f"    Estimated per seed: ~{per_seed:.0f}s"
                  f"  (closed: {wall:.0f}s, exact: ~{wall:.0f}s,"
                  f" divergent: ~{est_div:.0f}s, matched: ~{est_matched:.0f}s)")
        total = per_seed * len(args.seeds)
        print(f"\n  Total estimate: ~{total:.0f}s = ~{total/60:.0f} min")
        if total > 900:
            print(f"  ← ECS recommended (>15 min)")
        else:
            print(f"  ← OK for local")
        return 0

    for seed in args.seeds:
        print(f"══ Seed {seed} ══")

        cfg_9c_9d = _make_cfg(seed, event_pair_on=True, consolidation_on=True)
        assert cfg_9c_9d.event_pair_plasticity_enabled
        assert cfg_9c_9d.consolidation_enabled
        assert cfg_9c_9d.consolidation_diagnostics_enabled

        config_sha = hashlib.sha256(
            json.dumps({k: v for k, v in cfg_9c_9d.__dict__.items()
                        if not k.startswith("_")}, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]

        # ── Arm 1: closed_loop ──
        print(f"  [1/4] closed_loop ...", end=" ", flush=True)
        t0 = time.time()
        el_closed, s_closed, cap_closed = run_closed_loop(
            cfg_9c_9d, seed_env=seed, seed_sched=seed + 1000,
            decision_points=decision_points, pulse_dur=PULSE_DURATION,
            code_sha=code_sha, config_sha=config_sha)
        wall = time.time() - t0

        n_events = sum(1 for d in el_closed if d["chosen_event"] != "none")
        L_count = sum(1 for d in el_closed if d["chosen_event"] == "L")
        R_count = sum(1 for d in el_closed if d["chosen_event"] == "R")
        sim_count = sum(1 for d in el_closed if d["chosen_event"] == "simultaneous")
        print(f"{wall:.0f}s  events={n_events}"
              f"  L={L_count} R={R_count} sim={sim_count}"
              f"  captures={s_closed['capture_count']}"
              f"  slow_l1={s_closed['slow_weight_l1']:.8f}")

        event_trace = []
        for d in el_closed:
            if d["chosen_event"] != "none":
                event_trace.append((d["t_decision"], d["chosen_event"], d["payload_hash"]))
        trace_hash = _hash_trace(event_trace)

        s_closed.update({"event_count": n_events, "L_count": L_count,
                         "R_count": R_count, "simultaneous_count": sim_count,
                         "trace_hash": trace_hash, "wall_time_s": round(wall, 1)})
        all_summaries.append(s_closed)
        all_capture_rows.extend(_extract_capture_rows(seed, "closed_loop", cap_closed))
        diag_cl = _arm_diag_stats(cap_closed)
        diag_cl.update({"seed": seed, "arm": "closed_loop",
                        "capture_count": len(cap_closed),
                        "slow_weight_l1": s_closed["slow_weight_l1"]})
        all_arm_diag.append(diag_cl)

        # ── Arm 2: exact_replay ──
        print(f"  [2/4] exact_replay ...", end=" ", flush=True)
        t0 = time.time()
        cfg_exact = _make_cfg(seed, event_pair_on=True, consolidation_on=True)
        el_exact, s_exact, cap_exact = run_exact_replay(
            cfg_exact, seed_env=seed, event_trace=event_trace,
            pulse_dur=PULSE_DURATION, code_sha=code_sha, config_sha=config_sha)
        wall = time.time() - t0

        replay_exact = (s_exact["hash_mismatches"] == 0
                        and s_exact["n_replayed"] == s_exact["n_expected"])
        s_exact.update({"trace_hash": trace_hash, "wall_time_s": round(wall, 1),
                        "replay_exact": replay_exact})
        all_summaries.append(s_exact)
        all_capture_rows.extend(_extract_capture_rows(seed, "exact_replay", cap_exact))
        diag_ex = _arm_diag_stats(cap_exact)
        diag_ex.update({"seed": seed, "arm": "exact_replay",
                        "capture_count": len(cap_exact),
                        "slow_weight_l1": s_exact["slow_weight_l1"]})
        all_arm_diag.append(diag_ex)

        status = "EXACT" if replay_exact else "MISMATCH"
        print(f"{wall:.0f}s  replayed={s_exact['n_replayed']}"
              f"  captures={s_exact['capture_count']}"
              f"  slow_l1={s_exact['slow_weight_l1']:.8f}"
              f"  w_delta={s_exact['warmup_weight_delta_l1']:.6f}"
              f"  [{status}]")

        # ── Arm 3: divergent_warmup_replay ──
        print(f"  [3/4] divergent_warmup_replay ...", end=" ", flush=True)
        t0 = time.time()
        el_div, s_div, cap_div = run_divergent_warmup_replay(
            seed_env=seed, event_trace=event_trace,
            pulse_dur=PULSE_DURATION, code_sha=code_sha)
        wall = time.time() - t0

        replay_div = (s_div["hash_mismatches"] == 0
                      and s_div["n_replayed"] == s_div["n_expected"])
        s_div.update({"trace_hash": trace_hash, "wall_time_s": round(wall, 1),
                      "replay_exact": replay_div})
        all_summaries.append(s_div)
        all_capture_rows.extend(_extract_capture_rows(seed, "divergent_warmup_replay", cap_div))
        diag_dv = _arm_diag_stats(cap_div)
        diag_dv.update({"seed": seed, "arm": "divergent_warmup_replay",
                        "capture_count": len(cap_div),
                        "slow_weight_l1": s_div["slow_weight_l1"]})
        all_arm_diag.append(diag_dv)

        p6_ok = s_div["warmup_act_div"] > 1e-8
        print(f"{wall:.0f}s  replayed={s_div['n_replayed']}"
              f"  captures={s_div['capture_count']}"
              f"  slow_l1={s_div['slow_weight_l1']:.8f}"
              f"  act_div={s_div['warmup_act_div']:.6f}"
              f"  [P6={'OK' if p6_ok else 'FAIL'}]")

        # ── Arm 4: matched_warmup_control ──
        print(f"  [4/4] matched_warmup_control ...", end=" ", flush=True)
        t0 = time.time()
        _, s_matched, cap_matched = run_matched_warmup_control(
            seed_env=seed, pulse_dur=PULSE_DURATION, code_sha=code_sha)
        wall = time.time() - t0

        s_matched["wall_time_s"] = round(wall, 1)
        all_summaries.append(s_matched)
        all_capture_rows.extend(_extract_capture_rows(seed, "matched_warmup_control", cap_matched))
        diag_mc = _arm_diag_stats(cap_matched)
        diag_mc.update({"seed": seed, "arm": "matched_warmup_control",
                        "capture_count": len(cap_matched),
                        "slow_weight_l1": s_matched["slow_weight_l1"]})
        all_arm_diag.append(diag_mc)

        print(f"{wall:.0f}s  captures={s_matched['capture_count']}"
              f"  slow_l1={s_matched['slow_weight_l1']:.8f}"
              f"  w_delta={s_matched['warmup_weight_delta_l1']:.6f}"
              f"  {'← NONZERO?' if s_matched['slow_weight_l1'] > 1e-6 else '← clean'}")

    # ── Baseline gate-invariance check ──
    print()
    print("══ Baseline Gate-Invariance Check ══")
    baseline_ok = True
    for seed in args.seeds:
        if seed not in BASELINE_SLOW_L1:
            continue
        seed_sums = [s for s in all_summaries if s["seed_env"] == seed]
        by_arm = {s["arm"]: s for s in seed_sums}
        cl_sl = by_arm.get("closed_loop", {}).get("slow_weight_l1", float("nan"))
        expected = BASELINE_SLOW_L1[seed]
        diff = abs(cl_sl - expected)
        ok = diff <= BASELINE_TOL
        if not ok:
            baseline_ok = False
        print(f"  seed{seed}: closed_loop slow_l1={cl_sl:.8f}"
              f"  expected≈{expected:.8f}  diff={diff:.2e}"
              f"  {'OK' if ok else '⚠ MISMATCH — gate may have changed'}")
    print()

    # ── Diagnostic comparison: closed vs divergent ──
    print("══ Diagnostic Comparison (closed vs divergent) ══")
    for seed in args.seeds:
        by_arm_diag = {d["arm"]: d for d in all_arm_diag if d["seed"] == seed}
        cl_d = by_arm_diag.get("closed_loop", {})
        dv_d = by_arm_diag.get("divergent_warmup_replay", {})
        print(f"  Seed {seed}:")
        for f in DIAG_FIELDS:
            cl_mean = cl_d.get(f"{f}_mean", float("nan"))
            dv_mean = dv_d.get(f"{f}_mean", float("nan"))
            delta = dv_mean - cl_mean
            print(f"    {f:<28} closed={cl_mean:.6f}  divergent={dv_mean:.6f}"
                  f"  Δ={delta:+.6f}")
    print()

    # ── Per-arm summary table ──
    print("══ Per-Arm Summary ══")
    header = (f"  {'Seed':<5} {'Arm':<24}"
              f" {'Slow_L1':>12} {'Capt':>5}"
              f" {'align_mean':>11} {'tag_conc_mean':>14} {'trace_conc_mean':>16}")
    print(header)
    for d in all_arm_diag:
        print(f"  {d['seed']:<5} {d['arm']:<24}"
              f" {d['slow_weight_l1']:>12.8f}"
              f" {d['capture_count']:>5}"
              f" {d.get('tag_trace_alignment_mean', float('nan')):>11.6f}"
              f" {d.get('tag_concentration_mean', float('nan')):>14.6f}"
              f" {d.get('trace_concentration_mean', float('nan')):>16.6f}")
    print()

    # ── Save per-capture CSV ──
    if args.captures_csv and all_capture_rows:
        with open(args.captures_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CAPTURE_CSV_FIELDS, extrasaction="ignore")
            w.writeheader()
            w.writerows(all_capture_rows)
        print(f"  Captures CSV: {args.captures_csv} ({len(all_capture_rows)} rows)")

    # ── Save arm summary CSV ──
    if args.summary_csv and all_arm_diag:
        diag_fields_all = []
        seen_df = set()
        for d in all_arm_diag:
            for k in d:
                if k not in seen_df:
                    diag_fields_all.append(k)
                    seen_df.add(k)
        with open(args.summary_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=diag_fields_all, extrasaction="ignore")
            w.writeheader()
            w.writerows(all_arm_diag)
        print(f"  Summary CSV: {args.summary_csv}")

    # ── Save summary JSON ──
    if args.summary_json:
        json_sums = []
        for s in all_summaries:
            js = {}
            for k, v in s.items():
                if isinstance(v, (np.ndarray, list)):
                    js[k] = str(v)
                else:
                    js[k] = v
            json_sums.append(js)
        with open(args.summary_json, "w", encoding="utf-8") as f:
            json.dump({
                "experiment": "phase10C2_capture_diagnostics_smoke",
                "frozen_params": {
                    "w": W, "b_none": B_NONE, "b_L": B_L, "b_R": B_R,
                    "b_sim": B_SIM, "tau": TAU,
                    "total_steps": args.total_steps,
                    "warmup_end": WARMUP_END,
                    "decision_interval": args.decision_interval,
                    "pulse_duration": PULSE_DURATION,
                    "divergent_noise_offset": DIVERGENT_NOISE_OFFSET,
                    "consolidation_diagnostics_enabled": True,
                    "gate_logic": "UNCHANGED from 10A.2C",
                },
                "baseline_check": {
                    str(seed): {
                        "expected": BASELINE_SLOW_L1.get(seed),
                        "actual": next(
                            (s["slow_weight_l1"] for s in all_summaries
                             if s["seed_env"] == seed and s["arm"] == "closed_loop"), None),
                    }
                    for seed in args.seeds if seed in BASELINE_SLOW_L1
                },
                "arm_diagnostics": all_arm_diag,
                "summaries": json_sums,
                "n_seeds": len(args.seeds),
            }, f, indent=2, ensure_ascii=False)
        print(f"  JSON: {args.summary_json}")

    if not baseline_ok:
        print("\n  ⚠ Baseline mismatch — gate invariance not confirmed.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())