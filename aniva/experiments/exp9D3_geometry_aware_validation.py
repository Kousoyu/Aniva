"""Phase 9D.3 — Geometry-Aware Consolidation Validation.

Validates whether repeated ordered event histories produce directional slow
structural sediment ABOVE the shared geometry baseline.

geometry_baseline_DI = simultaneous combined-phi raw_projection_DI (shared global).
corrected_slow_DI = slow_DI - geometry_baseline_DI.

6 arms: L_then_R_repeated, R_then_L_repeated, L_then_R_single,
        R_then_L_single, simultaneous_combined, no_event.

Success: ordered arms exceed geometry baseline with correct directional sign.
"""

import argparse, csv, json, sys, time
import numpy as np

from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.environment.environment import Stimulus, StimulusEvent, Environment

L_STIM = Stimulus(position=(-0.5, 0.0, 0.0), intensity=0.02, radius=0.5)
R_STIM = Stimulus(position=(0.5, 0.0, 0.0), intensity=0.02, radius=0.5)
STIM_MAP = {"L": L_STIM, "R": R_STIM}

PULSE_DURATION = 80
WARMUP = 2000
PAIR_GAP = 500
PAIR_INTERVAL = 1500
TOTAL_STEPS = 7500
N_PAIRS_REPEATED = 3
EPS = 1e-12


def _unit_region(pos):
    x = pos[0]
    if x < -0.1: return "L"
    elif x > 0.1: return "R"
    return "M"


def _make_schedule(order, warmup, gap, pulse_dur, pair_interval, n_pairs):
    events = []
    first, second = ("L", "R") if order == "L_then_R" else ("R", "L")
    for i in range(n_pairs):
        base = warmup + i * pair_interval
        events.append((base, first, pulse_dur))
        events.append((base + gap, second, pulse_dur))
    return sorted(events, key=lambda x: x[0])


def _make_schedule_simultaneous(warmup, pulse_dur, pair_interval, n_pairs):
    events = []
    for i in range(n_pairs):
        base = warmup + i * pair_interval
        events.append((base, "L", pulse_dur))
        events.append((base, "R", pulse_dur))
    return sorted(events, key=lambda x: x[0])


def _event_starts_map(schedule):
    m = {}
    for t, side, _dur in schedule:
        m.setdefault(t, []).append(side)
    return m


def _l1_mask(arr, mask):
    return float(np.sum(np.abs(arr[mask])))


def compute_geometry_baseline(cfg):
    """Compute shared geometry_baseline_DI from simultaneous combined-phi.

    Offline computation — creates a LifeCore, simulates trace accumulation
    only (no step, no plasticity), and computes raw eligibility DI at the
    final event pair.
    """
    core = LifeCore(cfg)
    n_units = cfg.unit_count
    src_idx = core._source_indices
    tgt_idx = core._target_indices
    positions = core._positions

    src_regions = np.array([_unit_region(core.units[c.source_id].position)
                            for c in core.connections])
    tgt_regions = np.array([_unit_region(core.units[c.target_id].position)
                            for c in core.connections])
    is_LR = (src_regions == "L") & (tgt_regions == "R")
    is_RL = (src_regions == "R") & (tgt_regions == "L")

    phi_L = np.array([L_STIM.influence_at(tuple(positions[uid]))
                       for uid in range(n_units)], dtype=np.float64)
    phi_R = np.array([R_STIM.influence_at(tuple(positions[uid]))
                       for uid in range(n_units)], dtype=np.float64)
    combined = phi_L + phi_R

    schedule = _make_schedule_simultaneous(WARMUP, PULSE_DURATION, PAIR_INTERVAL, N_PAIRS_REPEATED)
    event_starts = sorted(set(t for t, _, _ in schedule))

    trace = np.zeros(n_units, dtype=np.float64)
    n_pairs_done = 0
    for step in event_starts:
        if n_pairs_done > 0:
            # trace now contains past combined phis
            pass
        trace += combined
        n_pairs_done += 1

    # Final event pair: raw eligibility = trace_before_last[src] × phi_final[tgt]
    # trace now has all 3 combined phis; we use the trace before last addition
    trace_before_last = trace - combined
    trace_mass = float(np.sum(np.abs(trace_before_last)))
    raw = trace_before_last[src_idx] * combined[tgt_idx]

    raw_LR_l1 = _l1_mask(raw, is_LR)
    raw_RL_l1 = _l1_mask(raw, is_RL)
    raw_DI = (raw_LR_l1 - raw_RL_l1) / (raw_LR_l1 + raw_RL_l1 + EPS)
    raw_total_l1 = float(np.sum(np.abs(raw)))

    return {
        "geometry_baseline_DI": raw_DI,
        "raw_LR_l1": raw_LR_l1,
        "raw_RL_l1": raw_RL_l1,
        "raw_total_l1": raw_total_l1,
        "trace_mass_before_final": trace_mass,
        "phi_mass_combined": float(np.sum(np.abs(combined))),
        "n_pairs_accumulated": n_pairs_done - 1,  # pairs contributing to trace
    }


def run_arm(cfg, total_steps, schedule, arm_label):
    """Run one arm and extract directional consolidation metrics.

    Adapted from 9D.2 run_arm. Uses the same step/event/consolidation flow.
    """
    core = LifeCore(cfg)
    n_units = cfg.unit_count

    src_regions = np.array([_unit_region(core.units[c.source_id].position)
                            for c in core.connections])
    tgt_regions = np.array([_unit_region(core.units[c.target_id].position)
                            for c in core.connections])
    is_LR = (src_regions == "L") & (tgt_regions == "R")
    is_RL = (src_regions == "R") & (tgt_regions == "L")

    env_events = []
    for t, side, dur in schedule:
        env_events.append(StimulusEvent(
            stimulus=STIM_MAP[side], start_step=t, duration_steps=dur))
    env = Environment()
    for ev in env_events:
        env.add_event(ev)

    event_starts = _event_starts_map(schedule)
    phi_cache = {
        "L": np.array([L_STIM.influence_at(tuple(core._positions[uid]))
                        for uid in range(n_units)], dtype=np.float64),
        "R": np.array([R_STIM.influence_at(tuple(core._positions[uid]))
                        for uid in range(n_units)], dtype=np.float64),
    }

    nan_hit = False
    n_updates = 0

    for s in range(total_steps):
        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)

        if not nan_hit:
            if (np.any(np.isnan(core._tag_cache))
                or np.any(np.isnan(core._slow_weight_cache))
                or np.any(np.isnan(core._weight_cache))):
                nan_hit = True

        if s in event_starts:
            sides = event_starts[s]
            phi = np.zeros(n_units, dtype=np.float64)
            for side in sides:
                phi += phi_cache[side]
            result = core.apply_event_pair_phi(phi)
            if result is not None:
                n_updates += 1

    slow = core._slow_weight_cache
    fast = core._weight_cache
    tag = core._tag_cache

    slow_LR_l1 = _l1_mask(slow, is_LR)
    slow_RL_l1 = _l1_mask(slow, is_RL)
    slow_DI = (slow_LR_l1 - slow_RL_l1) / (slow_LR_l1 + slow_RL_l1 + EPS)
    slow_l1_total = float(np.sum(np.abs(slow)))

    tag_mass_final = float(np.sum(np.abs(tag)))

    captures = list(core._consolidation_ledger)

    # Saturation
    effective = fast + slow
    np.clip(effective, -1.0, 1.0, out=effective)
    sat_frac = float(np.sum(np.abs(effective) >= 0.999)) / max(len(effective), 1)

    return {
        "arm": arm_label,
        "n_connections_LR": int(np.sum(is_LR)),
        "n_connections_RL": int(np.sum(is_RL)),
        "n_updates": n_updates,
        "n_captures": len(captures),
        "tag_mass_final": tag_mass_final,
        "n_tagged": int(np.sum(tag > 0)),
        "slow_LR_l1": slow_LR_l1,
        "slow_RL_l1": slow_RL_l1,
        "slow_DI": slow_DI,
        "slow_l1_total": slow_l1_total,
        "slow_max_abs": float(np.max(np.abs(slow))),
        "saturation_frac": sat_frac,
        "nan_hit": nan_hit,
        "capture_signals": [c["capture_signal"] for c in captures],
        "total_slow_delta_l1": sum(c["slow_weight_delta_l1"] for c in captures),
    }


def _fmt_di(v):
    return f"{v:+.4f}"


def _fmt_sci(v):
    return f"{v:.4e}"


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Phase 9D.3 Geometry-Aware Consolidation Validation")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--unit-count", type=int, default=300)
    p.add_argument("--quick", action="store_true",
                   help="Reduce TOTAL_STEPS for fast smoke (not for formal validation).")
    p.add_argument("--dry-run-schedule", action="store_true",
                   help="Print arm schedule summaries without running sim.")
    p.add_argument("--estimate-only", action="store_true",
                   help="Print runtime estimate without running sim.")
    p.add_argument("--output-csv", type=str,
                   default="results/phase9D3_geometry_aware_validation.csv")
    p.add_argument("--summary-json", type=str,
                   default="results/phase9D3_geometry_aware_validation_summary.json")
    args = p.parse_args(argv)

    total_steps = 3000 if args.quick else TOTAL_STEPS
    n_pairs = 1 if args.quick else N_PAIRS_REPEATED

    base_cfg = AnivaConfig(
        unit_count=args.unit_count, seed=args.seed,
        consolidation_enabled=True,
        consolidation_ledger_enabled=True,
        event_pair_plasticity_enabled=True,
        event_pair_trace_tau=1000.0,
        event_pair_ledger_enabled=False,
    )

    print(f"Phase 9D.3 Geometry-Aware Consolidation Validation")
    print(f"  seed={args.seed}  unit_count={args.unit_count}"
          f"  steps={total_steps}  n_pairs={n_pairs}"
          f"  {'(QUICK)' if args.quick else ''}")
    print()

    # Arm definitions
    arm_defs = [
        ("L_then_R_repeated", _make_schedule("L_then_R", WARMUP, PAIR_GAP, PULSE_DURATION, PAIR_INTERVAL, n_pairs)),
        ("R_then_L_repeated", _make_schedule("R_then_L", WARMUP, PAIR_GAP, PULSE_DURATION, PAIR_INTERVAL, n_pairs)),
        ("L_then_R_single",   _make_schedule("L_then_R", WARMUP, PAIR_GAP, PULSE_DURATION, PAIR_INTERVAL, 1)),
        ("R_then_L_single",   _make_schedule("R_then_L", WARMUP, PAIR_GAP, PULSE_DURATION, PAIR_INTERVAL, 1)),
        ("simultaneous",       _make_schedule_simultaneous(WARMUP, PULSE_DURATION, PAIR_INTERVAL, n_pairs)),
        ("no_event",           []),
    ]

    if args.dry_run_schedule:
        print("  Arm Schedules:")
        for name, sched in arm_defs:
            n_events = len(sched)
            if n_events == 0:
                print(f"    {name:22s}: no events")
            else:
                first_t = min(t for t, _, _ in sched)
                last_t = max(t for t, _, _ in sched)
                print(f"    {name:22s}: {n_events} events, "
                      f"steps {first_t}–{last_t}")
        print()
        return 0

    if args.estimate_only:
        single_arm_s = 120
        n_arms = 6
        est_local = n_arms * single_arm_s
        est_ecs = est_local / 4
        print(f"  Runtime estimate (single seed):")
        print(f"    Local:  ~{est_local}s ({est_local/60:.0f} min)")
        print(f"    ECS 4P: ~{est_ecs}s ({est_ecs/60:.0f} min)")
        print()
        return 0

    # ── Step 1: Compute shared geometry baseline ──
    print("  [0/6] Computing shared geometry baseline ...", end=" ", flush=True)
    t0 = time.time()
    gb = compute_geometry_baseline(base_cfg)
    geometry_baseline_DI = gb["geometry_baseline_DI"]
    print(f"{time.time() - t0:.0f}s")
    print(f"    geometry_baseline_DI = {_fmt_di(geometry_baseline_DI)}")
    print(f"    raw_LR_l1 = {_fmt_sci(gb['raw_LR_l1'])}  "
          f"raw_RL_l1 = {_fmt_sci(gb['raw_RL_l1'])}")
    print(f"    trace_mass = {_fmt_sci(gb['trace_mass_before_final'])}  "
          f"phi_mass = {_fmt_sci(gb['phi_mass_combined'])}")
    print()

    # ── Step 2: Run all arms ──
    arm_results = []
    for idx, (name, schedule) in enumerate(arm_defs):
        print(f"  [{idx+1}/6] {name} ...", end=" ", flush=True)
        t_arm = time.time()
        arm_cfg = AnivaConfig(**{k: v for k, v in base_cfg.__dict__.items()
                                  if not k.startswith("_")})
        arm_cfg.seed = args.seed
        r = run_arm(arm_cfg, total_steps, schedule, name)
        wall = time.time() - t_arm
        r["wall_time_s"] = wall
        print(f"{wall:.0f}s  slow_DI={_fmt_di(r['slow_DI'])}  "
              f"slow_l1={_fmt_sci(r['slow_l1_total'])}  "
              f"captures={r['n_captures']}  nan={r['nan_hit']}")
        arm_results.append(r)
    print()

    # ── Step 3: Compute corrected metrics ──
    print("  === Corrected Metrics (geometry_baseline_DI = "
          f"{_fmt_di(geometry_baseline_DI)}) ===")
    print()

    arms_by_name = {r["arm"]: r for r in arm_results}

    # Extract key arms
    lr_rep = arms_by_name["L_then_R_repeated"]
    rl_rep = arms_by_name["R_then_L_repeated"]
    lr_single = arms_by_name["L_then_R_single"]
    rl_single = arms_by_name["R_then_L_single"]
    sim = arms_by_name["simultaneous"]
    noev = arms_by_name["no_event"]

    # Corrected DI
    corrected_LR = lr_rep["slow_DI"] - geometry_baseline_DI
    corrected_RL = rl_rep["slow_DI"] - geometry_baseline_DI
    corrected_sim = sim["slow_DI"] - geometry_baseline_DI
    corrected_slow_OS = corrected_LR - corrected_RL

    # Repeated > single
    ratio_LR = lr_rep["slow_l1_total"] / max(lr_single["slow_l1_total"], EPS)
    ratio_RL = rl_rep["slow_l1_total"] / max(rl_single["slow_l1_total"], EPS)

    # Print per-arm table
    print(f"  {'Arm':<22} {'slow_LR':>12} {'slow_RL':>12} {'slow_DI':>10} "
          f"{'corrected':>10} {'captures':>9} {'slow_l1':>12}")
    print(f"  {'-'*22} {'-'*12} {'-'*12} {'-'*10} {'-'*10} {'-'*9} {'-'*12}")
    for r in arm_results:
        corr = r["slow_DI"] - geometry_baseline_DI
        print(f"  {r['arm']:<22} {_fmt_sci(r['slow_LR_l1']):>12} "
              f"{_fmt_sci(r['slow_RL_l1']):>12} {_fmt_di(r['slow_DI']):>10} "
              f"{_fmt_di(corr):>10} {r['n_captures']:>9} "
              f"{_fmt_sci(r['slow_l1_total']):>12}")
    print()

    # Cross-arm summary
    print("  === Cross-Arm Summary ===")
    print(f"    geometry_baseline_DI:       {_fmt_di(geometry_baseline_DI)}")
    print(f"    corrected_LR_repeated:      {_fmt_di(corrected_LR)}")
    print(f"    corrected_RL_repeated:      {_fmt_di(corrected_RL)}")
    print(f"    corrected_slow_OS:          {_fmt_di(corrected_slow_OS)}")
    print(f"    corrected_simultaneous:     {_fmt_di(corrected_sim)}")
    print(f"    repeated/single ratio LR:   {ratio_LR:.2f}x")
    print(f"    repeated/single ratio RL:   {ratio_RL:.2f}x")
    print(f"    no_event slow_l1:           {_fmt_sci(noev['slow_l1_total'])}")
    print()

    # ── Step 4: Evaluate success criteria ──
    criteria = {}

    # 4.1 Directional Pattern
    criteria["corrected_LR_gt_0"] = corrected_LR > 0
    criteria["corrected_RL_lt_0"] = corrected_RL < 0
    criteria["corrected_slow_OS_gt_0"] = corrected_slow_OS > 0
    criteria["corrected_slow_OS_gt_0.3"] = corrected_slow_OS > 0.3

    # 4.2 Repeated > Single
    criteria["repeated_gt_single_LR"] = ratio_LR > 3.0
    criteria["repeated_gt_single_RL"] = ratio_RL > 3.0

    # 4.3 Controls
    criteria["simultaneous_corrected_near_zero"] = abs(corrected_sim) < 0.1
    criteria["simultaneous_has_slow"] = sim["slow_l1_total"] > 1e-20
    criteria["no_event_clean"] = noev["slow_l1_total"] < 1e-15

    # 4.4 Safety
    criteria["no_nan"] = all(not r["nan_hit"] for r in arm_results)
    criteria["no_explosion"] = all(r["saturation_frac"] < 0.5 for r in arm_results)
    criteria["low_saturation"] = all(r["saturation_frac"] < 0.05 for r in arm_results)
    criteria["captures_present"] = all(
        r["n_captures"] >= 1 for r in arm_results if r["arm"] != "no_event")

    # 4.5 Additional
    criteria["slow_below_max"] = all(
        r["slow_max_abs"] < 0.099 for r in arm_results)  # well below 0.1

    print("  === Success Criteria ===")
    for name, passed in criteria.items():
        flag = "PASS" if passed else "FAIL"
        print(f"    [{flag}] {name}")
    print()

    n_pass = sum(1 for v in criteria.values() if v)
    n_total = len(criteria)
    print(f"  Criteria: {n_pass}/{n_total} passed")
    print()

    # Overall verdict
    primary = [
        criteria["corrected_LR_gt_0"],
        criteria["corrected_RL_lt_0"],
        criteria["corrected_slow_OS_gt_0"],
        criteria["no_nan"],
        criteria["no_event_clean"],
    ]
    if all(primary):
        if criteria["simultaneous_corrected_near_zero"]:
            overall = "POSITIVE: all primary criteria passed, simultaneous control clean."
        else:
            overall = ("CAVEATED POSITIVE: primary directional criteria passed, "
                       f"but simultaneous corrected_DI={corrected_sim:+.4f} "
                       "outside |DI|<0.1.")
    else:
        failed_primary = [k for k in ["corrected_LR_gt_0", "corrected_RL_lt_0",
                         "corrected_slow_OS_gt_0", "no_nan", "no_event_clean"]
                         if not criteria[k]]
        overall = f"NEGATIVE: primary criteria failed: {failed_primary}"

    print(f"  OVERALL: {overall}")
    print()

    # ── CSV ──
    rows = []
    for r in arm_results:
        row = {
            "seed": args.seed,
            "unit_count": args.unit_count,
            "arm": r["arm"],
            "slow_LR_l1": r["slow_LR_l1"],
            "slow_RL_l1": r["slow_RL_l1"],
            "slow_DI": r["slow_DI"],
            "geometry_baseline_DI": geometry_baseline_DI,
            "corrected_slow_DI": r["slow_DI"] - geometry_baseline_DI,
            "slow_l1_total": r["slow_l1_total"],
            "tag_mass_final": r["tag_mass_final"],
            "n_captures": r["n_captures"],
            "saturation_frac": r["saturation_frac"],
            "nan_hit": r["nan_hit"],
        }
        rows.append(row)

    if args.output_csv:
        with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"  CSV: {args.output_csv}")

    if args.summary_json:
        summary = {
            "experiment": "phase9D3_geometry_aware_validation",
            "params": {
                "seed": args.seed,
                "unit_count": args.unit_count,
                "total_steps": total_steps,
                "n_pairs": n_pairs,
            },
            "geometry_baseline": gb,
            "arm_results": {r["arm"]: {
                k: v for k, v in r.items() if k != "arm"
            } for r in arm_results},
            "cross_arm": {
                "corrected_LR_repeated": corrected_LR,
                "corrected_RL_repeated": corrected_RL,
                "corrected_slow_OS": corrected_slow_OS,
                "corrected_simultaneous": corrected_sim,
                "repeated_single_ratio_LR": ratio_LR,
                "repeated_single_ratio_RL": ratio_RL,
            },
            "criteria": criteria,
            "overall_verdict": overall,
        }
        with open(args.summary_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
        print(f"  JSON: {args.summary_json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
