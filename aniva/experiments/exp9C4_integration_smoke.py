"""Phase 9C.4 Integration Smoke — verify core skeleton plumbing.

Single seed, L_then_R + R_then_L only.
Uses Environment.phi_vector → LifeCore.apply_event_pair_phi
→ plasticity_event_pair.apply_event_pair_update chain.

Anti-cheat: dW per-direction classification is offline (experiment-layer),
NOT in the update path.
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


def _classify_connection(src_pos, tgt_pos):
    return f"{_unit_region(src_pos)}→{_unit_region(tgt_pos)}"


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
    return sorted(events, key=lambda x: x[0])


def _build_env_events(schedule):
    """Build StimulusEvent list from schedule tuples."""
    events = []
    for t, side, dur in schedule:
        stim = STIM_MAP[side]
        events.append(StimulusEvent(stimulus=stim, start_step=t, duration_steps=dur))
    return events


def _event_starts_map(schedule):
    """Map step → [side, ...] for event onset detection."""
    m = {}
    for t, side, dur in schedule:
        m.setdefault(t, []).append(side)
    return m


def run_smoke(cfg, steps, schedule, arm):
    """Run one arm using core skeleton: Environment + LifeCore.apply_event_pair_phi."""
    core = LifeCore(cfg)
    n_units = cfg.unit_count
    n_conns = len(core.connections)

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

    for s in range(steps):
        # Standard step with env influences
        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)

        # Event-pair update at event onsets
        if s in event_starts:
            sides = event_starts[s]

            # Build phi from all stimuli starting at this step
            phi = np.zeros(n_units, dtype=np.float64)
            for side in sides:
                phi += phi_cache[side]

            # Snapshot before update for per-direction accounting
            w_before = core._weight_cache.copy()

            result = core.apply_event_pair_phi(phi)

            # Compute per-connection dW (OFFLINE, experiment layer)
            dW_per_conn = core._weight_cache - w_before
            dw_lr = float(np.sum(np.abs(dW_per_conn[is_LR])))
            dw_rl = float(np.sum(np.abs(dW_per_conn[is_RL])))

            acc_dW_LR += dw_lr
            acc_dW_RL += dw_rl

            # Classify within/cross (arm-based, OFFLINE)
            if arm == "L_then_R":
                within = dw_lr
                cross = dw_rl
            else:  # R_then_L
                within = dw_rl
                cross = dw_lr

            within_total += within
            cross_total += cross

            # Gate classification by event parity
            is_within_event = (update_event_idx % 2 == 1)
            gate_val = result["gate"] if result else 0.0
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
                "trace_mass": result["trace_mass"] if result else 0.0,
                "phi_mass": result["phi_mass"] if result else 0.0,
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
              (acc_dW_LR + acc_dW_RL + EPS))
    contam = cross_total / (within_total + cross_total + EPS)

    event_count_L = sum(1 for _, side, _ in schedule if side == "L")
    event_count_R = sum(1 for _, side, _ in schedule if side == "R")

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
        "ledger": ledger,
        "n_connections": len(core.connections),
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Phase 9C.4 Integration Smoke")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--gap", type=int, default=500)
    p.add_argument("--tau", type=int, default=1000)
    p.add_argument("--num-pairs", type=int, default=5)
    p.add_argument("--target", type=float, default=1e-4)
    p.add_argument("--trace-gate-ref", type=float, default=3e-2)
    p.add_argument("--gate-power", type=float, default=1.0)
    p.add_argument("--rest-window", type=int, default=5000)
    p.add_argument("--output-csv", type=str,
                   default="results/phase9C4_integration_smoke.csv")
    p.add_argument("--summary-json", type=str,
                   default="results/phase9C4_integration_smoke_summary.json")
    p.add_argument("--quick", action="store_true",
                   help="Plumbing-only: unit_count=50, num_pairs=2, rest=500.")
    args = p.parse_args(argv)

    unit_count = 300
    num_pairs = args.num_pairs
    rest_window = args.rest_window
    output_csv = args.output_csv
    summary_json = args.summary_json

    if args.quick:
        unit_count = 50
        num_pairs = 2
        rest_window = 500
        output_csv = "results/phase9C4_integration_smoke_quick.csv"
        summary_json = "results/phase9C4_integration_smoke_quick_summary.json"
        print("*** QUICK MODE — plumbing check only, not 9C.3 replication ***")
        print(f"    unit_count={unit_count}  num_pairs={num_pairs}  "
              f"rest_window={rest_window}")
        print()

    pair_interval = args.gap + PULSE_DURATION + rest_window
    total_steps = WARMUP + num_pairs * pair_interval + TAIL_BUFFER

    arms = ["L_then_R", "R_then_L"]

    print(f"Phase 9C.4 Integration Smoke")
    print(f"  seed={args.seed}  unit_count={unit_count}  gap={args.gap}  "
          f"tau={args.tau}")
    print(f"  num_pairs={num_pairs}  rest={rest_window}")
    print(f"  pair_interval={pair_interval}  total_steps={total_steps}")
    print(f"  target={args.target}  gate_ref={args.trace_gate_ref}  "
          f"gate_power={args.gate_power}")
    print()

    t0 = time.time()
    results = {}

    for arm in arms:
        cfg = AnivaConfig(
            unit_count=unit_count, seed=args.seed,
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

        schedule = _make_schedule(arm, args.gap, pair_interval, num_pairs)
        r = run_smoke(cfg, total_steps, schedule, arm)
        results[arm] = r

        nL = r["event_count_L"]
        nR = r["event_count_R"]
        sched_ok = (nL == num_pairs and nR == num_pairs)
        r["schedule_ok"] = sched_ok

        print(f"  [{arm}]  events: L={nL} R={nR}  schedule_ok={sched_ok}")
        print(f"           gate_w={r['mean_gate_within']:.4f}  "
              f"gate_c={r['mean_gate_cross']:.4f}  "
              f"contam={r['contamination_ratio']:.4f}")
        print(f"           within={r['within_total']:.2e}  "
              f"cross={r['cross_total']:.2e}")
        print(f"           acc_dW_DI={r['acc_dW_DI']:+.6f}  "
              f"final_DI={r['final_DI']:+.6e}")
        print(f"           trace_mass={r['mean_trace_mass']:.2e}  "
              f"n_ledger={r['n_ledger']}")
        print()

    # Cross-arm metrics
    ltr = results.get("L_then_R", {})
    rtl = results.get("R_then_L", {})
    acc_dW_OS = ltr.get("acc_dW_DI", 0.0) - rtl.get("acc_dW_DI", 0.0)
    final_OS = ltr.get("final_DI", 0.0) - rtl.get("final_DI", 0.0)

    print(f"  acc_dW_OS = {acc_dW_OS:+.4f}")
    print(f"  final_OS  = {final_OS:+.2e}")

    has_nan = any(
        np.isnan(r[k]) for r in results.values()
        for k in ["final_DI", "acc_dW_DI", "mean_gate_within", "mean_gate_cross"]
        if isinstance(r.get(k), float)
    )
    all_sched_ok = all(r.get("schedule_ok", False) for r in results.values())

    print(f"\n  NaN: {'YES [WARN]' if has_nan else 'none'}")
    print(f"  schedule_ok: {'ALL' if all_sched_ok else 'FAIL'}")
    print(f"  Wall time: {time.time() - t0:.1f}s")

    # CSV output
    all_rows = []
    for arm in arms:
        r = results[arm]
        all_rows.append({
            "seed": args.seed, "unit_count": unit_count,
            "gap": args.gap, "tau_trace": args.tau,
            "rest_window": rest_window, "gate_mode": "soft_trace_gate",
            "arm": arm, "target_event_update_l1": args.target,
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
            "final_DI": r["final_DI"],
            "acc_dW_OS": acc_dW_OS,
        })

    if output_csv:
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
            w.writeheader()
            w.writerows(all_rows)
        print(f"\nCSV: {output_csv}")

    if summary_json:
        summary = {
            "experiment": "phase9C4_integration_smoke",
            "quick_mode": args.quick,
            "params": {
                "seed": args.seed, "unit_count": unit_count,
                "gap": args.gap, "tau_trace": args.tau,
                "num_pairs": num_pairs, "target": args.target,
                "trace_gate_ref": args.trace_gate_ref,
                "gate_power": args.gate_power,
                "rest_window": rest_window,
            },
            "acc_dW_OS": acc_dW_OS,
            "final_OS": final_OS,
            "has_nan": has_nan,
            "all_schedule_ok": all_sched_ok,
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
            } for r in results.values()],
        }
        with open(summary_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
        print(f"JSON: {summary_json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
