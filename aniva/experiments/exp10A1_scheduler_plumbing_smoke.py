"""Phase 10A.1 — Scheduler Plumbing Smoke.

Validates that a parameterized stochastic scheduler can produce varied,
non-degenerate event histories without cheating.

NO plasticity (9C). NO consolidation (9D). Event generation only.

Frozen parameters from docs/phase10A0_design_freeze.md.
"""

import argparse, csv, hashlib, json, sys, time
import numpy as np

from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.environment.environment import Stimulus, StimulusEvent, Environment

# ── Frozen from 10A.0 design freeze ──
L_STIM = Stimulus(position=(-0.5, 0.0, 0.0), intensity=0.02, radius=0.5)
R_STIM = Stimulus(position=(0.5, 0.0, 0.0), intensity=0.02, radius=0.5)
STIM_MAP = {"L": L_STIM, "R": R_STIM}

TOTAL_STEPS = 7500
WARMUP = 2000
DECISION_INTERVAL = 500
PULSE_DURATION = 80

# Scheduler θ (FROZEN — do not tune per run)
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


class Scheduler:
    """Parameterized stochastic scheduler. Fixed θ, no learning, no memory.

    Allowed inputs: activity_L, activity_R (mean activation per hemisphere).
    Disallowed: arm_label, event_count, weights, tags, future info.
    """

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
                "none": float(logit_none),
                "L": float(logit_L),
                "R": float(logit_R),
                "simultaneous": float(logit_sim),
            },
            "probs": {
                "none": float(probs[0]),
                "L": float(probs[1]),
                "R": float(probs[2]),
                "simultaneous": float(probs[3]),
            },
            "u_draw": u,
            "chosen": EVENT_SET[chosen_idx],
        }


def _compute_region_activity(core):
    acts = core._activations
    positions = core._positions
    l_vals = []
    r_vals = []
    for uid in range(len(acts)):
        reg = _unit_region(positions[uid])
        if reg == "L":
            l_vals.append(acts[uid])
        elif reg == "R":
            r_vals.append(acts[uid])
    act_l = float(np.mean(l_vals)) if l_vals else 0.0
    act_r = float(np.mean(r_vals)) if r_vals else 0.0
    return act_l, act_r


def run_scheduler_smoke(cfg, total_steps, warmup, decision_interval, pulse_dur,
                        seed_env, seed_sched):
    """Run one seed of 10A.1 scheduler plumbing smoke.

    Returns: (event_log_rows, summary_dict)
    """
    core = LifeCore(cfg)
    n_units = cfg.unit_count

    sched_rng = np.random.default_rng(seed_sched)
    scheduler = Scheduler(sched_rng)

    env = Environment()
    env_rng = np.random.default_rng(seed_env)

    phi_cache = {
        "L": np.array([L_STIM.influence_at(tuple(core._positions[uid]))
                       for uid in range(n_units)], dtype=np.float64),
        "R": np.array([R_STIM.influence_at(tuple(core._positions[uid]))
                       for uid in range(n_units)], dtype=np.float64),
    }
    phi_sim = phi_cache["L"] + phi_cache["R"]

    code_sha = _git_sha()
    config_sha = hashlib.sha256(
        json.dumps({k: v for k, v in cfg.__dict__.items()
                    if not k.startswith("_")}, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]

    nan_hit = False
    decision_points = list(range(warmup, total_steps, decision_interval))
    event_log = []
    active_events = {}  # t -> StimulusEvent for pulse tracking

    for s in range(total_steps):
        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)

        if not nan_hit:
            if np.any(np.isnan(core._activations)):
                nan_hit = True

        if s in decision_points:
            act_l, act_r = _compute_region_activity(core)
            result = scheduler.propose(act_l, act_r)

            row = {
                "run_id": f"phase10A1_seed{seed_env}",
                "arm": "closed_loop",
                "seed_env": seed_env,
                "seed_sched": seed_sched,
                "code_sha": code_sha,
                "config_sha": config_sha,
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
                "chosen_event": result["chosen"],
                "payload_hash": "",
                "applied_ok": True,
            }

            chosen = result["chosen"]
            if chosen != "none":
                if chosen == "simultaneous":
                    phi = phi_sim
                else:
                    phi = phi_cache[chosen]
                row["payload_hash"] = _hash_payload(phi)

                stim = STIM_MAP.get(chosen)
                if stim is None:
                    evt = StimulusEvent(
                        stimulus=L_STIM, start_step=s, duration_steps=pulse_dur)
                    env.add_event(evt)
                    evt2 = StimulusEvent(
                        stimulus=R_STIM, start_step=s, duration_steps=pulse_dur)
                    env.add_event(evt2)
                else:
                    evt = StimulusEvent(
                        stimulus=stim, start_step=s, duration_steps=pulse_dur)
                    env.add_event(evt)

            event_log.append(row)

    # Build summary
    decisions = event_log
    n_decisions = len(decisions)
    events = [d for d in decisions if d["chosen_event"] != "none"]
    none_events = [d for d in decisions if d["chosen_event"] == "none"]
    n_events = len(events)
    n_none = len(none_events)
    none_rate = n_none / max(n_decisions, 1)

    type_counts = {"none": 0, "L": 0, "R": 0, "simultaneous": 0}
    for d in decisions:
        type_counts[d["chosen_event"]] += 1

    non_none_types = {k: v for k, v in type_counts.items()
                      if k != "none" and v > 0}
    n_unique_types = len(non_none_types)

    event_times = [d["t_decision"] for d in events]
    iei_list = []
    for i in range(1, len(event_times)):
        iei_list.append(event_times[i] - event_times[i - 1])
    iei_mean = float(np.mean(iei_list)) if iei_list else 0.0
    iei_var = float(np.var(iei_list)) if iei_list else 0.0

    applied_ok_all = all(d["applied_ok"] for d in decisions)

    # Pass/fail per design freeze
    p1 = not nan_hit
    p2 = all(
        d.get("run_id") and d.get("t_decision") is not None
        and d.get("obs_hash") and d.get("chosen_event") is not None
        for d in decisions
    )
    # P3/P4 checked by protocol tests (separate)
    b1 = n_events > 0
    b2 = 0.30 < none_rate < 0.90
    b3 = n_unique_types >= 2

    all_soft_pass = b1 and b2 and b3
    all_hard_pass = p1 and p2

    summary = {
        "experiment": "phase10A1_scheduler_plumbing_smoke",
        "seed_env": seed_env,
        "seed_sched": seed_sched,
        "code_sha": code_sha,
        "config_sha": config_sha,
        "n_decisions": n_decisions,
        "event_count": n_events,
        "none_count": type_counts["none"],
        "L_count": type_counts["L"],
        "R_count": type_counts["R"],
        "simultaneous_count": type_counts["simultaneous"],
        "none_rate": round(none_rate, 4),
        "n_unique_event_types": n_unique_types,
        "inter_event_interval_mean": round(iei_mean, 2),
        "inter_event_interval_var": round(iei_var, 2),
        "nan_count": 1 if nan_hit else 0,
        "applied_ok_all": applied_ok_all,
        "hard_pass": all_hard_pass,
        "soft_pass": all_soft_pass,
        "p1_no_nan": p1,
        "p2_fields_present": p2,
        "b1_events_gt_0": b1,
        "b2_none_rate_bounded": b2,
        "b3_type_diversity": b3,
    }

    return event_log, summary


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
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Phase 10A.1 — Scheduler Plumbing Smoke")
    p.add_argument("--seeds", type=int, nargs="+", default=[42, 77])
    p.add_argument("--unit-count", type=int, default=300)
    p.add_argument("--total-steps", type=int, default=TOTAL_STEPS)
    p.add_argument("--decision-interval", type=int, default=DECISION_INTERVAL)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--output-events-csv", type=str,
                   default="results/phase10A1_scheduler_events.csv")
    p.add_argument("--output-summary-csv", type=str,
                   default="results/phase10A1_scheduler_summary.csv")
    p.add_argument("--summary-json", type=str,
                   default="results/phase10A1_scheduler_summary.json")
    args = p.parse_args(argv)

    warmup = WARMUP
    pulse_dur = PULSE_DURATION

    print(f"Phase 10A.1 — Scheduler Plumbing Smoke")
    print(f"  seeds={args.seeds}  unit_count={args.unit_count}"
          f"  steps={args.total_steps}  interval={args.decision_interval}")
    print(f"  scheduler θ: w={W} b_none={B_NONE} b_L={B_L} b_R={B_R}"
          f" b_sim={B_SIM} tau={TAU}")
    print(f"  plasticity=OFF  consolidation=OFF")
    print()

    if args.dry_run:
        n = (args.total_steps - warmup) // args.decision_interval
        print(f"  Decision points: {n} (from step {warmup}"
              f" to {args.total_steps} every {args.decision_interval})")
        print(f"  Scheduler inputs: activity_L, activity_R only")
        print(f"  Event set: none, L, R, simultaneous")
        print()
        return 0

    all_event_rows = []
    all_summaries = []

    for seed in args.seeds:
        print(f"  [seed {seed}] ...", end=" ", flush=True)
        t0 = time.time()

        cfg = AnivaConfig(
            unit_count=args.unit_count,
            seed=seed,
        )
        # Explicitly confirm all plasticity/consolidation are OFF (defaults)
        assert not cfg.event_pair_plasticity_enabled
        assert not cfg.consolidation_enabled

        event_rows, summary = run_scheduler_smoke(
            cfg, args.total_steps, warmup, args.decision_interval,
            pulse_dur, seed_env=seed, seed_sched=seed + 1000)

        wall = time.time() - t0
        summary["wall_time_s"] = round(wall, 1)

        status = "PASS" if summary["hard_pass"] and summary["soft_pass"] else "FAIL"
        print(f"{wall:.0f}s  events={summary['event_count']}"
              f"  none_rate={summary['none_rate']:.2f}"
              f"  types={summary['n_unique_event_types']}"
              f"  [{status}]")

        all_event_rows.extend(event_rows)
        all_summaries.append(summary)

    print()

    # Print per-seed summary table
    print(f"  {'Seed':<6} {'Decisions':>10} {'Events':>8} {'none%':>8}"
          f" {'L':>5} {'R':>5} {'sim':>5} {'Types':>6} {'Hard':>6} {'Soft':>6}")
    print(f"  {'-'*6} {'-'*10} {'-'*8} {'-'*8} {'-'*5} {'-'*5}"
          f" {'-'*5} {'-'*6} {'-'*6} {'-'*6}")
    for s in all_summaries:
        print(f"  {s['seed_env']:<6} {s['n_decisions']:>10} {s['event_count']:>8}"
              f" {s['none_rate']:>8.2f} {s['L_count']:>5} {s['R_count']:>5}"
              f" {s['simultaneous_count']:>5} {s['n_unique_event_types']:>6}"
              f" {'OK' if s['hard_pass'] else 'FAIL':>6}"
              f" {'OK' if s['soft_pass'] else 'FAIL':>6}")
    print()

    # Cross-seed check
    if len(all_summaries) >= 2:
        traces = []
        for rows, s in zip(
            [all_event_rows[:len(all_event_rows)//len(args.seeds)],
             all_event_rows[len(all_event_rows)//len(args.seeds):]],
            all_summaries
        ):
            # simpler: reconstruct per-seed
            pass

    n_hard_ok = sum(1 for s in all_summaries if s["hard_pass"])
    n_soft_ok = sum(1 for s in all_summaries if s["soft_pass"])
    print(f"  Hard pass: {n_hard_ok}/{len(args.seeds)}")
    print(f"  Soft pass: {n_soft_ok}/{len(args.seeds)}")
    print()

    # Save outputs
    if args.output_events_csv:
        _save_event_log(all_event_rows, args.output_events_csv)
        print(f"  Events CSV: {args.output_events_csv}"
              f" ({len(all_event_rows)} rows)")

    if args.output_summary_csv:
        with open(args.output_summary_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(all_summaries[0].keys()))
            w.writeheader()
            w.writerows(all_summaries)
        print(f"  Summary CSV: {args.output_summary_csv}")

    if args.summary_json:
        with open(args.summary_json, "w", encoding="utf-8") as f:
            json.dump({
                "experiment": "phase10A1_scheduler_plumbing_smoke",
                "frozen_params": {
                    "w": W, "b_none": B_NONE, "b_L": B_L,
                    "b_R": B_R, "b_sim": B_SIM, "tau": TAU,
                    "total_steps": args.total_steps,
                    "warmup": warmup,
                    "decision_interval": args.decision_interval,
                    "pulse_duration": pulse_dur,
                },
                "summaries": all_summaries,
                "n_hard_pass": n_hard_ok,
                "n_soft_pass": n_soft_ok,
                "n_seeds": len(args.seeds),
            }, f, indent=2, ensure_ascii=False)
        print(f"  JSON: {args.summary_json}")

    return 0 if (n_hard_ok == len(args.seeds)) else 1


if __name__ == "__main__":
    sys.exit(main())
