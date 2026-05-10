"""Phase 10A.2C — Divergent Warmup Replay (new replay control).

Tests whether sustained state-context divergence from a 2000-step
divergent warmup period produces measurable slow-structure differences
under identical event replay.

Same seed / same topology / same event log — different warmup prehistory.
Plasticity OFF during warmup (via weight snapshot/restore).

Scheme E (initial activation perturbation) is exhausted.
This is Route A from the 10A.2B.2 decision.
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


# ── State snapshot / restore (for divergent warmup) ──

def _snapshot_core_state(core):
    """Capture all mutable state needed to clone a core's identity."""
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
    """Overwrite a core's mutable state from a snapshot."""
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
    """Parameterized stochastic scheduler. Fixed θ, no learning, no memory."""

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
            "logits": {
                "none": float(logit_none), "L": float(logit_L),
                "R": float(logit_R), "simultaneous": float(logit_sim),
            },
            "probs": {
                "none": float(probs[0]), "L": float(probs[1]),
                "R": float(probs[2]), "simultaneous": float(probs[3]),
            },
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


def _save_event_log(rows, path):
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


def _make_cfg(seed, event_pair_on=True, consolidation_on=True):
    return AnivaConfig(
        unit_count=300,
        seed=seed,
        event_pair_plasticity_enabled=event_pair_on,
        event_pair_ledger_enabled=event_pair_on,
        consolidation_enabled=consolidation_on,
        consolidation_ledger_enabled=consolidation_on,
    )


# ═══════════════════════════════════════════════════════════════════
# Arm runners
# ═══════════════════════════════════════════════════════════════════

def run_closed_loop(cfg, seed_env, seed_sched, decision_points, pulse_dur,
                    code_sha, config_sha):
    """Standard closed_loop arm. Scheduler active, 9C+9D ON."""
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
                "run_id": f"phase10A2C_closed_seed{seed_env}",
                "arm": "closed_loop",
                "seed_env": seed_env,
                "code_sha": code_sha, "config_sha": config_sha,
                "t_decision": s,
                "chosen_event": chosen,
                "payload_hash": "",
            }

            if chosen != "none":
                phi = phi_cache[chosen]
                row["payload_hash"] = _hash_payload(phi)

                stim = STIM_MAP.get(chosen)
                if stim is None:
                    env.add_event(StimulusEvent(
                        stimulus=L_STIM, start_step=s, duration_steps=pulse_dur))
                    env.add_event(StimulusEvent(
                        stimulus=R_STIM, start_step=s, duration_steps=pulse_dur))
                else:
                    env.add_event(StimulusEvent(
                        stimulus=stim, start_step=s, duration_steps=pulse_dur))

                core.apply_event_pair_phi(phi)

            event_log.append(row)

    captures = core._consolidation_ledger if core._consolidation_ledger else []

    return event_log, {
        "arm": "closed_loop",
        "seed_env": seed_env,
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


def run_exact_replay(cfg, seed_env, event_trace, pulse_dur, code_sha, config_sha):
    """Exact replay with plasticity OFF during warmup (weight snapshot/restore).

    Warmup: steps 0-1999, no events, weights snapshotted at step 0 and
    restored at warmup end to guarantee no plasticity.
    Replay: steps 2000-7499, 9C+9D ON, events replayed.
    """
    core = LifeCore(cfg)
    # Disable 9C/9D during warmup
    core.config.event_pair_plasticity_enabled = False
    core.config.consolidation_enabled = False
    phi_cache = _build_phi_cache(core)
    env = Environment()
    nan_hit = False
    event_log = []
    replay_idx = 0
    n_expected = len(event_trace)
    hash_mismatches = 0

    # Snapshot initial weights for P7
    w0 = core._weight_cache.copy()

    for s in range(TOTAL_STEPS):
        if s == WARMUP_END:
            # Restore weights to pre-warmup values → plasticity OFF verified
            core._weight_cache[:] = w0
            for i, conn in enumerate(core.connections):
                conn.weight = float(w0[i])
            # Enable 9C/9D for replay phase
            core.config.event_pair_plasticity_enabled = True
            core.config.consolidation_enabled = True
            # Ensure consolidation structures exist
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
                env.add_event(StimulusEvent(
                    stimulus=L_STIM, start_step=s, duration_steps=pulse_dur))
                env.add_event(StimulusEvent(
                    stimulus=R_STIM, start_step=s, duration_steps=pulse_dur))
            else:
                env.add_event(StimulusEvent(
                    stimulus=stim, start_step=s, duration_steps=pulse_dur))

            core.apply_event_pair_phi(phi)

            row = {
                "run_id": f"phase10A2C_exact_seed{seed_env}",
                "arm": "exact_replay",
                "seed_env": seed_env,
                "code_sha": code_sha, "config_sha": config_sha,
                "t_decision": s,
                "chosen_event": chosen,
                "payload_hash": actual_hash,
                "expected_payload_hash": exp_hash,
                "hash_match": actual_hash == exp_hash,
            }
            event_log.append(row)
            replay_idx += 1

    captures = core._consolidation_ledger if core._consolidation_ledger else []

    # P7: weight delta during warmup
    warmup_weight_delta = float(np.sum(np.abs(core._weight_cache - w0)))

    return event_log, {
        "arm": "exact_replay",
        "seed_env": seed_env,
        "n_expected": n_expected,
        "n_replayed": replay_idx,
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


def run_divergent_warmup_replay(seed_env, event_trace, pulse_dur, code_sha):
    """Divergent warmup replay — primary test arm.

    Phase 1 (warmup, 0-1999):
      - Create core with seed+5000, overwrite topology/state to match
        the canonical (seed=seed_env) core.
      - Different RNG position → different noise trajectory.
      - no 9C, no 9D, weights snapshotted.
      - Save state at step 2000.

    Phase 2 (replay, 2000-7499):
      - Create NEW core with seed=seed_env (same post-init RNG as exact_replay).
      - Overwrite activations/energy/trace with saved divergent state.
      - 9C+9D ON, replay events.
    """
    # ── Phase 1: create canonical reference to snapshot topology ──
    cfg_ref = AnivaConfig(unit_count=300, seed=seed_env,
                          event_pair_plasticity_enabled=False,
                          consolidation_enabled=False)
    core_ref = LifeCore(cfg_ref)
    ref_snap = _snapshot_core_state(core_ref)

    # ── Phase 2: create divergent core, overwrite to match canonical ──
    cfg_div = AnivaConfig(unit_count=300, seed=seed_env + DIVERGENT_NOISE_OFFSET,
                          event_pair_plasticity_enabled=False,
                          consolidation_enabled=False)
    core_div = LifeCore(cfg_div)
    _restore_core_state(core_div, ref_snap)

    # Verify overwrite: positions & weights must match
    assert np.allclose(core_div._positions, core_ref._positions)
    assert np.allclose(core_div._weight_cache, core_ref._weight_cache)

    phi_cache_div = _build_phi_cache(core_div)
    env_div = Environment()
    w0_div = core_div._weight_cache.copy()
    acts_warmup_start = core_div._activations.copy()

    # ── Run divergent warmup ──
    for s in range(WARMUP_END):
        influences = env_div.compute_influences(core_div.units, s)
        core_div.step(env_influences=influences if influences else None)

    # Restore weights (plasticity OFF guarantee)
    warmup_weight_delta = float(np.sum(np.abs(core_div._weight_cache - w0_div)))
    core_div._weight_cache[:] = w0_div
    for i, conn in enumerate(core_div.connections):
        conn.weight = float(w0_div[i])

    # P6: state divergence at warmup end
    # Run the reference core through the same warmup for comparison
    env_ref = Environment()
    w0_ref = core_ref._weight_cache.copy()
    for s in range(WARMUP_END):
        influences = env_ref.compute_influences(core_ref.units, s)
        core_ref.step(env_influences=influences if influences else None)
    core_ref._weight_cache[:] = w0_ref
    for i, conn in enumerate(core_ref.connections):
        conn.weight = float(w0_ref[i])

    warmup_act_div = _activation_divergence(
        core_div._activations, core_ref._activations)
    warmup_energy_div = abs(
        float(np.mean(core_div._energies)) - float(np.mean(core_ref._energies)))

    # Save divergent state for phase 2
    div_state = {
        "activations": core_div._activations.copy(),
        "energies": core_div._energies.copy(),
        "traces": core_div._traces.copy(),
        "event_trace": core_div._event_trace.copy(),
        "weight_cache": core_div._weight_cache.copy(),
    }

    # ── Phase 3: replay on new core with matching seed ──
    cfg_replay = _make_cfg(seed_env, event_pair_on=True, consolidation_on=True)
    core_replay = LifeCore(cfg_replay)

    # Overwrite state with divergent warmup state
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
                env_replay.add_event(StimulusEvent(
                    stimulus=L_STIM, start_step=s, duration_steps=pulse_dur))
                env_replay.add_event(StimulusEvent(
                    stimulus=R_STIM, start_step=s, duration_steps=pulse_dur))
            else:
                env_replay.add_event(StimulusEvent(
                    stimulus=stim, start_step=s, duration_steps=pulse_dur))

            core_replay.apply_event_pair_phi(phi)

            row = {
                "run_id": f"phase10A2C_divergent_seed{seed_env}",
                "arm": "divergent_warmup_replay",
                "seed_env": seed_env,
                "code_sha": code_sha,
                "t_decision": s,
                "chosen_event": chosen,
                "payload_hash": actual_hash,
                "expected_payload_hash": exp_hash,
                "hash_match": actual_hash == exp_hash,
            }
            event_log.append(row)
            replay_idx += 1

    captures = core_replay._consolidation_ledger if core_replay._consolidation_ledger else []

    return event_log, {
        "arm": "divergent_warmup_replay",
        "seed_env": seed_env,
        "n_expected": n_expected,
        "n_replayed": replay_idx,
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


def run_matched_warmup_control(seed_env, pulse_dur, code_sha):
    """Matched warmup control — same divergent warmup, NO event replay.

    Phase 1 (warmup, 0-1999): same as divergent_warmup_replay.
    Phase 2 (post-warmup, 2000-7499): continue with no events, 9C+9D ON.
    Isolates whether divergent warmup alone deposits slow structure.
    """
    # ── Same divergent warmup as arm 3 ──
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

    phi_cache_div = _build_phi_cache(core_div)
    env_div = Environment()
    w0_div = core_div._weight_cache.copy()

    # Run warmup
    for s in range(WARMUP_END):
        influences = env_div.compute_influences(core_div.units, s)
        core_div.step(env_influences=influences if influences else None)

    warmup_weight_delta = float(np.sum(np.abs(core_div._weight_cache - w0_div)))
    core_div._weight_cache[:] = w0_div
    for i, conn in enumerate(core_div.connections):
        conn.weight = float(w0_div[i])

    warmup_act_div = _activation_divergence(
        core_div._activations, ref_snap["activations"])  # vs canonical at t=0

    # ── Phase 2: create new core, enable 9C+9D, NO events ──
    cfg_replay = _make_cfg(seed_env, event_pair_on=True, consolidation_on=True)
    core_replay = LifeCore(cfg_replay)

    # Overwrite state
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

    return [], {
        "arm": "matched_warmup_control",
        "seed_env": seed_env,
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


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def main(argv=None):
    p = argparse.ArgumentParser(
        description="Phase 10A.2C — Divergent Warmup Replay")
    p.add_argument("--seeds", type=int, nargs="+", default=[42, 77])
    p.add_argument("--unit-count", type=int, default=300)
    p.add_argument("--total-steps", type=int, default=TOTAL_STEPS)
    p.add_argument("--decision-interval", type=int, default=DECISION_INTERVAL)
    p.add_argument("--estimate-only", action="store_true")
    p.add_argument("--dry-run-schedule", action="store_true")
    p.add_argument("--output-csv", type=str,
                   default="results/phase10A2C_divergent_warmup.csv")
    p.add_argument("--events-csv", type=str,
                   default="results/phase10A2C_divergent_warmup_events.csv")
    p.add_argument("--summary-json", type=str,
                   default="results/phase10A2C_divergent_warmup_summary.json")
    args = p.parse_args(argv)

    decision_points = list(range(WARMUP_END, args.total_steps, args.decision_interval))
    n_decisions = len(decision_points)

    print("Phase 10A.2C — Divergent Warmup Replay")
    print(f"  seeds={args.seeds}  unit_count={args.unit_count}"
          f"  steps={args.total_steps}  warmup={WARMUP_END}")
    print(f"  decision_points={n_decisions}"
          f"  interval={args.decision_interval}")
    print(f"  scheduler θ: w={W} b_none={B_NONE} b_L={B_L} b_R={B_R}"
          f"  b_sim={B_SIM} tau={TAU}")
    print(f"  divergent noise offset: +{DIVERGENT_NOISE_OFFSET}")
    print(f"  warmup plasticity: OFF (weight snapshot/restore)")
    print(f"  post-warmup: 9C ON  9D ON")
    print()

    if args.dry_run_schedule:
        print(f"  Arms: closed_loop, exact_replay,"
              f" divergent_warmup_replay, matched_warmup_control")
        print(f"  Decision points (first 5): {decision_points[:5]}...")
        print(f"  Decision points (last 5): ...{decision_points[-5:]}")
        print(f"  Warmup: 0–{WARMUP_END-1} (2000 steps), plasticity OFF,"
              f" no events")
        print(f"  Replay: {WARMUP_END}–{TOTAL_STEPS-1} (5500 steps),"
              f" 9C+9D ON")
        print(f"  Estimated per seed: ~5-7 min")
        print(f"  Total: ~10-14 min for 2 seeds")
        print()
        return 0

    code_sha = _git_sha()
    all_event_rows = []
    all_summaries = []

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
            el, s_info = run_closed_loop(
                cfg, seed_env=seed, seed_sched=seed + 1000,
                decision_points=decision_points, pulse_dur=PULSE_DURATION,
                code_sha=code_sha, config_sha=config_sha)
            wall = time.time() - t0
            n_events = sum(1 for d in el if d["chosen_event"] != "none")
            print(f"{wall:.0f}s  events={n_events}")

            # divergent_warmup_replay: warmup (~70% of closed) + replay (~closed)
            est_div = wall * 2.5
            # matched_warmup_control: warmup + no-event
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

        config_sha = hashlib.sha256(
            json.dumps({k: v for k, v in cfg_9c_9d.__dict__.items()
                        if not k.startswith("_")}, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]

        # ── Arm 1: closed_loop ──
        print(f"  [1/4] closed_loop ...", end=" ", flush=True)
        t0 = time.time()
        el_closed, s_closed = run_closed_loop(
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
              f"  slow_l1={s_closed['slow_weight_l1']:.6f}")

        event_trace = []
        for d in el_closed:
            if d["chosen_event"] != "none":
                event_trace.append((d["t_decision"], d["chosen_event"],
                                    d["payload_hash"]))
        trace_hash = _hash_trace(event_trace)

        s_closed.update({
            "event_count": n_events,
            "L_count": L_count, "R_count": R_count,
            "simultaneous_count": sim_count,
            "trace_hash": trace_hash,
            "wall_time_s": round(wall, 1),
        })
        all_event_rows.extend(el_closed)
        all_summaries.append(s_closed)

        # ── Arm 2: exact_replay ──
        print(f"  [2/4] exact_replay (mirror check) ...", end=" ", flush=True)
        t0 = time.time()
        cfg_exact = _make_cfg(seed, event_pair_on=True, consolidation_on=True)
        el_exact, s_exact = run_exact_replay(
            cfg_exact, seed_env=seed, event_trace=event_trace,
            pulse_dur=PULSE_DURATION, code_sha=code_sha, config_sha=config_sha)
        wall = time.time() - t0

        replay_exact = (s_exact["hash_mismatches"] == 0
                        and s_exact["n_replayed"] == s_exact["n_expected"])
        s_exact.update({
            "trace_hash": trace_hash,
            "wall_time_s": round(wall, 1),
            "replay_exact": replay_exact,
        })
        all_event_rows.extend(el_exact)
        all_summaries.append(s_exact)

        status = "EXACT" if replay_exact else "MISMATCH"
        print(f"{wall:.0f}s  replayed={s_exact['n_replayed']}"
              f"  captures={s_exact['capture_count']}"
              f"  slow_l1={s_exact['slow_weight_l1']:.6f}"
              f"  w_delta={s_exact['warmup_weight_delta_l1']:.6f}"
              f"  [{status}]")

        # ── Arm 3: divergent_warmup_replay ──
        print(f"  [3/4] divergent_warmup_replay ...", end=" ", flush=True)
        t0 = time.time()
        el_div, s_div = run_divergent_warmup_replay(
            seed_env=seed, event_trace=event_trace,
            pulse_dur=PULSE_DURATION, code_sha=code_sha)
        wall = time.time() - t0

        replay_div = (s_div["hash_mismatches"] == 0
                       and s_div["n_replayed"] == s_div["n_expected"])
        s_div.update({
            "trace_hash": trace_hash,
            "wall_time_s": round(wall, 1),
            "replay_exact": replay_div,
        })
        all_event_rows.extend(el_div)
        all_summaries.append(s_div)

        p6_ok = s_div["warmup_act_div"] > 1e-8
        p6_str = f"P6={'OK' if p6_ok else '⚠ NO DIVERGENCE'}"
        print(f"{wall:.0f}s  replayed={s_div['n_replayed']}"
              f"  captures={s_div['capture_count']}"
              f"  slow_l1={s_div['slow_weight_l1']:.6f}"
              f"  act_div={s_div['warmup_act_div']:.6f}"
              f"  [{p6_str}]")

        # ── Arm 4: matched_warmup_control ──
        print(f"  [4/4] matched_warmup_control ...", end=" ", flush=True)
        t0 = time.time()
        _, s_matched = run_matched_warmup_control(
            seed_env=seed, pulse_dur=PULSE_DURATION, code_sha=code_sha)
        wall = time.time() - t0

        s_matched["wall_time_s"] = round(wall, 1)
        all_summaries.append(s_matched)

        print(f"{wall:.0f}s  captures={s_matched['capture_count']}"
              f"  slow_l1={s_matched['slow_weight_l1']:.6f}"
              f"  w_delta={s_matched['warmup_weight_delta_l1']:.6f}"
              f"  {'← NONZERO?' if s_matched['slow_weight_l1'] > 1e-6 else '← clean'}")

    # ── Cross-arm comparison ──
    print()
    print("══ Per-Arm Summary ══")
    header = (f"  {'Seed':<5} {'Arm':<24}"
              f" {'Slow_L1':>12} {'Fast_L1':>12}"
              f" {'Capt':>5} {'TagMass':>10} {'Satur%':>7}"
              f" {'WarmupDiv':>10} {'W_delta':>10} {'NaN':>5}")
    print(header)
    print(f"  {'-'*5} {'-'*24} {'-'*12} {'-'*12}"
          f" {'-'*5} {'-'*10} {'-'*7} {'-'*10} {'-'*10} {'-'*5}")
    for s in all_summaries:
        act_div = s.get("warmup_act_div", float("nan"))
        w_delta = s.get("warmup_weight_delta_l1", float("nan"))
        print(f"  {s['seed_env']:<5} {s['arm']:<24}"
              f" {s['slow_weight_l1']:>12.8f}"
              f" {s['fast_weight_l1']:>12.6f}"
              f" {s['capture_count']:>5}"
              f" {s['tag_mass_final']:>10.6f}"
              f" {s['saturation_frac']:>6.4f}"
              f" {act_div:>10.6f}"
              f" {w_delta:>10.6f}"
              f" {'Y' if s['nan_hit'] else 'N':>5}")
    print()

    # ── Cross-arm deltas ──
    print("══ Cross-Arm Deltas ══")
    for seed in args.seeds:
        seed_sums = [s for s in all_summaries if s["seed_env"] == seed]
        by_arm = {s["arm"]: s for s in seed_sums}
        cl = by_arm.get("closed_loop", {})
        ex = by_arm.get("exact_replay", {})
        dv = by_arm.get("divergent_warmup_replay", {})
        mc = by_arm.get("matched_warmup_control", {})

        cl_sl = cl.get("slow_weight_l1", float("nan"))
        ex_sl = ex.get("slow_weight_l1", float("nan"))
        dv_sl = dv.get("slow_weight_l1", float("nan"))
        mc_sl = mc.get("slow_weight_l1", float("nan"))

        cl_fl = cl.get("fast_weight_l1", float("nan"))
        ex_fl = ex.get("fast_weight_l1", float("nan"))
        dv_fl = dv.get("fast_weight_l1", float("nan"))

        d_ce_slow = cl_sl - ex_sl
        d_cd_slow = cl_sl - dv_sl
        d_ed_slow = ex_sl - dv_sl
        d_cd_fast = cl_fl - dv_fl
        d_dm_slow = dv_sl - mc_sl  # net effect of events on diverged state

        amp = abs(d_ed_slow) / abs(d_cd_fast) if abs(d_cd_fast) > 1e-30 else 0.0
        mirror_ok = abs(d_ce_slow) < max(1e-6, 0.01 * cl_sl) if cl_sl > 0 else True
        p6 = dv.get("warmup_act_div", 0.0) > 1e-8 if "warmup_act_div" in dv else False

        print(f"  Seed {seed}:")
        print(f"    slow_l1:  closed={cl_sl:.8f}  exact={ex_sl:.8f}"
              f"  divergent={dv_sl:.8f}  matched_ctrl={mc_sl:.8f}")
        print(f"    fast_l1:  closed={cl_fl:.6f}  exact={ex_fl:.6f}"
              f"  divergent={dv_fl:.6f}")
        print(f"    warmup_act_div            = {dv.get('warmup_act_div', 'N/A')}"
              f"  ({'P6 OK' if p6 else 'P6 FAIL'})")
        print(f"    warmup_energy_div         = {dv.get('warmup_energy_div', 'N/A')}")
        print(f"    warmup_weight_delta (div) = {dv.get('warmup_weight_delta_l1', 'N/A')}")
        print(f"    Δ(closed-exact)_slow      = {d_ce_slow:.8f}"
              f"  {'← MIRROR OK' if mirror_ok else '← PROTOCOL BUG'}")
        print(f"    Δ(closed-divergent)_slow  = {d_cd_slow:.8f}")
        print(f"    Δ(exact-divergent)_slow   = {d_ed_slow:.8f}")
        print(f"    Δ(closed-divergent)_fast  = {d_cd_fast:.8f}")
        print(f"    Δ(divergent-matched_ctrl) = {d_dm_slow:.8f}"
              f"  (net event effect on diverged state)")
        print(f"    amplification_ratio       = {amp:.6f}")
        print(f"    captures:"
              f" closed={cl.get('capture_count','?')}"
              f" exact={ex.get('capture_count','?')}"
              f" divergent={dv.get('capture_count','?')}"
              f" matched_ctrl={mc.get('capture_count','?')}")
    print()

    # ── Hard protocol ──
    n_hard_ok = 0
    for seed in args.seeds:
        seed_sums = [s for s in all_summaries if s["seed_env"] == seed]
        by_arm = {s["arm"]: s for s in seed_sums}

        p1 = not any(s["nan_hit"] for s in seed_sums)
        p2 = all(s["max_abs_weight"] < 10.0 for s in seed_sums)
        p3 = all(s.get("hash_mismatches", 0) == 0 for s in seed_sums
                 if s["arm"] != "closed_loop"
                 and s["arm"] != "matched_warmup_control")

        cl_ev = by_arm.get("closed_loop", {}).get("event_count", -1)
        ex_ev = by_arm.get("exact_replay", {}).get("n_replayed", -1)
        dv_ev = by_arm.get("divergent_warmup_replay", {}).get("n_replayed", -1)
        p4 = (cl_ev == ex_ev == dv_ev) and cl_ev >= 0

        cl_sl = by_arm.get("closed_loop", {}).get("slow_weight_l1", 0.0)
        ex_sl = by_arm.get("exact_replay", {}).get("slow_weight_l1", 0.0)
        p5 = abs(cl_sl - ex_sl) < max(1e-6, 0.01 * cl_sl) if cl_sl > 0 else True

        p6 = by_arm.get("divergent_warmup_replay", {}).get("warmup_act_div", 0.0) > 1e-8

        # P7: weights unchanged during warmup (for exact and divergent)
        ex_wd = by_arm.get("exact_replay", {}).get("warmup_weight_delta_l1", float("nan"))
        dv_wd = by_arm.get("divergent_warmup_replay", {}).get("warmup_weight_delta_l1", float("nan"))
        p7 = (ex_wd < 1e-6 and dv_wd < 1e-6)

        # P8: matched_warmup_control slow_l1 negligible
        mc_sl = by_arm.get("matched_warmup_control", {}).get("slow_weight_l1", 0.0)
        p8 = mc_sl < 1e-6

        seed_ok = p1 and p2 and p3 and p4 and p5 and p6 and p7 and p8
        if seed_ok:
            n_hard_ok += 1

        checks = [
            f"P1={'OK' if p1 else 'FAIL'}",
            f"P2={'OK' if p2 else 'FAIL'}",
            f"P3={'OK' if p3 else 'FAIL'}",
            f"P4={'OK' if p4 else 'FAIL'}",
            f"P5={'OK' if p5 else 'FAIL'}",
            f"P6={'OK' if p6 else 'FAIL'}",
            f"P7={'OK' if p7 else 'FAIL'}",
            f"P8={'OK' if p8 else 'FAIL'}",
        ]
        print(f"  Seed {seed}: {'  '.join(checks)}"
              f"  → {'PASS' if seed_ok else 'FAIL'}")

        # If P6 fails, print explicit warning
        if not p6:
            print(f"    ⚠ P6 FAIL: divergent warmup did not produce state divergence."
                  f" warmup_act_div={by_arm.get('divergent_warmup_replay', {}).get('warmup_act_div', 0)}")
            print(f"    Mechanism failure, NOT a scientific negative."
                  f" Do not interpret slow/fast deltas.")
        if not p7:
            print(f"    ⚠ P7 FAIL: weights changed during warmup."
                  f" exact_wd={ex_wd}  divergent_wd={dv_wd}")

    print(f"\n  Hard pass: {n_hard_ok}/{len(args.seeds)}")
    print()

    # ── Save outputs ──
    if args.events_csv:
        _save_event_log(all_event_rows, args.events_csv)
        print(f"  Events CSV: {args.events_csv} ({len(all_event_rows)} rows)")

    if args.output_csv:
        if all_summaries:
            all_sf, seen_sf = [], set()
            for s in all_summaries:
                for k in s:
                    if k not in seen_sf and not isinstance(s[k], (np.ndarray, list, dict)):
                        all_sf.append(k)
                        seen_sf.add(k)
            with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=all_sf, extrasaction="ignore")
                w.writeheader()
                w.writerows(all_summaries)
            print(f"  Summary CSV: {args.output_csv}")

    if args.summary_json:
        json_sums = []
        for s in all_summaries:
            js = {}
            for k, v in s.items():
                if isinstance(v, (np.ndarray, list)):
                    js[k] = float(v) if isinstance(v, (np.floating, float, int)) else str(v)
                else:
                    js[k] = v
            json_sums.append(js)

        with open(args.summary_json, "w", encoding="utf-8") as f:
            json.dump({
                "experiment": "phase10A2C_divergent_warmup_replay",
                "frozen_params": {
                    "w": W, "b_none": B_NONE, "b_L": B_L, "b_R": B_R,
                    "b_sim": B_SIM, "tau": TAU,
                    "total_steps": args.total_steps,
                    "warmup_end": WARMUP_END,
                    "decision_interval": args.decision_interval,
                    "pulse_duration": PULSE_DURATION,
                    "divergent_noise_offset": DIVERGENT_NOISE_OFFSET,
                    "warmup_plasticity": "OFF (snapshot/restore)",
                    "9C_enabled": True,
                    "9D_enabled": True,
                },
                "summaries": json_sums,
                "n_hard_pass": n_hard_ok,
                "n_seeds": len(args.seeds),
            }, f, indent=2, ensure_ascii=False)
        print(f"  JSON: {args.summary_json}")

    if n_hard_ok != len(args.seeds):
        print("\n  ⚠ Some seeds FAILED hard protocol."
              " Check P6/P7 failures before interpreting scientific signal.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
