"""Phase 10A.2B.1 — Perturbed Initial State Replay Smoke (Scheme E).

Tests whether a single t=0 activation perturbation can be amplified by
the 9C fast plasticity pipeline into measurable fast weight divergence.

Arms: closed_loop, exact_replay, perturbed_replay.
Perturbation: uniform [-0.02, +0.02] per unit, once at t=0, activations only.

Frozen from docs/phase10A2B1_perturbed_replay_smoke_design.md.
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


def _fast_weight_per_region(core):
    src_l, src_r, src_m = [], [], []
    si = core._source_indices
    wc = core._weight_cache
    positions = core._positions
    for k in range(len(si)):
        reg = _unit_region(positions[si[k]])
        if reg == "L": src_l.append(abs(wc[k]))
        elif reg == "R": src_r.append(abs(wc[k]))
        else: src_m.append(abs(wc[k]))
    return {
        "L": float(np.sum(src_l)) if src_l else 0.0,
        "R": float(np.sum(src_r)) if src_r else 0.0,
        "M": float(np.sum(src_m)) if src_m else 0.0,
    }


def _activation_divergence(acts_a, acts_b):
    """Mean L1 distance between two activation vectors."""
    return float(np.mean(np.abs(acts_a - acts_b)))


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


# ═══════════════════════════════════════════════════════════════════
# Arm runners
# ═══════════════════════════════════════════════════════════════════

def run_closed_loop(cfg, seed_env, seed_sched, decision_points, pulse_dur,
                    code_sha, config_sha):
    """Run closed_loop arm. Scheduler ONLINE, 9C ON."""
    core = LifeCore(cfg)
    sched_rng = np.random.default_rng(seed_sched)
    scheduler = Scheduler(sched_rng)
    env = Environment()
    phi_cache = _build_phi_cache(core)

    nan_hit = False
    event_log = []
    activations_at_warmup_end = None

    for s in range(TOTAL_STEPS):
        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)

        if not nan_hit and np.any(np.isnan(core._activations)):
            nan_hit = True

        if s == WARMUP:
            activations_at_warmup_end = core._activations.copy()

        if s in decision_points:
            act_l, act_r = _compute_region_activity(core)
            result = scheduler.propose(act_l, act_r)
            chosen = result["chosen"]

            row = {
                "run_id": f"phase10A2B1_closed_seed{seed_env}",
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
                "trace_mass_before": 0.0,
                "phi_mass": 0.0,
                "dW_l1": 0.0,
                "gate_value": 0.0,
                "fast_weight_snapshot_l1": 0.0,
            }

            if chosen != "none":
                phi = phi_cache[chosen]
                row["payload_hash"] = _hash_payload(phi)
                row["trace_mass_before"] = round(
                    float(np.sum(np.abs(core._event_trace))), 8)
                row["phi_mass"] = round(float(np.sum(np.abs(phi))), 8)

                stim = STIM_MAP.get(chosen)
                if stim is None:
                    env.add_event(StimulusEvent(
                        stimulus=L_STIM, start_step=s, duration_steps=pulse_dur))
                    env.add_event(StimulusEvent(
                        stimulus=R_STIM, start_step=s, duration_steps=pulse_dur))
                else:
                    env.add_event(StimulusEvent(
                        stimulus=stim, start_step=s, duration_steps=pulse_dur))

                ledger = core.apply_event_pair_phi(phi)
                if ledger:
                    row["dW_l1"] = round(ledger["dW_l1"], 10)
                    row["gate_value"] = round(ledger["gate"], 8)

            row["fast_weight_snapshot_l1"] = round(_fast_weight_l1(core), 8)
            event_log.append(row)

    final_fast_l1 = _fast_weight_l1(core)
    fast_per_region = _fast_weight_per_region(core)
    max_abs_w = float(np.max(np.abs(core._weight_cache))) if len(core._weight_cache) > 0 else 0.0

    return event_log, {
        "arm": "closed_loop",
        "seed_env": seed_env,
        "final_fast_weight_l1": round(final_fast_l1, 8),
        "fast_weight_per_region": fast_per_region,
        "max_abs_weight": round(max_abs_w, 8),
        "nan_hit": nan_hit,
        "activations_at_warmup_end": activations_at_warmup_end,
    }


def run_exact_replay(cfg, seed_env, event_trace, pulse_dur, code_sha, config_sha):
    """Run exact_replay arm. Scheduler DISABLED, no perturbation. 9C ON.

    Expected: bit-identical to closed_loop (mirror confirmation).
    """
    core = LifeCore(cfg)
    phi_cache = _build_phi_cache(core)
    env = Environment()

    nan_hit = False
    event_log = []
    replay_idx = 0
    n_expected = len(event_trace)
    hash_mismatches = 0
    activations_at_warmup_end = None

    for s in range(TOTAL_STEPS):
        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)

        if not nan_hit and np.any(np.isnan(core._activations)):
            nan_hit = True

        if s == WARMUP:
            activations_at_warmup_end = core._activations.copy()

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

            trace_mass_before = float(np.sum(np.abs(core._event_trace)))
            phi_mass = float(np.sum(np.abs(phi)))
            ledger = core.apply_event_pair_phi(phi)

            row = {
                "run_id": f"phase10A2B1_exact_seed{seed_env}",
                "arm": "exact_replay",
                "seed_env": seed_env,
                "code_sha": code_sha, "config_sha": config_sha,
                "t_decision": s,
                "chosen_event": chosen,
                "payload_hash": actual_hash,
                "expected_payload_hash": exp_hash,
                "hash_match": actual_hash == exp_hash,
                "applied_ok": True,
                "trace_mass_before": round(trace_mass_before, 8),
                "phi_mass": round(phi_mass, 8),
                "dW_l1": round(ledger["dW_l1"], 10) if ledger else 0.0,
                "gate_value": round(ledger["gate"], 8) if ledger else 0.0,
                "fast_weight_snapshot_l1": 0.0,
            }
            row["fast_weight_snapshot_l1"] = round(_fast_weight_l1(core), 8)
            event_log.append(row)
            replay_idx += 1

    final_fast_l1 = _fast_weight_l1(core)
    fast_per_region = _fast_weight_per_region(core)
    max_abs_w = float(np.max(np.abs(core._weight_cache))) if len(core._weight_cache) > 0 else 0.0

    return event_log, {
        "arm": "exact_replay",
        "seed_env": seed_env,
        "n_expected": n_expected,
        "n_replayed": replay_idx,
        "hash_mismatches": hash_mismatches,
        "final_fast_weight_l1": round(final_fast_l1, 8),
        "fast_weight_per_region": fast_per_region,
        "max_abs_weight": round(max_abs_w, 8),
        "nan_hit": nan_hit,
        "activations_at_warmup_end": activations_at_warmup_end,
    }


def run_perturbed_replay(cfg, seed_env, event_trace, pulse_dur, code_sha, config_sha):
    """Run perturbed_replay arm. Scheduler DISABLED. 9C ON.

    At t=0, before first step: activations += uniform[-ε, +ε], clip to [0,1].
    Then replay exact event log. This is the primary test arm.
    """
    core = LifeCore(cfg)
    phi_cache = _build_phi_cache(core)

    # ── Apply perturbation at t=0, before first step ──
    perturb_rng = np.random.default_rng(seed_env + PERTURB_SEED_OFFSET)
    eps_vec = perturb_rng.uniform(-EPSILON, EPSILON, size=core.unit_count)
    acts_before = core._activations.copy()
    core._activations += eps_vec
    np.clip(core._activations, 0.0, 1.0, out=core._activations)
    actual_eps = core._activations - acts_before

    perturb_l1 = float(np.sum(np.abs(actual_eps)))
    perturb_l2 = float(np.sqrt(np.sum(actual_eps ** 2)))
    perturb_max = float(np.max(np.abs(actual_eps)))

    env = Environment()
    nan_hit = False
    event_log = []
    replay_idx = 0
    n_expected = len(event_trace)
    hash_mismatches = 0
    activations_at_warmup_end = None

    for s in range(TOTAL_STEPS):
        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)

        if not nan_hit and np.any(np.isnan(core._activations)):
            nan_hit = True

        if s == WARMUP:
            activations_at_warmup_end = core._activations.copy()

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

            trace_mass_before = float(np.sum(np.abs(core._event_trace)))
            phi_mass = float(np.sum(np.abs(phi)))
            ledger = core.apply_event_pair_phi(phi)

            row = {
                "run_id": f"phase10A2B1_perturbed_seed{seed_env}",
                "arm": "perturbed_replay",
                "seed_env": seed_env,
                "code_sha": code_sha, "config_sha": config_sha,
                "t_decision": s,
                "chosen_event": chosen,
                "payload_hash": actual_hash,
                "expected_payload_hash": exp_hash,
                "hash_match": actual_hash == exp_hash,
                "applied_ok": True,
                "trace_mass_before": round(trace_mass_before, 8),
                "phi_mass": round(phi_mass, 8),
                "dW_l1": round(ledger["dW_l1"], 10) if ledger else 0.0,
                "gate_value": round(ledger["gate"], 8) if ledger else 0.0,
                "fast_weight_snapshot_l1": 0.0,
            }
            row["fast_weight_snapshot_l1"] = round(_fast_weight_l1(core), 8)
            event_log.append(row)
            replay_idx += 1

    final_fast_l1 = _fast_weight_l1(core)
    fast_per_region = _fast_weight_per_region(core)
    max_abs_w = float(np.max(np.abs(core._weight_cache))) if len(core._weight_cache) > 0 else 0.0

    return event_log, {
        "arm": "perturbed_replay",
        "seed_env": seed_env,
        "n_expected": n_expected,
        "n_replayed": replay_idx,
        "hash_mismatches": hash_mismatches,
        "perturb_norm_l1": round(perturb_l1, 10),
        "perturb_norm_l2": round(perturb_l2, 10),
        "perturb_max_abs": round(perturb_max, 10),
        "epsilon_frozen": EPSILON,
        "final_fast_weight_l1": round(final_fast_l1, 8),
        "fast_weight_per_region": fast_per_region,
        "max_abs_weight": round(max_abs_w, 8),
        "nan_hit": nan_hit,
        "activations_at_warmup_end": activations_at_warmup_end,
    }


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def main(argv=None):
    p = argparse.ArgumentParser(
        description="Phase 10A.2B.1 — Perturbed Initial State Replay Smoke")
    p.add_argument("--seeds", type=int, nargs="+", default=[42, 77])
    p.add_argument("--unit-count", type=int, default=300)
    p.add_argument("--total-steps", type=int, default=TOTAL_STEPS)
    p.add_argument("--decision-interval", type=int, default=DECISION_INTERVAL)
    p.add_argument("--estimate-only", action="store_true")
    p.add_argument("--dry-run-schedule", action="store_true")
    p.add_argument("--output-csv", type=str,
                   default="results/phase10A2B1_perturbed_replay.csv")
    p.add_argument("--events-csv", type=str,
                   default="results/phase10A2B1_perturbed_replay_events.csv")
    p.add_argument("--summary-json", type=str,
                   default="results/phase10A2B1_perturbed_replay_summary.json")
    args = p.parse_args(argv)

    warmup = WARMUP
    pulse_dur = PULSE_DURATION
    decision_points = list(range(warmup, args.total_steps, args.decision_interval))
    n_decisions = len(decision_points)

    print("Phase 10A.2B.1 — Perturbed Initial State Replay Smoke (Scheme E)")
    print(f"  seeds={args.seeds}  unit_count={args.unit_count}"
          f"  steps={args.total_steps}  interval={args.decision_interval}")
    print(f"  decision_points={n_decisions}")
    print(f"  scheduler θ: w={W} b_none={B_NONE} b_L={B_L} b_R={B_R}"
          f" b_sim={B_SIM} tau={TAU}")
    print(f"  perturbation: ε={EPSILON}  target=activations  timing=t=0 once"
          f"  seed_offset={PERTURB_SEED_OFFSET}")
    print(f"  9C ON  9D OFF")
    print()

    if args.dry_run_schedule:
        print(f"  Arms: closed_loop, exact_replay, perturbed_replay")
        print(f"  Decision points (first 5): {decision_points[:5]}...")
        print(f"  Decision points (last 5): ...{decision_points[-5:]}")
        print(f"  Expected per seed: closed ~1.5min, exact ~1.5min,"
              f" perturbed ~1.5min")
        print(f"  Total expected: ~4.5 min/seed × {len(args.seeds)} seeds"
              f" = ~{4.5 * len(args.seeds)} min")
        print()
        return 0

    code_sha = _git_sha()
    all_event_rows = []
    all_summaries = []

    for seed in args.seeds:
        print(f"── Seed {seed} ──")

        cfg_9c_on = AnivaConfig(
            unit_count=args.unit_count,
            seed=seed,
            event_pair_plasticity_enabled=True,
            event_pair_ledger_enabled=True,
        )
        assert cfg_9c_on.event_pair_plasticity_enabled
        assert not cfg_9c_on.consolidation_enabled

        config_sha = hashlib.sha256(
            json.dumps({k: v for k, v in cfg_9c_on.__dict__.items()
                        if not k.startswith("_")}, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]

        if args.estimate_only:
            print(f"  Estimating closed_loop...", end=" ", flush=True)
            t0 = time.time()
            el, s_info = run_closed_loop(
                cfg_9c_on, seed_env=seed, seed_sched=seed + 1000,
                decision_points=decision_points, pulse_dur=pulse_dur,
                code_sha=code_sha, config_sha=config_sha)
            wall = time.time() - t0
            n_events = sum(1 for d in el if d["chosen_event"] != "none")
            print(f"{wall:.0f}s  events={n_events}")
            print(f"    Estimated exact_replay: ~{wall:.0f}s"
                  f"  perturbed_replay: ~{wall:.0f}s")
            print(f"    Estimated total: ~{wall * 3:.0f}s per seed")
            continue

        # ── Arm 1: closed_loop ──
        print(f"  [1/3] closed_loop ...", end=" ", flush=True)
        t0 = time.time()
        el_closed, s_closed = run_closed_loop(
            cfg_9c_on, seed_env=seed, seed_sched=seed + 1000,
            decision_points=decision_points, pulse_dur=pulse_dur,
            code_sha=code_sha, config_sha=config_sha)
        wall = time.time() - t0

        n_events = sum(1 for d in el_closed if d["chosen_event"] != "none")
        none_count = sum(1 for d in el_closed if d["chosen_event"] == "none")
        none_rate = none_count / max(len(el_closed), 1)
        types_present = len(set(d["chosen_event"] for d in el_closed
                                if d["chosen_event"] != "none"))
        L_count = sum(1 for d in el_closed if d["chosen_event"] == "L")
        R_count = sum(1 for d in el_closed if d["chosen_event"] == "R")
        sim_count = sum(1 for d in el_closed if d["chosen_event"] == "simultaneous")

        print(f"{wall:.0f}s  events={n_events}  none_rate={none_rate:.2f}"
              f"  L={L_count} R={R_count} sim={sim_count}  types={types_present}")

        # Build event trace for replay
        event_trace = []
        for d in el_closed:
            if d["chosen_event"] != "none":
                event_trace.append((d["t_decision"], d["chosen_event"],
                                    d["payload_hash"]))
        trace_hash = _hash_trace(event_trace)

        s_closed.update({
            "event_count": n_events,
            "none_rate": round(none_rate, 4),
            "L_count": L_count,
            "R_count": R_count,
            "simultaneous_count": sim_count,
            "n_types": types_present,
            "trace_hash": trace_hash,
            "wall_time_s": round(wall, 1),
        })
        all_event_rows.extend(el_closed)
        all_summaries.append(s_closed)

        # ── Arm 2: exact_replay ──
        print(f"  [2/3] exact_replay ({n_events} events) ...", end=" ", flush=True)
        t0 = time.time()

        cfg_replay = AnivaConfig(
            unit_count=args.unit_count,
            seed=seed,
            event_pair_plasticity_enabled=True,
            event_pair_ledger_enabled=True,
        )

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
              f"  hash_mismatches={s_exact['hash_mismatches']}  [{status}]")

        # ── Arm 3: perturbed_replay ──
        print(f"  [3/3] perturbed_replay ({n_events} events, ε={EPSILON}) ...",
              end=" ", flush=True)
        t0 = time.time()

        cfg_pert = AnivaConfig(
            unit_count=args.unit_count,
            seed=seed,
            event_pair_plasticity_enabled=True,
            event_pair_ledger_enabled=True,
        )

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
              f"  hash_mismatches={s_pert['hash_mismatches']}"
              f"  perturb_l1={s_pert['perturb_norm_l1']:.4f}"
              f"  [{status_p}]")

    if args.estimate_only:
        return 0

    # ── Cross-arm comparison ──
    print()
    print("── Cross-Arm Comparison ──")
    print(f"  {'Seed':<6} {'Arm':<18} {'Fast_L1':>14} {'MaxW':>8}"
          f" {'NaN':>5} {'Events':>7} {'Perturb_L1':>12}")
    print(f"  {'-'*6} {'-'*18} {'-'*14} {'-'*8} {'-'*5} {'-'*7} {'-'*12}")
    for s in all_summaries:
        perturb_str = f"{s.get('perturb_norm_l1', 0):.6f}" if "perturb_norm_l1" in s else "N/A"
        events_str = str(s.get("event_count", s.get("n_replayed", "N/A")))
        print(f"  {s['seed_env']:<6} {s['arm']:<18}"
              f" {s['final_fast_weight_l1']:>14.8f}"
              f" {s['max_abs_weight']:>8.5f}"
              f" {'Y' if s['nan_hit'] else 'N':>5}"
              f" {events_str:>7}"
              f" {perturb_str:>12}")
    print()

    # ── Per-seed deltas ──
    print("── Fast Weight Deltas ──")
    for seed in args.seeds:
        seed_sums = [s for s in all_summaries if s["seed_env"] == seed]
        by_arm = {s["arm"]: s for s in seed_sums}
        cl = by_arm.get("closed_loop", {})
        ex = by_arm.get("exact_replay", {})
        pe = by_arm.get("perturbed_replay", {})

        cl_l1 = cl.get("final_fast_weight_l1", float("nan"))
        ex_l1 = ex.get("final_fast_weight_l1", float("nan"))
        pe_l1 = pe.get("final_fast_weight_l1", float("nan"))

        delta_ce = cl_l1 - ex_l1 if not (np.isnan(cl_l1) or np.isnan(ex_l1)) else float("nan")
        delta_cp = cl_l1 - pe_l1 if not (np.isnan(cl_l1) or np.isnan(pe_l1)) else float("nan")
        delta_ep = ex_l1 - pe_l1 if not (np.isnan(ex_l1) or np.isnan(pe_l1)) else float("nan")

        # Activation divergence at warmup end
        act_div_ce = float("nan")
        act_div_cp = float("nan")
        if (cl.get("activations_at_warmup_end") is not None
                and ex.get("activations_at_warmup_end") is not None):
            act_div_ce = _activation_divergence(
                cl["activations_at_warmup_end"], ex["activations_at_warmup_end"])
        if (cl.get("activations_at_warmup_end") is not None
                and pe.get("activations_at_warmup_end") is not None):
            act_div_cp = _activation_divergence(
                cl["activations_at_warmup_end"], pe["activations_at_warmup_end"])

        print(f"  Seed {seed}:")
        print(f"    closed_l1           = {cl_l1:.8f}")
        print(f"    exact_l1            = {ex_l1:.8f}")
        print(f"    perturbed_l1        = {pe_l1:.8f}")
        print(f"    Δ(closed-exact)     = {delta_ce:.8f}"
              f"  {'← MIRROR OK' if abs(delta_ce) < 1e-10 else '← PROTOCOL BUG?'}")
        print(f"    Δ(closed-perturbed) = {delta_cp:.8f}"
              f"  {'← CRACK?' if abs(delta_cp) > 1e-10 else '← STILL MIRROR'}")
        print(f"    Δ(exact-perturbed)  = {delta_ep:.8f}")
        print(f"    perturb_l1          = {pe.get('perturb_norm_l1', 'N/A')}")
        print(f"    act_div(closed,exact)_at_warmup_end"
              f"      = {act_div_ce:.8f}")
        print(f"    act_div(closed,perturbed)_at_warmup_end"
              f"      = {act_div_cp:.8f}")
    print()

    # ── Hard protocol ──
    n_hard_ok = 0
    for seed in args.seeds:
        seed_sums = [s for s in all_summaries if s["seed_env"] == seed]
        by_arm = {s["arm"]: s for s in seed_sums}

        p1 = not any(s["nan_hit"] for s in seed_sums)
        p2 = all(s["max_abs_weight"] < 10.0 for s in seed_sums)
        p3 = all(s.get("hash_mismatches", 0) == 0 for s in seed_sums
                 if s["arm"] != "closed_loop")
        cl_events = by_arm.get("closed_loop", {}).get("event_count", -1)
        ex_events = by_arm.get("exact_replay", {}).get("n_replayed", -1)
        pe_events = by_arm.get("perturbed_replay", {}).get("n_replayed", -1)
        p4 = (cl_events == ex_events == pe_events) and cl_events >= 0
        seed_ok = p1 and p2 and p3 and p4
        if seed_ok:
            n_hard_ok += 1

        print(f"  Seed {seed} hard protocol:"
              f"  P1(nan)={'OK' if p1 else 'FAIL'}"
              f"  P2(explosion)={'OK' if p2 else 'FAIL'}"
              f"  P3(replay_hash)={'OK' if p3 else 'FAIL'}"
              f"  P4(event_count)={'OK' if p4 else 'FAIL'}"
              f"  → {'PASS' if seed_ok else 'FAIL'}")

    print(f"\n  Hard pass: {n_hard_ok}/{len(args.seeds)}")
    print()

    # ── Save outputs ──
    if args.events_csv:
        _save_event_log(all_event_rows, args.events_csv)
        print(f"  Events CSV: {args.events_csv} ({len(all_event_rows)} rows)")

    if args.output_csv:
        if all_summaries:
            all_sf = []
            seen_sf = set()
            for s in all_summaries:
                for k in s:
                    if k not in seen_sf:
                        # Skip numpy arrays in CSV
                        if not isinstance(s[k], np.ndarray):
                            all_sf.append(k)
                            seen_sf.add(k)
            with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=all_sf, extrasaction="ignore")
                w.writeheader()
                w.writerows(all_summaries)
            print(f"  Summary CSV: {args.output_csv}")

    if args.summary_json:
        # Convert numpy arrays for JSON serialization
        json_summaries = []
        for s in all_summaries:
            js = {}
            for k, v in s.items():
                if isinstance(v, np.ndarray):
                    js[k] = v.tolist()
                elif isinstance(v, dict):
                    js[k] = {kk: vv for kk, vv in v.items()}
                else:
                    js[k] = v
            json_summaries.append(js)

        with open(args.summary_json, "w", encoding="utf-8") as f:
            json.dump({
                "experiment": "phase10A2B1_perturbed_replay_smoke",
                "frozen_params": {
                    "w": W, "b_none": B_NONE, "b_L": B_L,
                    "b_R": B_R, "b_sim": B_SIM, "tau": TAU,
                    "total_steps": args.total_steps,
                    "warmup": warmup,
                    "decision_interval": args.decision_interval,
                    "pulse_duration": pulse_dur,
                    "epsilon": EPSILON,
                    "perturb_seed_offset": PERTURB_SEED_OFFSET,
                    "perturbation_target": "activations only",
                    "9C_enabled": True,
                    "9D_enabled": False,
                },
                "summaries": json_summaries,
                "n_hard_pass": n_hard_ok,
                "n_seeds": len(args.seeds),
            }, f, indent=2, ensure_ascii=False)
        print(f"  JSON: {args.summary_json}")

    return 0 if n_hard_ok == len(args.seeds) else 1


if __name__ == "__main__":
    sys.exit(main())
