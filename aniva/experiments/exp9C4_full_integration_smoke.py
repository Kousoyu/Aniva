"""Phase 9C.4 Full Integration Smoke — 300-unit core path vs 9C.3 diagnostic.

Verifies the core skeleton chain at full scale:
  Environment.phi_vector → LifeCore.apply_event_pair_phi
  → plasticity_event_pair.apply_event_pair_update

KEY DIFFERENCE from 9C.3 diagnostic (exp9C1C_trace_gated_update.py):
  - 9C.3 diagnostic: Hebbian plasticity DISABLED (temporal_plasticity_enabled=False).
    Event-pair update is the only plasticity source.
  - 9C.4 full smoke: Hebbian plasticity ENABLED (normal LifeCore.step).
    Event-pair dW is superimposed on continuous Hebbian dW.

  This means full smoke does NOT require bit-identical results with 9C.3.
  The success criteria are:
    gate_w ≈ 1.0, gate_c < 0.05, contamination < 0.05,
    acc_dW_OS positive, schedule_ok all true, no NaN / no explosion.

Anti-cheat: dW per-direction classification is offline (experiment-layer),
NOT in the update path. No arm/L/R labels in apply_event_pair_update.
"""

import argparse, csv, json, sys, math, time
import numpy as np

from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.environment.environment import Stimulus, StimulusEvent, Environment

L_STIM = Stimulus(position=(-0.5, 0.0, 0.0), intensity=0.02, radius=0.5)
R_STIM = Stimulus(position=(0.5, 0.0, 0.0), intensity=0.02, radius=0.5)

PULSE_DURATION = 80
WARMUP = 200
TAIL_BUFFER = 200
EPS = 1e-12

STIM_MAP = {"L": L_STIM, "R": R_STIM}


def _unit_region(pos):
    x = pos[0]
    if x < -0.1: return "L"
    elif x > 0.1: return "R"
    return "M"


def _make_schedule(order, pair_gap, pair_interval, num_pairs):
    events = []
    for i in range(num_pairs):
        pair_start = WARMUP + i * pair_interval
        if order == "L_then_R":
            events.append((pair_start, "L", PULSE_DURATION))
            events.append((pair_start + pair_gap, "R", PULSE_DURATION))
        elif order == "R_then_L":
            events.append((pair_start, "R", PULSE_DURATION))
            events.append((pair_start + pair_gap, "L", PULSE_DURATION))
        elif order == "simultaneous":
            events.append((pair_start, "L", PULSE_DURATION))
            events.append((pair_start, "R", PULSE_DURATION))
        elif order == "separated_control":
            events.append((pair_start, "L", PULSE_DURATION))
            events.append((pair_start + pair_interval // 2, "R", PULSE_DURATION))
    return sorted(events, key=lambda x: x[0])


def _build_env_events(schedule):
    events = []
    for t, side, dur in schedule:
        events.append(StimulusEvent(
            stimulus=STIM_MAP[side], start_step=t, duration_steps=dur))
    return events


def _event_starts_map(schedule):
    m = {}
    for t, side, _dur in schedule:
        m.setdefault(t, []).append(side)
    return m


def run_arm(cfg, steps, schedule, arm):
    """Run one arm using core path: Environment + LifeCore.apply_event_pair_phi."""
    core = LifeCore(cfg)
    n_units = cfg.unit_count

    # Pre-compute connection metadata for offline analysis
    src_regions = np.array([_unit_region(core.units[c.source_id].position)
                            for c in core.connections])
    tgt_regions = np.array([_unit_region(core.units[c.target_id].position)
                            for c in core.connections])
    is_LR = (src_regions == "L") & (tgt_regions == "R")
    is_RL = (src_regions == "R") & (tgt_regions == "L")

    # Build environment
    env_events = _build_env_events(schedule)
    env = Environment()
    for ev in env_events:
        env.add_event(ev)

    event_starts = _event_starts_map(schedule)

    # Pre-compute phi for each stimulus (position-dependent, unchanging)
    phi_cache = {
        "L": np.array([L_STIM.influence_at(tuple(core._positions[uid]))
                        for uid in range(n_units)], dtype=np.float64),
        "R": np.array([R_STIM.influence_at(tuple(core._positions[uid]))
                        for uid in range(n_units)], dtype=np.float64),
    }

    w0 = core._weight_cache.copy()
    acc_dW_LR = 0.0
    acc_dW_RL = 0.0
    within_total = 0.0
    cross_total = 0.0
    gates_within = []
    gates_cross = []
    ledger = []
    update_event_idx = 1
    nan_count = 0

    for s in range(steps):
        # Standard step with env influences (includes Hebbian plasticity,
        # homeostasis, trace decay — full core path)
        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)

        # Check for NaN in weights
        if np.any(np.isnan(core._weight_cache)):
            nan_count += 1

        # Event-pair update at event onsets
        if s in event_starts:
            sides = event_starts[s]

            phi = np.zeros(n_units, dtype=np.float64)
            for side in sides:
                phi += phi_cache[side]

            w_before = core._weight_cache.copy()
            result = core.apply_event_pair_phi(phi)

            # Check if an update actually fired (trace had mass)
            update_fired = result is not None

            if update_fired:
                dW_per_conn = core._weight_cache - w_before
                dw_lr = float(np.sum(np.abs(dW_per_conn[is_LR])))
                dw_rl = float(np.sum(np.abs(dW_per_conn[is_RL])))

                acc_dW_LR += dw_lr
                acc_dW_RL += dw_rl

                # Classify within/cross (arm-based, OFFLINE)
                if arm == "L_then_R":
                    within, cross = dw_lr, dw_rl
                elif arm == "R_then_L":
                    within, cross = dw_rl, dw_lr
                elif arm == "simultaneous":
                    within = cross = (dw_lr + dw_rl) / 2.0
                else:  # separated_control
                    within, cross = dw_lr, dw_rl

                within_total += within
                cross_total += cross

                # Gate classification by event parity
                # (matches diagnostic: update_event_idx is only incremented
                #  when an update fires, so parity correctly maps to within/cross)
                is_within_event = (update_event_idx % 2 == 1)
                gate_val = result["gate"]
                if is_within_event:
                    gates_within.append(gate_val)
                else:
                    gates_cross.append(gate_val)

                acc_dW_DI = ((acc_dW_LR - acc_dW_RL) /
                             (acc_dW_LR + acc_dW_RL + EPS))

                ledger.append({
                    "event_index": update_event_idx,
                    "pair_index": (update_event_idx + 1) // 2,
                    "step": s,
                    "gate": gate_val,
                    "trace_mass": result["trace_mass"],
                    "phi_mass": result["phi_mass"],
                    "dW_LR_l1": dw_lr,
                    "dW_RL_l1": dw_rl,
                    "within": within,
                    "cross": cross,
                    "contamination": cross / (within + cross + EPS),
                    "acc_dW_DI": acc_dW_DI,
                })

                update_event_idx += 1

    # Final readout
    wf = core._weight_cache
    dw_lr_final = float(np.sum(np.abs(wf[is_LR] - w0[is_LR])))
    dw_rl_final = float(np.sum(np.abs(wf[is_RL] - w0[is_RL])))
    final_DI = ((dw_lr_final - dw_rl_final) /
                (dw_lr_final + dw_rl_final + EPS))

    acc_DI = ((acc_dW_LR - acc_dW_RL) /
              (acc_dW_LR + acc_dW_RL + EPS)) if (acc_dW_LR + acc_dW_RL) > EPS else 0.0
    contam = cross_total / (within_total + cross_total + EPS)

    event_count_L = sum(1 for _, side, _ in schedule if side == "L")
    event_count_R = sum(1 for _, side, _ in schedule if side == "R")

    # Saturation: fraction of weights exactly at ±1.0 boundary
    sat_frac = float(np.sum(np.abs(wf) >= 0.999)) / len(wf) if len(wf) > 0 else 0.0

    return {
        "arm": arm,
        "event_count_L": event_count_L,
        "event_count_R": event_count_R,
        "final_DI": final_DI,
        "acc_dW_LR": acc_dW_LR,
        "acc_dW_RL": acc_dW_RL,
        "acc_dW_DI": acc_DI,
        "within_total": within_total,
        "cross_total": cross_total,
        "contamination_ratio": contam,
        "mean_gate_within": float(np.mean(gates_within)) if gates_within else 0.0,
        "mean_gate_cross": float(np.mean(gates_cross)) if gates_cross else 0.0,
        "mean_trace_mass": float(np.mean([e["trace_mass"] for e in ledger])) if ledger else 0.0,
        "n_ledger": len(ledger),
        "nan_count": nan_count,
        "saturation_frac": sat_frac,
        "n_connections": len(core.connections),
        "ledger": ledger,
    }


def estimate_runtime(total_steps, n_arms):
    """Rough estimate based on ECS 9C.3 timing ~9 min/arm for 28300 steps."""
    base_steps = 28300
    base_time_per_arm_min = 9.0
    est_per_arm = (total_steps / base_steps) * base_time_per_arm_min
    total = est_per_arm * n_arms
    print(f"Runtime estimate:")
    print(f"  total_steps per arm: {total_steps}")
    print(f"  n_arms: {n_arms}")
    print(f"  est per arm: ~{est_per_arm:.1f} min")
    print(f"  est total (serial): ~{total:.1f} min")
    print(f"  est total (ECS 4-core parallel): ~{est_per_arm * max(1, n_arms / 4):.1f} min")
    print(f"  NOTE: based on 9C.3 ECS timing (~9 min/arm @ 28300 steps, 300 units)")


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Phase 9C.4 Full Integration Smoke — 300-unit core path")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--unit-count", type=int, default=300)
    p.add_argument("--gap", type=int, default=500)
    p.add_argument("--tau", type=int, default=1000)
    p.add_argument("--num-pairs", type=int, default=5)
    p.add_argument("--target", type=float, default=1e-4,
                   help="target_event_update_l1")
    p.add_argument("--trace-gate-ref", type=float, default=3e-2)
    p.add_argument("--gate-power", type=float, default=1.0)
    p.add_argument("--rest-window", type=int, default=5000)
    p.add_argument("--arms", type=str, nargs="+",
                   default=["L_then_R", "R_then_L"])
    p.add_argument("--output-csv", type=str,
                   default="results/phase9C4_full_integration_smoke_seed42_seq.csv")
    p.add_argument("--summary-json", type=str,
                   default="results/phase9C4_full_integration_smoke_seed42_seq_summary.json")
    p.add_argument("--estimate-only", action="store_true",
                   help="Print runtime estimate and exit (no simulation).")
    p.add_argument("--dry-run-schedule", action="store_true",
                   help="Print schedule for each arm and exit (no simulation).")
    args = p.parse_args(argv)

    pair_interval = args.gap + PULSE_DURATION + args.rest_window
    total_steps = WARMUP + args.num_pairs * pair_interval + TAIL_BUFFER

    if args.estimate_only:
        estimate_runtime(total_steps, len(args.arms))
        return 0

    if args.dry_run_schedule:
        for arm in args.arms:
            sched = _make_schedule(arm, args.gap, pair_interval, args.num_pairs)
            nL = sum(1 for _, side, _ in sched if side == "L")
            nR = sum(1 for _, side, _ in sched if side == "R")
            print(f"[{arm}] total_steps={total_steps}  events: L={nL} R={nR}  "
                  f"schedule_ok={nL == args.num_pairs and nR == args.num_pairs}")
            for t, side, dur in sched:
                print(f"  step={t:>6d}  side={side}  dur={dur}")
        return 0

    print(f"Phase 9C.4 Full Integration Smoke")
    print(f"  seed={args.seed}  unit_count={args.unit_count}")
    print(f"  gap={args.gap}  tau={args.tau}  num_pairs={args.num_pairs}")
    print(f"  rest_window={args.rest_window}  target={args.target}")
    print(f"  gate_ref={args.trace_gate_ref}  gate_power={args.gate_power}")
    print(f"  pair_interval={pair_interval}  total_steps={total_steps}")
    print(f"  arms={args.arms}")
    print(f"  NOTE: Hebbian plasticity ENABLED (full core path).")
    print(f"        Results NOT expected to be bit-identical with 9C.3 diagnostic.")
    print()

    t0 = time.time()
    results = {}

    for arm in args.arms:
        cfg = AnivaConfig(
            unit_count=args.unit_count, seed=args.seed,
            event_pair_plasticity_enabled=True,
            event_pair_trace_tau=float(args.tau),
            event_pair_target_update_l1=args.target,
            event_pair_gate_mode="soft_trace_gate",
            event_pair_trace_gate_ref=args.trace_gate_ref,
            event_pair_gate_power=args.gate_power,
            event_pair_ledger_enabled=True,
            homeostasis_enabled=True,
            homeostatic_target_abs_weight=0.30,
            homeostatic_rate=1.0,
        )

        schedule = _make_schedule(arm, args.gap, pair_interval, args.num_pairs)
        r = run_arm(cfg, total_steps, schedule, arm)
        results[arm] = r

        nL = r["event_count_L"]
        nR = r["event_count_R"]
        sched_ok = (nL == args.num_pairs and nR == args.num_pairs)
        r["schedule_ok"] = sched_ok

        print(f"  [{arm}]")
        print(f"    events: L={nL} R={nR}  schedule_ok={sched_ok}")
        print(f"    gate_w={r['mean_gate_within']:.4f}  "
              f"gate_c={r['mean_gate_cross']:.4f}")
        print(f"    within={r['within_total']:.2e}  "
              f"cross={r['cross_total']:.2e}  "
              f"contam={r['contamination_ratio']:.4f}")
        print(f"    acc_dW_DI={r['acc_dW_DI']:+.6f}  "
              f"final_DI={r['final_DI']:+.6e}")
        print(f"    trace_mass={r['mean_trace_mass']:.2e}  "
              f"n_ledger={r['n_ledger']}  "
              f"nan={r['nan_count']}  sat={r['saturation_frac']:.4f}")
        print()

    # Cross-arm metrics
    ltr = results.get("L_then_R", {})
    rtl = results.get("R_then_L", {})
    acc_dW_OS = (ltr.get("acc_dW_DI", 0.0) - rtl.get("acc_dW_DI", 0.0)
                 if ltr and rtl else 0.0)
    final_OS = (ltr.get("final_DI", 0.0) - rtl.get("final_DI", 0.0)
                if ltr and rtl else 0.0)

    print(f"  acc_dW_OS = {acc_dW_OS:+.4f}")
    print(f"  final_OS  = {final_OS:+.2e}")

    total_nan = sum(r.get("nan_count", 0) for r in results.values())
    all_sched_ok = all(r.get("schedule_ok", False) for r in results.values())

    has_nan_metric = any(
        np.isnan(r[k]) for r in results.values()
        for k in ["final_DI", "acc_dW_DI", "mean_gate_within",
                   "mean_gate_cross", "contamination_ratio"]
        if isinstance(r.get(k), float)
    )

    wall_s = time.time() - t0
    print(f"\n  NaN (metrics): {'YES [WARN]' if has_nan_metric else 'none'}")
    print(f"  NaN (weights): {total_nan}")
    print(f"  schedule_ok: {'ALL' if all_sched_ok else 'FAIL'}")
    print(f"  Wall time: {wall_s:.1f}s")

    # 9C.3 reference for sanity check
    print(f"\n  9C.3 seed42 reference: acc_dW_OS=+1.949  "
          f"contam=0.017  gate_w=1.000  gate_c≈0.02-0.03")
    print(f"  (full smoke not required to match exactly — Hebbian coexistence)")

    # CSV output
    all_rows = []
    for arm in args.arms:
        r = results[arm]
        all_rows.append({
            "seed": args.seed,
            "unit_count": args.unit_count,
            "gap": args.gap,
            "tau_trace": args.tau,
            "rest_window": args.rest_window,
            "num_pairs": args.num_pairs,
            "gate_mode": "soft_trace_gate",
            "arm": arm,
            "target_event_update_l1": args.target,
            "trace_gate_ref": args.trace_gate_ref,
            "gate_power": args.gate_power,
            "event_count_L": r["event_count_L"],
            "event_count_R": r["event_count_R"],
            "schedule_ok": r["schedule_ok"],
            "mean_trace_mass": r["mean_trace_mass"],
            "mean_gate_within": r["mean_gate_within"],
            "mean_gate_cross": r["mean_gate_cross"],
            "within_pair_dW_L1": r["within_total"],
            "cross_pair_dW_L1": r["cross_total"],
            "contamination_ratio": r["contamination_ratio"],
            "acc_dW_DI": r["acc_dW_DI"],
            "acc_dW_LR": r["acc_dW_LR"],
            "acc_dW_RL": r["acc_dW_RL"],
            "acc_dW_OS": acc_dW_OS,
            "final_DI": r["final_DI"],
            "final_OS": final_OS,
            "nan_count": r["nan_count"],
            "saturation_frac": r["saturation_frac"],
            "runtime_s": wall_s,
        })

    if args.output_csv:
        with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
            w.writeheader()
            w.writerows(all_rows)
        print(f"\nCSV: {args.output_csv}")

    if args.summary_json:
        summary = {
            "experiment": "phase9C4_full_integration_smoke",
            "params": {
                "seed": args.seed,
                "unit_count": args.unit_count,
                "gap": args.gap,
                "tau_trace": args.tau,
                "num_pairs": args.num_pairs,
                "target_event_update_l1": args.target,
                "trace_gate_ref": args.trace_gate_ref,
                "gate_power": args.gate_power,
                "rest_window": args.rest_window,
                "gate_mode": "soft_trace_gate",
            },
            "acc_dW_OS": acc_dW_OS,
            "final_OS": final_OS,
            "has_nan_metric": has_nan_metric,
            "total_nan_weights": total_nan,
            "all_schedule_ok": all_sched_ok,
            "wall_time_s": wall_s,
            "c9_3_reference": {
                "acc_dW_OS": 1.949,
                "contam": 0.017,
                "gate_w": 1.0,
                "gate_c_range": [0.023, 0.027],
                "note": "full smoke NOT required to match — Hebbian coexistence",
            },
            "arms": [{
                "arm": r["arm"],
                "acc_dW_DI": r["acc_dW_DI"],
                "final_DI": r["final_DI"],
                "contamination_ratio": r["contamination_ratio"],
                "mean_gate_within": r["mean_gate_within"],
                "mean_gate_cross": r["mean_gate_cross"],
                "within_total": r["within_total"],
                "cross_total": r["cross_total"],
                "schedule_ok": r["schedule_ok"],
                "nan_count": r["nan_count"],
                "saturation_frac": r["saturation_frac"],
            } for r in results.values()],
        }
        with open(args.summary_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
        print(f"JSON: {args.summary_json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
