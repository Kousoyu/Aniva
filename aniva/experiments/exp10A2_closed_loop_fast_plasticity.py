"""Phase 10A.2 — Closed-Loop Fast Plasticity (2-seed pilot).

First time opening 9C event-pair plasticity in the Phase 10 pipeline.
9D consolidation OFF. Validates that closed-loop event history changes
fast weight trajectory, distinguishable from matched replay and random
controls.

Frozen parameters from 10A.1B (decision_interval=250) and 10A.0 (θ).
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
DECISION_INTERVAL = 250  # 10A.1B calibrated
PULSE_DURATION = 80

# Scheduler θ (FROZEN)
W = 5.0
B_NONE = +1.0
B_L = -1.5
B_R = -1.5
B_SIM = -3.0
TAU = 1.0

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


# ═══════════════════════════════════════════════════════════════════
# Arm runners
# ═══════════════════════════════════════════════════════════════════

def run_closed_loop(cfg, seed_env, seed_sched, decision_points, pulse_dur,
                    code_sha, config_sha):
    """Run closed_loop arm. Scheduler ONLINE, 9C ON."""
    core = LifeCore(cfg)
    n_units = cfg.unit_count

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
                "run_id": f"phase10A2_closed_seed{seed_env}",
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
    }


def run_matched_replay(cfg, seed_env, event_trace, pulse_dur, code_sha, config_sha):
    """Run matched_open_loop_replay arm. Scheduler DISABLED, 9C ON.

    event_trace: list of (t_decision, chosen_event, payload_hash).
    """
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

            trace_mass_before = float(np.sum(np.abs(core._event_trace)))
            phi_mass = float(np.sum(np.abs(phi)))

            ledger = core.apply_event_pair_phi(phi)

            row = {
                "run_id": f"phase10A2_replay_seed{seed_env}",
                "arm": "matched_open_loop_replay",
                "seed_env": seed_env,
                "source_seed": seed_env,  # same seed, paired replay
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
        "arm": "matched_open_loop_replay",
        "seed_env": seed_env,
        "n_expected": n_expected,
        "n_replayed": replay_idx,
        "hash_mismatches": hash_mismatches,
        "final_fast_weight_l1": round(final_fast_l1, 8),
        "fast_weight_per_region": fast_per_region,
        "max_abs_weight": round(max_abs_w, 8),
        "nan_hit": nan_hit,
    }


def run_random_uniform(cfg, seed_env, n_events, pulse_dur, code_sha, config_sha):
    """Run random_uniform_control arm. Scheduler DISABLED, 9C ON.

    Generates n_events with uniform random timing (in [warmup, total_steps))
    and random L/R type (equal probability). No simultaneous events.
    """
    core = LifeCore(cfg)
    phi_cache = _build_phi_cache(core)
    env = Environment()
    control_rng = np.random.default_rng(seed_env + 2000)

    # Generate event schedule
    available = list(range(WARMUP, TOTAL_STEPS))
    times = sorted(control_rng.choice(available, size=min(n_events, len(available)),
                                      replace=False))
    types = control_rng.choice(["L", "R"], size=n_events)

    schedule = {t: [] for t in times}
    for t, typ in zip(times, types):
        schedule[t].append(typ)

    nan_hit = False
    event_log = []
    event_idx = 0

    for s in range(TOTAL_STEPS):
        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)

        if not nan_hit and np.any(np.isnan(core._activations)):
            nan_hit = True

        if s in schedule:
            for typ in schedule[s]:
                phi = phi_cache[typ]
                actual_hash = _hash_payload(phi)

                stim = STIM_MAP[typ]
                env.add_event(StimulusEvent(
                    stimulus=stim, start_step=s, duration_steps=pulse_dur))

                trace_mass_before = float(np.sum(np.abs(core._event_trace)))
                phi_mass = float(np.sum(np.abs(phi)))

                ledger = core.apply_event_pair_phi(phi)

                row = {
                    "run_id": f"phase10A2_random_seed{seed_env}",
                    "arm": "random_uniform_control",
                    "seed_env": seed_env,
                    "code_sha": code_sha, "config_sha": config_sha,
                    "t_decision": s,
                    "chosen_event": typ,
                    "payload_hash": actual_hash,
                    "applied_ok": True,
                    "trace_mass_before": round(trace_mass_before, 8),
                    "phi_mass": round(phi_mass, 8),
                    "dW_l1": round(ledger["dW_l1"], 10) if ledger else 0.0,
                    "gate_value": round(ledger["gate"], 8) if ledger else 0.0,
                    "fast_weight_snapshot_l1": 0.0,
                }
                row["fast_weight_snapshot_l1"] = round(_fast_weight_l1(core), 8)
                event_log.append(row)
                event_idx += 1

    final_fast_l1 = _fast_weight_l1(core)
    fast_per_region = _fast_weight_per_region(core)
    max_abs_w = float(np.max(np.abs(core._weight_cache))) if len(core._weight_cache) > 0 else 0.0

    return event_log, {
        "arm": "random_uniform_control",
        "seed_env": seed_env,
        "n_scheduled": n_events,
        "n_applied": event_idx,
        "final_fast_weight_l1": round(final_fast_l1, 8),
        "fast_weight_per_region": fast_per_region,
        "max_abs_weight": round(max_abs_w, 8),
        "nan_hit": nan_hit,
    }


def run_no_event(cfg, seed_env, code_sha, config_sha):
    """Run no_event_control arm. No events, no scheduler. 9C trace decays only."""
    core = LifeCore(cfg)
    env = Environment()

    nan_hit = False

    for s in range(TOTAL_STEPS):
        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)

        if not nan_hit and np.any(np.isnan(core._activations)):
            nan_hit = True

    final_fast_l1 = _fast_weight_l1(core)
    fast_per_region = _fast_weight_per_region(core)
    max_abs_w = float(np.max(np.abs(core._weight_cache))) if len(core._weight_cache) > 0 else 0.0

    return [], {
        "arm": "no_event_control",
        "seed_env": seed_env,
        "final_fast_weight_l1": round(final_fast_l1, 8),
        "fast_weight_per_region": fast_per_region,
        "max_abs_weight": round(max_abs_w, 8),
        "nan_hit": nan_hit,
    }


# ═══════════════════════════════════════════════════════════════════
# Summary + output
# ═══════════════════════════════════════════════════════════════════

def _build_summaries(all_arm_results, code_sha):
    """Build per-arm summaries and cross-arm comparisons."""
    summaries = []
    for res in all_arm_results:
        summaries.append(res)

    # cross-arm comparisons per seed
    comparisons = []
    for seed in sorted(set(r["seed_env"] for r in all_arm_results)):
        seed_results = [r for r in all_arm_results if r["seed_env"] == seed]
        by_arm = {r["arm"]: r for r in seed_results}

        comp = {"seed_env": seed}
        cl = by_arm.get("closed_loop")
        rp = by_arm.get("matched_open_loop_replay")
        rd = by_arm.get("random_uniform_control")
        ne = by_arm.get("no_event_control")

        if cl:
            comp["closed_fast_l1"] = cl["final_fast_weight_l1"]
            comp["closed_nan"] = cl["nan_hit"]
        if rp:
            comp["replay_fast_l1"] = rp["final_fast_weight_l1"]
            comp["replay_hash_mismatches"] = rp["hash_mismatches"]
            comp["replay_nan"] = rp["nan_hit"]
        if rd:
            comp["random_fast_l1"] = rd["final_fast_weight_l1"]
            comp["random_nan"] = rd["nan_hit"]
        if ne:
            comp["no_event_fast_l1"] = ne["final_fast_weight_l1"]
            comp["no_event_nan"] = ne["nan_hit"]

        if cl and rp:
            comp["closed_vs_replay_delta"] = round(
                cl["final_fast_weight_l1"] - rp["final_fast_weight_l1"], 8)
        if cl and rd:
            comp["closed_vs_random_delta"] = round(
                cl["final_fast_weight_l1"] - rd["final_fast_weight_l1"], 8)
        if cl and ne:
            comp["closed_vs_no_event_delta"] = round(
                cl["final_fast_weight_l1"] - ne["final_fast_weight_l1"], 8)

        comparisons.append(comp)

    return summaries, comparisons


def _save_event_log(rows, path):
    if not rows:
        return
    # Collect all field names across all arms (schemas differ)
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
        description="Phase 10A.2 — Closed-Loop Fast Plasticity (2-seed pilot)")
    p.add_argument("--seeds", type=int, nargs="+", default=[42, 77])
    p.add_argument("--unit-count", type=int, default=300)
    p.add_argument("--total-steps", type=int, default=TOTAL_STEPS)
    p.add_argument("--decision-interval", type=int, default=DECISION_INTERVAL)
    p.add_argument("--estimate-only", action="store_true",
                   help="Print estimated runtime and event counts, do not run")
    p.add_argument("--dry-run-schedule", action="store_true",
                   help="Print decision points and arm plan, do not run")
    p.add_argument("--skip-random", action="store_true")
    p.add_argument("--skip-no-event", action="store_true")
    p.add_argument("--output-csv", type=str,
                   default="results/phase10A2_summary.csv")
    p.add_argument("--events-csv", type=str,
                   default="results/phase10A2_events.csv")
    p.add_argument("--summary-json", type=str,
                   default="results/phase10A2_summary.json")
    args = p.parse_args(argv)

    warmup = WARMUP
    pulse_dur = PULSE_DURATION
    decision_points = list(range(warmup, args.total_steps, args.decision_interval))
    n_decisions = len(decision_points)

    print("Phase 10A.2 — Closed-Loop Fast Plasticity (2-seed pilot)")
    print(f"  seeds={args.seeds}  unit_count={args.unit_count}"
          f"  steps={args.total_steps}  interval={args.decision_interval}")
    print(f"  decision_points={n_decisions}")
    print(f"  scheduler θ: w={W} b_none={B_NONE} b_L={B_L} b_R={B_R}"
          f" b_sim={B_SIM} tau={TAU}")
    print(f"  9C event-pair plasticity: ON")
    print(f"  9D consolidation: OFF")
    print()

    if args.dry_run_schedule:
        arms = ["closed_loop", "matched_open_loop_replay"]
        if not args.skip_random:
            arms.append("random_uniform_control")
        if not args.skip_no_event:
            arms.append("no_event_control")
        print(f"  Arms: {', '.join(arms)}")
        print(f"  Decision points (first 5): {decision_points[:5]}...")
        print(f"  Decision points (last 5): ...{decision_points[-5:]}")
        print(f"  Expected runtime per seed: closed ~3min, replay ~3min,"
              f" random ~2min, no_event ~2min")
        print(f"  Total expected: ~10 min/seed × {len(args.seeds)} seeds"
              f" = ~{10 * len(args.seeds)} min")
        print()
        return 0

    # First pass: run closed_loop for all seeds to get event traces
    code_sha = _git_sha()
    all_event_rows = []
    all_summaries = []
    all_comparisons = []

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
            # Quick closed_loop run to get event count
            print(f"  Estimating...", end=" ", flush=True)
            t0 = time.time()
            el, s_info = run_closed_loop(
                cfg_9c_on, seed_env=seed, seed_sched=seed + 1000,
                decision_points=decision_points, pulse_dur=pulse_dur,
                code_sha=code_sha, config_sha=config_sha)
            wall = time.time() - t0
            n_events = sum(1 for d in el if d["chosen_event"] != "none")
            print(f"{wall:.0f}s  events={n_events}")
            print(f"    Estimated replay: ~{wall:.0f}s"
                  f"  random: ~{wall * 0.7:.0f}s"
                  f"  no_event: ~{wall * 0.5:.0f}s")
            print(f"    Estimated total per seed: ~{wall * 3.2:.0f}s")
            continue

        # ── Arm 1: closed_loop ──
        print(f"  [1/4] closed_loop ...", end=" ", flush=True)
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
        print(f"{wall:.0f}s  events={n_events}  none_rate={none_rate:.2f}"
              f"  types={types_present}")

        # Build event trace for replay
        event_trace = []
        for d in el_closed:
            if d["chosen_event"] != "none":
                event_trace.append((d["t_decision"], d["chosen_event"],
                                    d["payload_hash"]))
        trace_hash = _hash_trace(event_trace)

        s_closed["event_count"] = n_events
        s_closed["none_rate"] = round(none_rate, 4)
        s_closed["n_types"] = types_present
        s_closed["trace_hash"] = trace_hash
        s_closed["wall_time_s"] = round(wall, 1)
        all_event_rows.extend(el_closed)
        all_summaries.append(s_closed)

        # ── Arm 2: matched_open_loop_replay ──
        print(f"  [2/4] matched_replay ({n_events} events) ...", end=" ", flush=True)
        t0 = time.time()

        cfg_replay = AnivaConfig(
            unit_count=args.unit_count,
            seed=seed,
            event_pair_plasticity_enabled=True,
            event_pair_ledger_enabled=True,
        )

        el_replay, s_replay = run_matched_replay(
            cfg_replay, seed_env=seed, event_trace=event_trace,
            pulse_dur=pulse_dur, code_sha=code_sha, config_sha=config_sha)
        wall = time.time() - t0

        s_replay["trace_hash"] = trace_hash
        s_replay["wall_time_s"] = round(wall, 1)
        s_replay["replay_exact"] = (s_replay["hash_mismatches"] == 0
                                     and s_replay["n_replayed"] == s_replay["n_expected"])
        all_event_rows.extend(el_replay)
        all_summaries.append(s_replay)

        status = "EXACT" if s_replay["replay_exact"] else "MISMATCH"
        print(f"{wall:.0f}s  replayed={s_replay['n_replayed']}"
              f"  hash_mismatches={s_replay['hash_mismatches']}  [{status}]")

        # ── Arm 3: random_uniform_control ──
        if not args.skip_random:
            print(f"  [3/4] random_uniform ({n_events} events) ...",
                  end=" ", flush=True)
            t0 = time.time()

            cfg_random = AnivaConfig(
                unit_count=args.unit_count,
                seed=seed,
                event_pair_plasticity_enabled=True,
                event_pair_ledger_enabled=True,
            )

            el_random, s_random = run_random_uniform(
                cfg_random, seed_env=seed, n_events=n_events,
                pulse_dur=pulse_dur, code_sha=code_sha, config_sha=config_sha)
            wall = time.time() - t0

            s_random["wall_time_s"] = round(wall, 1)
            all_event_rows.extend(el_random)
            all_summaries.append(s_random)

            print(f"{wall:.0f}s  applied={s_random['n_applied']}")

        # ── Arm 4: no_event_control ──
        if not args.skip_no_event:
            print(f"  [4/4] no_event_control ...", end=" ", flush=True)
            t0 = time.time()

            cfg_no_event = AnivaConfig(
                unit_count=args.unit_count,
                seed=seed,
                event_pair_plasticity_enabled=True,  # trace still decays
            )

            _, s_no_event = run_no_event(
                cfg_no_event, seed_env=seed,
                code_sha=code_sha, config_sha=config_sha)
            wall = time.time() - t0

            s_no_event["wall_time_s"] = round(wall, 1)
            all_summaries.append(s_no_event)

            print(f"{wall:.0f}s  fast_l1={s_no_event['final_fast_weight_l1']}")

    if args.estimate_only:
        return 0

    # ── Cross-arm comparisons ──
    _, comparisons = _build_summaries(all_summaries, code_sha)
    all_comparisons.extend(comparisons)

    print()
    print("── Cross-Arm Comparison ──")
    print(f"  {'Seed':<6} {'Closed_L1':>12} {'Replay_L1':>12}"
          f" {'Random_L1':>12} {'NoEvent_L1':>12}"
          f" {'ΔReplay':>10} {'ΔRandom':>10} {'ΔNoEvent':>10}")
    print(f"  {'-'*6} {'-'*12} {'-'*12} {'-'*12} {'-'*12}"
          f" {'-'*10} {'-'*10} {'-'*10}")
    for c in comparisons:
        print(f"  {c['seed_env']:<6}"
              f" {c.get('closed_fast_l1', 'N/A'):>12}"
              f" {c.get('replay_fast_l1', 'N/A'):>12}"
              f" {c.get('random_fast_l1', 'N/A'):>12}"
              f" {c.get('no_event_fast_l1', 'N/A'):>12}"
              f" {c.get('closed_vs_replay_delta', 'N/A'):>10}"
              f" {c.get('closed_vs_random_delta', 'N/A'):>10}"
              f" {c.get('closed_vs_no_event_delta', 'N/A'):>10}")
    print()

    # Save outputs
    if args.events_csv:
        _save_event_log(all_event_rows, args.events_csv)
        print(f"  Events CSV: {args.events_csv} ({len(all_event_rows)} rows)")

    if args.output_csv:
        if all_summaries:
            # Collect all field names across arms (schemas differ)
            all_sf = []
            seen_sf = set()
            for s in all_summaries:
                for k in s:
                    if k not in seen_sf:
                        all_sf.append(k)
                        seen_sf.add(k)
            with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=all_sf, extrasaction="ignore")
                w.writeheader()
                w.writerows(all_summaries)
            print(f"  Summary CSV: {args.output_csv}")

    if args.summary_json:
        with open(args.summary_json, "w", encoding="utf-8") as f:
            json.dump({
                "experiment": "phase10A2_closed_loop_fast_plasticity",
                "frozen_params": {
                    "w": W, "b_none": B_NONE, "b_L": B_L,
                    "b_R": B_R, "b_sim": B_SIM, "tau": TAU,
                    "total_steps": args.total_steps,
                    "warmup": warmup,
                    "decision_interval": args.decision_interval,
                    "pulse_duration": pulse_dur,
                    "9C_enabled": True,
                    "9D_enabled": False,
                },
                "summaries": all_summaries,
                "comparisons": all_comparisons,
            }, f, indent=2, ensure_ascii=False)
        print(f"  JSON: {args.summary_json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
