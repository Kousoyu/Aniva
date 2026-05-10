"""Phase 10A.3 — Closed-Loop Slow Consolidation (2-seed pilot).

First time both 9C event-pair fast plasticity and 9D slow structural
consolidation are opened in the Phase 10 pipeline.

Tests whether 9D consolidation preserves or amplifies the hairline
fast-weight divergence (from 10A.2B.1) into measurable slow structure.

Frozen from docs/phase10A3_closed_loop_slow_consolidation_design.md.
"""

import argparse, csv, hashlib, json, sys, time
import numpy as np

from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.environment.environment import Stimulus, StimulusEvent, Environment

# ── Frozen from 10A.0 / 10A.1B / 10A.2B.1 ──
L_STIM = Stimulus(position=(-0.5, 0.0, 0.0), intensity=0.02, radius=0.5)
R_STIM = Stimulus(position=(0.5, 0.0, 0.0), intensity=0.02, radius=0.5)
STIM_MAP = {"L": L_STIM, "R": R_STIM}

TOTAL_STEPS = 7500
WARMUP = 2000
DECISION_INTERVAL = 250
PULSE_DURATION = 80

# Scheduler θ (FROZEN)
W = 5.0
B_NONE = +1.0
B_L = -1.5
B_R = -1.5
B_SIM = -3.0
TAU = 1.0

# Perturbation (FROZEN)
EPSILON = 0.02
PERTURB_SEED_OFFSET = 3000

# 9D defaults (from AnivaConfig, validated in Phase 9D)
CONSOLIDATION_TAG_TAU = 5000.0
CONSOLIDATION_CAPTURE_THRESHOLD = 0.5
CONSOLIDATION_SLOW_WEIGHT_MAX = 0.1
CONSOLIDATION_SLOW_WEIGHT_RATE = 0.1
CONSOLIDATION_CAPTURE_REFRACTORY = 500

# Fast-weight deltas from 10A.2B.1 (hardcoded, not re-measured)
FAST_DELTA_EXACT_VS_PERTURBED = {42: abs(0.00080134), 77: abs(-0.00046194)}

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
    """Fraction of effective weights near clamp ceiling."""
    eff = core._weight_cache + core._slow_weight_cache
    np.clip(eff, -1.0, 1.0, out=eff)
    return float(np.mean(np.abs(eff) >= 0.999))


def _tag_mass(core):
    return float(np.sum(np.abs(core._tag_cache)))


def _n_tagged(core):
    return int(np.sum(core._tag_cache > 0))


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


def _make_cfg(seed, consolidation_enabled=True):
    """Build AnivaConfig with 9C ON, 9D controlled."""
    return AnivaConfig(
        unit_count=300,
        seed=seed,
        event_pair_plasticity_enabled=True,
        event_pair_ledger_enabled=True,
        consolidation_enabled=consolidation_enabled,
        consolidation_ledger_enabled=consolidation_enabled,
    )


# ═══════════════════════════════════════════════════════════════════
# Arm runners
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
                "run_id": f"phase10A3_closed_seed{seed_env}",
                "arm": "closed_loop",
                "seed_env": seed_env, "seed_sched": seed_sched,
                "code_sha": code_sha, "config_sha": config_sha,
                "t_decision": s,
                "activity_L": round(act_l, 8),
                "activity_R": round(act_r, 8),
                "obs_hash": _hash_obs(act_l, act_r),
                "obs_schema_version": "1.0",
                "logit_none": round(result["logits"]["none"], 8),
                "logit_L": round(result["logits"]["L"], 8),
                "logit_R": round(result["logits"]["R"], 8),
                "logit_sim": round(result["logits"]["simultaneous"], 8),
                "prob_none": round(result["probs"]["none"], 8),
                "prob_L": round(result["probs"]["L"], 8),
                "prob_R": round(result["probs"]["R"], 8),
                "prob_sim": round(result["probs"]["simultaneous"], 8),
                "u_draw": round(result["u_draw"], 8),
                "chosen_event": chosen,
                "payload_hash": "",
                "applied_ok": True,
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

    slow = core._slow_weight_cache
    captures = core._consolidation_ledger if cfg.consolidation_enabled else []

    return event_log, {
        "arm": "closed_loop",
        "seed_env": seed_env,
        "fast_weight_l1": round(_fast_weight_l1(core), 8),
        "slow_weight_l1": round(_slow_weight_l1(core), 8),
        "slow_weight_max_abs": round(float(np.max(np.abs(slow))), 8) if len(slow) > 0 else 0.0,
        "capture_count": len(captures),
        "tag_mass_final": round(_tag_mass(core), 8),
        "n_tagged_connections": _n_tagged(core),
        "saturation_frac": round(_saturation_frac(core), 8),
        "max_abs_weight": round(float(np.max(np.abs(core._weight_cache))), 8) if len(core._weight_cache) > 0 else 0.0,
        "nan_hit": nan_hit,
    }


def run_exact_replay(cfg, seed_env, event_trace, pulse_dur, code_sha, config_sha):
    core = LifeCore(cfg)
    phi_cache = _build_phi_cache(core)
    env = Environment()

    nan_hit = False
    event_log = []
    replay_idx = 0
    n_expected = len(event_trace)
    hash_mismatches = 0

    for s in range(TOTAL_STEPS):
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
                "run_id": f"phase10A3_exact_seed{seed_env}",
                "arm": "exact_replay",
                "seed_env": seed_env,
                "code_sha": code_sha, "config_sha": config_sha,
                "t_decision": s,
                "chosen_event": chosen,
                "payload_hash": actual_hash,
                "expected_payload_hash": exp_hash,
                "hash_match": actual_hash == exp_hash,
                "applied_ok": True,
            }
            event_log.append(row)
            replay_idx += 1

    slow = core._slow_weight_cache
    captures = core._consolidation_ledger if cfg.consolidation_enabled else []

    return event_log, {
        "arm": "exact_replay",
        "seed_env": seed_env,
        "n_expected": n_expected,
        "n_replayed": replay_idx,
        "hash_mismatches": hash_mismatches,
        "fast_weight_l1": round(_fast_weight_l1(core), 8),
        "slow_weight_l1": round(_slow_weight_l1(core), 8),
        "slow_weight_max_abs": round(float(np.max(np.abs(slow))), 8) if len(slow) > 0 else 0.0,
        "capture_count": len(captures),
        "tag_mass_final": round(_tag_mass(core), 8),
        "n_tagged_connections": _n_tagged(core),
        "saturation_frac": round(_saturation_frac(core), 8),
        "max_abs_weight": round(float(np.max(np.abs(core._weight_cache))), 8) if len(core._weight_cache) > 0 else 0.0,
        "nan_hit": nan_hit,
    }


def run_perturbed_replay(cfg, seed_env, event_trace, pulse_dur, code_sha, config_sha):
    core = LifeCore(cfg)
    phi_cache = _build_phi_cache(core)

    # ── Perturbation at t=0 ──
    perturb_rng = np.random.default_rng(seed_env + PERTURB_SEED_OFFSET)
    eps_vec = perturb_rng.uniform(-EPSILON, EPSILON, size=core.unit_count)
    core._activations += eps_vec
    np.clip(core._activations, 0.0, 1.0, out=core._activations)

    env = Environment()
    nan_hit = False
    event_log = []
    replay_idx = 0
    n_expected = len(event_trace)
    hash_mismatches = 0

    for s in range(TOTAL_STEPS):
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
                "run_id": f"phase10A3_perturbed_seed{seed_env}",
                "arm": "perturbed_replay",
                "seed_env": seed_env,
                "code_sha": code_sha, "config_sha": config_sha,
                "t_decision": s,
                "chosen_event": chosen,
                "payload_hash": actual_hash,
                "expected_payload_hash": exp_hash,
                "hash_match": actual_hash == exp_hash,
                "applied_ok": True,
            }
            event_log.append(row)
            replay_idx += 1

    slow = core._slow_weight_cache
    captures = core._consolidation_ledger if cfg.consolidation_enabled else []

    return event_log, {
        "arm": "perturbed_replay",
        "seed_env": seed_env,
        "n_expected": n_expected,
        "n_replayed": replay_idx,
        "hash_mismatches": hash_mismatches,
        "fast_weight_l1": round(_fast_weight_l1(core), 8),
        "slow_weight_l1": round(_slow_weight_l1(core), 8),
        "slow_weight_max_abs": round(float(np.max(np.abs(slow))), 8) if len(slow) > 0 else 0.0,
        "capture_count": len(captures),
        "tag_mass_final": round(_tag_mass(core), 8),
        "n_tagged_connections": _n_tagged(core),
        "saturation_frac": round(_saturation_frac(core), 8),
        "max_abs_weight": round(float(np.max(np.abs(core._weight_cache))), 8) if len(core._weight_cache) > 0 else 0.0,
        "nan_hit": nan_hit,
    }


def run_no_event(cfg, seed_env, code_sha, config_sha):
    core = LifeCore(cfg)
    env = Environment()
    nan_hit = False

    for s in range(TOTAL_STEPS):
        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)

        if not nan_hit and np.any(np.isnan(core._activations)):
            nan_hit = True

    slow = core._slow_weight_cache
    captures = core._consolidation_ledger if cfg.consolidation_enabled else []

    return [], {
        "arm": "no_event_control",
        "seed_env": seed_env,
        "fast_weight_l1": round(_fast_weight_l1(core), 8),
        "slow_weight_l1": round(_slow_weight_l1(core), 8),
        "slow_weight_max_abs": round(float(np.max(np.abs(slow))), 8) if len(slow) > 0 else 0.0,
        "capture_count": len(captures),
        "tag_mass_final": round(_tag_mass(core), 8),
        "n_tagged_connections": _n_tagged(core),
        "saturation_frac": round(_saturation_frac(core), 8),
        "max_abs_weight": round(float(np.max(np.abs(core._weight_cache))), 8) if len(core._weight_cache) > 0 else 0.0,
        "nan_hit": nan_hit,
    }


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def main(argv=None):
    p = argparse.ArgumentParser(
        description="Phase 10A.3 — Closed-Loop Slow Consolidation (2-seed pilot)")
    p.add_argument("--seeds", type=int, nargs="+", default=[42, 77])
    p.add_argument("--unit-count", type=int, default=300)
    p.add_argument("--total-steps", type=int, default=TOTAL_STEPS)
    p.add_argument("--decision-interval", type=int, default=DECISION_INTERVAL)
    p.add_argument("--estimate-only", action="store_true")
    p.add_argument("--dry-run-schedule", action="store_true")
    p.add_argument("--output-csv", type=str,
                   default="results/phase10A3_slow_consolidation.csv")
    p.add_argument("--events-csv", type=str,
                   default="results/phase10A3_slow_consolidation_events.csv")
    p.add_argument("--summary-json", type=str,
                   default="results/phase10A3_slow_consolidation_summary.json")
    args = p.parse_args(argv)

    warmup = WARMUP
    pulse_dur = PULSE_DURATION
    decision_points = list(range(warmup, args.total_steps, args.decision_interval))
    n_decisions = len(decision_points)

    print("Phase 10A.3 — Closed-Loop Slow Consolidation (2-seed pilot)")
    print(f"  seeds={args.seeds}  unit_count={args.unit_count}"
          f"  steps={args.total_steps}  interval={args.decision_interval}")
    print(f"  decision_points={n_decisions}")
    print(f"  scheduler θ: w={W} b_none={B_NONE} b_L={B_L} b_R={B_R}"
          f" b_sim={B_SIM} tau={TAU}")
    print(f"  perturbation: ε={EPSILON}  target=activations  timing=t=0 once")
    print(f"  9C ON  9D ON")
    print(f"  9D params: tag_tau={CONSOLIDATION_TAG_TAU}"
          f"  capture_threshold={CONSOLIDATION_CAPTURE_THRESHOLD}"
          f"  slow_max={CONSOLIDATION_SLOW_WEIGHT_MAX}"
          f"  slow_rate={CONSOLIDATION_SLOW_WEIGHT_RATE}"
          f"  refractory={CONSOLIDATION_CAPTURE_REFRACTORY}")
    print()

    if args.dry_run_schedule:
        print(f"  Arms: closed_loop, exact_replay, perturbed_replay, no_event")
        print(f"  Decision points (first 5): {decision_points[:5]}...")
        print(f"  Decision points (last 5): ...{decision_points[-5:]}")
        print(f"  Expected per seed: closed ~2min, exact ~2min,"
              f" perturbed ~2min, no_event ~1.5min")
        print(f"  Total expected: ~7.5 min/seed × {len(args.seeds)} seeds"
              f" = ~{7.5 * len(args.seeds)} min")
        print()
        return 0

    code_sha = _git_sha()
    all_event_rows = []
    all_summaries = []

    for seed in args.seeds:
        print(f"── Seed {seed} ──")

        cfg_9c_9d = _make_cfg(seed, consolidation_enabled=True)
        assert cfg_9c_9d.event_pair_plasticity_enabled
        assert cfg_9c_9d.consolidation_enabled

        config_sha = hashlib.sha256(
            json.dumps({k: v for k, v in cfg_9c_9d.__dict__.items()
                        if not k.startswith("_")}, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]

        if args.estimate_only:
            print(f"  Estimating closed_loop...", end=" ", flush=True)
            t0 = time.time()
            el, s_info = run_closed_loop(
                cfg_9c_9d, seed_env=seed, seed_sched=seed + 1000,
                decision_points=decision_points, pulse_dur=pulse_dur,
                code_sha=code_sha, config_sha=config_sha)
            wall = time.time() - t0
            n_events = sum(1 for d in el if d["chosen_event"] != "none")
            n_captures = s_info["capture_count"]
            print(f"{wall:.0f}s  events={n_events}  captures={n_captures}")
            print(f"    Estimated exact_replay: ~{wall:.0f}s"
                  f"  perturbed_replay: ~{wall:.0f}s"
                  f"  no_event: ~{wall * 0.7:.0f}s")
            print(f"    Estimated total: ~{wall * 3.7:.0f}s per seed")
            continue

        # ── Arm 1: closed_loop ──
        print(f"  [1/4] closed_loop (9C+9D) ...", end=" ", flush=True)
        t0 = time.time()
        el_closed, s_closed = run_closed_loop(
            cfg_9c_9d, seed_env=seed, seed_sched=seed + 1000,
            decision_points=decision_points, pulse_dur=pulse_dur,
            code_sha=code_sha, config_sha=config_sha)
        wall = time.time() - t0

        n_events = sum(1 for d in el_closed if d["chosen_event"] != "none")
        none_count = sum(1 for d in el_closed if d["chosen_event"] == "none")
        L_count = sum(1 for d in el_closed if d["chosen_event"] == "L")
        R_count = sum(1 for d in el_closed if d["chosen_event"] == "R")
        sim_count = sum(1 for d in el_closed if d["chosen_event"] == "simultaneous")

        print(f"{wall:.0f}s  events={n_events}  L={L_count} R={R_count} sim={sim_count}"
              f"  captures={s_closed['capture_count']}"
              f"  slow_l1={s_closed['slow_weight_l1']:.4f}")

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
            "none_rate": round(none_count / max(len(el_closed), 1), 4),
            "trace_hash": trace_hash,
            "wall_time_s": round(wall, 1),
        })
        all_event_rows.extend(el_closed)
        all_summaries.append(s_closed)

        # ── Arm 2: exact_replay ──
        print(f"  [2/4] exact_replay (9C+9D, mirror check) ...", end=" ", flush=True)
        t0 = time.time()
        cfg_replay = _make_cfg(seed, consolidation_enabled=True)
        el_exact, s_exact = run_exact_replay(
            cfg_replay, seed_env=seed, event_trace=event_trace,
            pulse_dur=pulse_dur, code_sha=code_sha, config_sha=config_sha)
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
              f"  slow_l1={s_exact['slow_weight_l1']:.4f}  [{status}]")

        # ── Arm 3: perturbed_replay ──
        print(f"  [3/4] perturbed_replay (9C+9D, ε={EPSILON}) ...",
              end=" ", flush=True)
        t0 = time.time()
        cfg_pert = _make_cfg(seed, consolidation_enabled=True)
        el_pert, s_pert = run_perturbed_replay(
            cfg_pert, seed_env=seed, event_trace=event_trace,
            pulse_dur=pulse_dur, code_sha=code_sha, config_sha=config_sha)
        wall = time.time() - t0

        replay_exact_p = (s_pert["hash_mismatches"] == 0
                          and s_pert["n_replayed"] == s_pert["n_expected"])
        s_pert.update({
            "trace_hash": trace_hash,
            "wall_time_s": round(wall, 1),
            "replay_exact": replay_exact_p,
        })
        all_event_rows.extend(el_pert)
        all_summaries.append(s_pert)

        status_p = "EXACT" if replay_exact_p else "MISMATCH"
        print(f"{wall:.0f}s  replayed={s_pert['n_replayed']}"
              f"  captures={s_pert['capture_count']}"
              f"  slow_l1={s_pert['slow_weight_l1']:.4f}  [{status_p}]")

        # ── Arm 4: no_event ──
        print(f"  [4/4] no_event (9C+9D, baseline) ...", end=" ", flush=True)
        t0 = time.time()
        cfg_null = _make_cfg(seed, consolidation_enabled=True)
        _, s_null = run_no_event(
            cfg_null, seed_env=seed,
            code_sha=code_sha, config_sha=config_sha)
        wall = time.time() - t0

        s_null["wall_time_s"] = round(wall, 1)
        all_summaries.append(s_null)

        print(f"{wall:.0f}s  captures={s_null['capture_count']}"
              f"  slow_l1={s_null['slow_weight_l1']:.4f}"
              f"  {'← NONZERO?' if s_null['slow_weight_l1'] > 1e-6 else '← clean'}")

    if args.estimate_only:
        return 0

    # ── Cross-arm comparison ──
    print()
    print("── Slow Weight Comparison ──")
    header = (f"  {'Seed':<6} {'Arm':<18} {'Slow_L1':>12} {'Captures':>9}"
              f" {'TagMass':>10} {'Satur%':>7} {'Fast_L1':>12} {'NaN':>5}")
    print(header)
    print(f"  {'-'*6} {'-'*18} {'-'*12} {'-'*9} {'-'*10} {'-'*7} {'-'*12} {'-'*5}")
    for s in all_summaries:
        print(f"  {s['seed_env']:<6} {s['arm']:<18}"
              f" {s['slow_weight_l1']:>12.6f}"
              f" {s['capture_count']:>9}"
              f" {s['tag_mass_final']:>10.6f}"
              f" {s['saturation_frac']:>6.4f}"
              f" {s['fast_weight_l1']:>12.6f}"
              f" {'Y' if s['nan_hit'] else 'N':>5}")
    print()

    # ── Per-seed slow deltas ──
    print("── Slow Weight Deltas ──")
    for seed in args.seeds:
        seed_sums = [s for s in all_summaries if s["seed_env"] == seed]
        by_arm = {s["arm"]: s for s in seed_sums}
        cl = by_arm.get("closed_loop", {})
        ex = by_arm.get("exact_replay", {})
        pe = by_arm.get("perturbed_replay", {})
        ne = by_arm.get("no_event_control", {})

        cl_slow = cl.get("slow_weight_l1", float("nan"))
        ex_slow = ex.get("slow_weight_l1", float("nan"))
        pe_slow = pe.get("slow_weight_l1", float("nan"))
        ne_slow = ne.get("slow_weight_l1", float("nan"))

        d_ce = cl_slow - ex_slow
        d_cp = cl_slow - pe_slow
        d_ep = ex_slow - pe_slow
        d_cn = cl_slow - ne_slow

        fast_delta_ref = FAST_DELTA_EXACT_VS_PERTURBED.get(seed, 1.0)
        amp_ratio = abs(d_ep) / fast_delta_ref if fast_delta_ref > 1e-30 else float("nan")

        mirror_ok = abs(d_ce) < max(1e-6, 0.01 * cl_slow) if cl_slow > 0 else True

        print(f"  Seed {seed}:")
        print(f"    closed_slow_l1      = {cl_slow:.8f}")
        print(f"    exact_slow_l1       = {ex_slow:.8f}")
        print(f"    perturbed_slow_l1   = {pe_slow:.8f}")
        print(f"    no_event_slow_l1    = {ne_slow:.8f}")
        print(f"    Δ(closed-exact)     = {d_ce:.8f}"
              f"  {'← MIRROR OK' if mirror_ok else '← PROTOCOL WARN'}")
        print(f"    Δ(closed-perturbed) = {d_cp:.8f}")
        print(f"    Δ(exact-perturbed)  = {d_ep:.8f}"
              f"  (fast ref = {fast_delta_ref:.8f})")
        print(f"    amplification_ratio = {amp_ratio:.4f}"
              f"  {'← AMPLIFIED' if amp_ratio > 1.0 else '← dampened/unchanged'}")
        print(f"    Δ(closed-no_event)  = {d_cn:.8f}")
        print(f"    captures:"
              f" closed={cl.get('capture_count','?')}"
              f" exact={ex.get('capture_count','?')}"
              f" perturbed={pe.get('capture_count','?')}"
              f" noevent={ne.get('capture_count','?')}")
    print()

    # ── Hard protocol ──
    n_hard_ok = 0
    for seed in args.seeds:
        seed_sums = [s for s in all_summaries if s["seed_env"] == seed]
        by_arm = {s["arm"]: s for s in seed_sums}

        p1 = not any(s["nan_hit"] for s in seed_sums)
        p2 = all(s["max_abs_weight"] < 10.0 for s in seed_sums)
        p3 = all(s.get("hash_mismatches", 0) == 0 for s in seed_sums
                 if s["arm"] != "closed_loop" and s["arm"] != "no_event_control")
        cl_ev = by_arm.get("closed_loop", {}).get("event_count", -1)
        ex_ev = by_arm.get("exact_replay", {}).get("n_replayed", -1)
        pe_ev = by_arm.get("perturbed_replay", {}).get("n_replayed", -1)
        p4 = (cl_ev == ex_ev == pe_ev) and cl_ev >= 0

        # P6: mirror sanity — exact must be close to closed
        cl_sl = by_arm.get("closed_loop", {}).get("slow_weight_l1", 0.0)
        ex_sl = by_arm.get("exact_replay", {}).get("slow_weight_l1", 0.0)
        p6 = abs(cl_sl - ex_sl) < max(1e-6, 0.01 * cl_sl) if cl_sl > 0 else True

        seed_ok = p1 and p2 and p3 and p4 and p6
        if seed_ok:
            n_hard_ok += 1

        print(f"  Seed {seed} hard protocol:"
              f"  P1(nan)={'OK' if p1 else 'FAIL'}"
              f"  P2(explosion)={'OK' if p2 else 'FAIL'}"
              f"  P3(replay_hash)={'OK' if p3 else 'FAIL'}"
              f"  P4(event_count)={'OK' if p4 else 'FAIL'}"
              f"  P6(mirror_sanity)={'OK' if p6 else 'FAIL'}"
              f"  → {'PASS' if seed_ok else 'FAIL'}")

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
                "experiment": "phase10A3_closed_loop_slow_consolidation",
                "frozen_params": {
                    "w": W, "b_none": B_NONE, "b_L": B_L, "b_R": B_R,
                    "b_sim": B_SIM, "tau": TAU,
                    "total_steps": args.total_steps,
                    "warmup": warmup,
                    "decision_interval": args.decision_interval,
                    "pulse_duration": pulse_dur,
                    "epsilon": EPSILON,
                    "perturb_seed_offset": PERTURB_SEED_OFFSET,
                    "consolidation_tag_tau": CONSOLIDATION_TAG_TAU,
                    "consolidation_capture_threshold": CONSOLIDATION_CAPTURE_THRESHOLD,
                    "consolidation_slow_weight_max": CONSOLIDATION_SLOW_WEIGHT_MAX,
                    "9C_enabled": True,
                    "9D_enabled": True,
                },
                "summaries": json_sums,
                "fast_delta_reference": FAST_DELTA_EXACT_VS_PERTURBED,
                "n_hard_pass": n_hard_ok,
                "n_seeds": len(args.seeds),
            }, f, indent=2, ensure_ascii=False)
        print(f"  JSON: {args.summary_json}")

    return 0 if n_hard_ok == len(args.seeds) else 1


if __name__ == "__main__":
    sys.exit(main())
