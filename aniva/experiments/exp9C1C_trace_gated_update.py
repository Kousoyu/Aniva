"""Phase 9C.1C: Trace-Gated Event-Pair Update.

Diagnostic: restore trace decay as the temporal gate by making the per-event
update budget proportional to trace_mass, not constant.

Gate modes:
  bare_l1_norm:    dW = target * raw / raw_l1          (9C.1B replicate)
  soft_trace_gate: dW = target * gate * raw / raw_l1   (MAIN)
                    gate = min(1, trace_mass / ref) ** power
  hard_threshold:  dW = target * raw / raw_l1 if trace_mass > thresh else 0  (ablation)

Rest conditions: 500 (baseline), 5000 (trial-isolated / washout).

Anti-cheat: arm/L/R labels used ONLY for offline ledger analysis.
Plasticity update path contains NO labels, NO arm names, NO order knowledge.
"""

import argparse, csv, json, sys, math, time
import numpy as np

from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.environment.environment import Stimulus, StimulusEvent

L_STIM = Stimulus(position=(-0.5, 0.0, 0.0), intensity=0.02, radius=0.5)
R_STIM = Stimulus(position=(0.5, 0.0, 0.0), intensity=0.02, radius=0.5)

PULSE_DURATION = 80
WARMUP = 200
TAIL_BUFFER = 200
DEFAULT_GAP = 500
DEFAULT_TAU = 1000
DEFAULT_TARGET = 1e-4
EPS = 1e-12


def _unit_region(pos):
    x = pos[0]
    if x < -0.1: return "L"
    elif x > 0.1: return "R"
    return "M"


def _classify_connection(sp, tp):
    return f"{_unit_region(sp)}→{_unit_region(tp)}"


# ── Readout ─────────────────────────────────────────────────────────────

def _structural_readout(core, w0):
    conns = list(core.connections)
    wf = np.array([c.weight for c in conns], dtype=np.float64)
    deltas = wf - w0
    regions = [_classify_connection(core.units[c.source_id].position,
                                     core.units[c.target_id].position) for c in conns]
    uregs = sorted(set(regions))
    regional = {}
    for reg in uregs:
        m = np.array([r == reg for r in regions])
        rd = deltas[m]
        regional[reg] = {"count": int(np.sum(m)),
                         "l1": float(np.mean(np.abs(rd))) if len(rd) > 0 else 0.0}
    return {
        "global_l1": float(np.mean(np.abs(deltas))),
        "regional": regional,
        "directional": {
            "L_to_R_l1": regional.get("L→R", {}).get("l1", 0.0),
            "R_to_L_l1": regional.get("R→L", {}).get("l1", 0.0),
        },
    }


def _compute_DI(d):
    lr = d.get("L_to_R_l1", 0.0)
    rl = d.get("R_to_L_l1", 0.0)
    return (lr - rl) / (lr + rl + EPS)


# ── Scheduling ──────────────────────────────────────────────────────────

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


# ── Phi ─────────────────────────────────────────────────────────────────

def _compute_phi(core, stimulus):
    n = core.config.unit_count
    phi = np.zeros(n, dtype=np.float64)
    stim_pos = np.array(stimulus.position)
    for uid in range(n):
        u = core.units[uid]
        d = np.linalg.norm(np.array(u.position) - stim_pos)
        if d <= stimulus.radius:
            phi[uid] = stimulus.intensity * (1.0 - d / stimulus.radius)
    return phi


# ── Environment ─────────────────────────────────────────────────────────

def _influences_at_step(active_events, step, core):
    inf = {}
    for ev in active_events:
        if ev.start_step <= step < ev.start_step + ev.duration_steps:
            for uid in range(core.config.unit_count):
                u = core.units[uid]
                d = np.linalg.norm(np.array(u.position) - np.array(ev.stimulus.position))
                if d <= ev.stimulus.radius:
                    v = ev.stimulus.intensity * (1.0 - d / ev.stimulus.radius)
                    inf[uid] = inf.get(uid, 0.0) + v
    return inf if inf else None


# ── Trace-gated update ──────────────────────────────────────────────────

def _apply_trace_gated_update(core, trace, phi, target_l1, gate_mode,
                               trace_gate_ref, gate_power, threshold):
    """Apply event-pair update with trace-mass-gated normalization.

    Returns (ledger dict, dw_lr, dw_rl).
    Labels used ONLY in the returned ledger for offline analysis.
    """
    conns = list(core.connections)
    n_conns = len(conns)
    n_units = core.config.unit_count

    # Pre-compute region masks for ledger analysis only
    unit_regions = np.array([_unit_region(core.units[uid].position) for uid in range(n_units)])
    mask_L = unit_regions == "L"
    mask_R = unit_regions == "R"

    trace_mass = float(np.sum(np.abs(trace)))
    trace_L_mass = float(np.sum(np.abs(trace[mask_L])))
    trace_R_mass = float(np.sum(np.abs(trace[mask_R])))
    phi_L_mass = float(np.sum(np.abs(phi[mask_L])))
    phi_R_mass = float(np.sum(np.abs(phi[mask_R])))

    # Compute raw deltas — NO labels
    raw = np.zeros(n_conns, dtype=np.float64)
    for k, conn in enumerate(conns):
        raw[k] = trace[conn.source_id] * phi[conn.target_id]

    raw_l1 = float(np.sum(np.abs(raw)))

    # Compute gate value
    if gate_mode == "bare_l1_norm":
        gate = 1.0
    elif gate_mode == "soft_trace_gate":
        gate = min(1.0, trace_mass / max(trace_gate_ref, EPS)) ** gate_power
    elif gate_mode == "hard_threshold":
        gate = 1.0 if trace_mass > threshold else 0.0
    else:
        gate = 1.0

    effective_target = target_l1 * gate

    if raw_l1 < EPS or effective_target < EPS:
        return {
            "trace_mass": trace_mass,
            "trace_L_mass": trace_L_mass,
            "trace_R_mass": trace_R_mass,
            "phi_L_mass": phi_L_mass,
            "phi_R_mass": phi_R_mass,
            "raw_l1": raw_l1,
            "gate": gate,
            "effective_target": effective_target,
            "dW_L_to_R_l1": 0.0,
            "dW_R_to_L_l1": 0.0,
            "dW_total_l1": 0.0,
            "within_pair_dW": 0.0,
            "cross_pair_dW": 0.0,
            "contamination_ratio": 0.0,
        }, 0.0, 0.0

    scale = effective_target / raw_l1

    # Apply update — NO labels
    dW_by_conn = np.zeros(n_conns, dtype=np.float64)
    for k, conn in enumerate(conns):
        dw = scale * raw[k]
        w = conn.weight + dw
        conn.weight = max(-1.0, min(1.0, w))
        dW_by_conn[k] = dw

    # Per-direction accounting (ANALYSIS ONLY)
    dw_lr, dw_rl = 0.0, 0.0
    for k, conn in enumerate(conns):
        reg = _classify_connection(core.units[conn.source_id].position,
                                    core.units[conn.target_id].position)
        if reg == "L→R":
            dw_lr += abs(dW_by_conn[k])
        elif reg == "R→L":
            dw_rl += abs(dW_by_conn[k])

    return {
        "trace_mass": trace_mass,
        "trace_L_mass": trace_L_mass,
        "trace_R_mass": trace_R_mass,
        "phi_L_mass": phi_L_mass,
        "phi_R_mass": phi_R_mass,
        "raw_l1": raw_l1,
        "gate": gate,
        "effective_target": effective_target,
        "dW_L_to_R_l1": dw_lr,
        "dW_R_to_L_l1": dw_rl,
        "dW_total_l1": float(np.sum(np.abs(dW_by_conn))),
    }, dw_lr, dw_rl


# ── Core simulation ────────────────────────────────────────────────────

def _run_gated(cfg, steps, schedule, tau_trace, target_l1,
               gate_mode, trace_gate_ref, gate_power, threshold, mode, arm):
    core = LifeCore(cfg)
    w0 = np.array([c.weight for c in core.connections], dtype=np.float64)
    n_units = cfg.unit_count

    trace = np.zeros(n_units, dtype=np.float64) if mode == "event_pair" else None
    last_pulse_time = 0.0

    acc_dW_LR = 0.0
    acc_dW_RL = 0.0
    within_total = 0.0
    cross_total = 0.0

    # Gate diagnostics per event type
    gates_within = []
    gates_cross = []

    ledger = []
    elog = []
    aevs = []
    idx = 0

    phi_cache = {"L": _compute_phi(core, L_STIM), "R": _compute_phi(core, R_STIM)} \
        if mode == "event_pair" else {}

    event_starts = {}
    for t, side, dur in schedule:
        event_starts.setdefault(t, []).append(side)

    update_event_idx = 1

    for s in range(steps):
        if mode == "event_pair" and s in event_starts:
            sides = event_starts[s]

            dt = s - last_pulse_time if last_pulse_time > 0 else 0.0
            if dt > 0 and tau_trace > 0:
                trace *= math.exp(-dt / tau_trace)

            phi = np.zeros(n_units, dtype=np.float64)
            for side in sides:
                phi += phi_cache[side]

            if np.sum(np.abs(trace)) > EPS and np.sum(np.abs(phi)) > EPS:
                info, dw_lr, dw_rl = _apply_trace_gated_update(
                    core, trace, phi, target_l1, gate_mode,
                    trace_gate_ref, gate_power, threshold)

                acc_dW_LR += dw_lr
                acc_dW_RL += dw_rl

                # Classify within/cross (ANALYSIS ONLY, uses arm)
                if arm == "L_then_R":
                    within = dw_lr; cross = dw_rl
                elif arm == "R_then_L":
                    within = dw_rl; cross = dw_lr
                elif arm == "simultaneous":
                    within = (dw_lr + dw_rl) / 2.0; cross = (dw_lr + dw_rl) / 2.0
                else:  # separated_control
                    within = dw_lr; cross = dw_rl

                within_total += within
                cross_total += cross

                is_within_event = (update_event_idx % 2 == 1)
                if is_within_event:
                    gates_within.append(info["gate"])
                else:
                    gates_cross.append(info["gate"])

                acc_dW_DI = ((acc_dW_LR - acc_dW_RL) /
                             (acc_dW_LR + acc_dW_RL + EPS))

                ledger.append({
                    "event_index": update_event_idx,
                    "pair_index": (update_event_idx + 1) // 2,
                    "pulse_step": s,
                    "pulse_region": sides[0] if len(sides) == 1 else "LR",
                    "is_within_pair_event": is_within_event,
                    "dt": dt,
                    "trace_mass": info["trace_mass"],
                    "trace_L_mass": info["trace_L_mass"],
                    "trace_R_mass": info["trace_R_mass"],
                    "phi_L_mass": info["phi_L_mass"],
                    "phi_R_mass": info["phi_R_mass"],
                    "raw_l1": info["raw_l1"],
                    "gate": info["gate"],
                    "effective_target": info["effective_target"],
                    "dW_L_to_R_l1": dw_lr,
                    "dW_R_to_L_l1": dw_rl,
                    "within_pair_dW": within,
                    "cross_pair_dW": cross,
                    "contamination_ratio": cross / (within + cross + EPS),
                    "accumulated_dW_DI": acc_dW_DI,
                    "accumulated_dW_LR": acc_dW_LR,
                    "accumulated_dW_RL": acc_dW_RL,
                })

                update_event_idx += 1

            # Update trace for next event
            trace += phi
            last_pulse_time = float(s)

        while idx < len(schedule) and schedule[idx][0] <= s:
            t, lb, dur = schedule[idx]
            if t == s:
                stim = L_STIM if lb == "L" else R_STIM
                aevs.append(StimulusEvent(stimulus=stim, start_step=s, duration_steps=dur))
                elog.append({"step": s, "side": lb, "duration": dur})
            idx += 1

        core.step(env_influences=_influences_at_step(aevs, s, core))

    final_readout = _structural_readout(core, w0)
    final_DI = _compute_DI(final_readout["directional"])
    acc_DI = ((acc_dW_LR - acc_dW_RL) / (acc_dW_LR + acc_dW_RL + EPS))
    contam = cross_total / (within_total + cross_total + EPS)

    nL = sum(1 for e in elog if e["side"] == "L")
    nR = sum(1 for e in elog if e["side"] == "R")

    return {
        "arm": arm,
        "event_count_L": nL, "event_count_R": nR, "total_events": len(elog),
        "final_readout": final_readout, "final_DI": final_DI,
        "acc_dW_LR": acc_dW_LR, "acc_dW_RL": acc_dW_RL, "acc_dW_DI": acc_DI,
        "within_total": within_total, "cross_total": cross_total,
        "contamination_ratio": contam,
        "mean_trace_mass": float(np.mean([e["trace_mass"] for e in ledger])) if ledger else 0.0,
        "mean_gate_within": float(np.mean(gates_within)) if gates_within else 0.0,
        "mean_gate_cross": float(np.mean(gates_cross)) if gates_cross else 0.0,
        "n_ledger": len(ledger),
        "ledger": ledger,
    }


# ── Main ────────────────────────────────────────────────────────────────

def main(argv=None):
    import sys as _sys
    _sys.stdout.reconfigure(line_buffering=True)

    p = argparse.ArgumentParser(description="Phase 9C.1C: Trace-Gated Update")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--gap", type=int, default=DEFAULT_GAP)
    p.add_argument("--tau", type=int, default=DEFAULT_TAU)
    p.add_argument("--num-pairs", type=int, default=5)
    p.add_argument("--target", type=float, default=DEFAULT_TARGET)
    p.add_argument("--rest-windows", type=int, nargs="+", default=[500])
    p.add_argument("--gate-modes", type=str, nargs="+",
                   default=["bare_l1_norm", "soft_trace_gate", "hard_threshold"])
    p.add_argument("--trace-gate-ref", type=float, default=3e-2)
    p.add_argument("--gate-power", type=float, default=1.0)
    p.add_argument("--threshold", type=float, default=1e-3)
    p.add_argument("--arms", type=str, nargs="+",
                   default=["L_then_R", "R_then_L", "simultaneous", "separated_control"])
    p.add_argument("--output-csv", type=str,
                   default="results/phase9C1C_trace_gated_update.csv")
    p.add_argument("--summary-json", type=str,
                   default="results/phase9C1C_trace_gated_update_summary.json")
    p.add_argument("--no-homeostasis", action="store_true")
    args = p.parse_args(argv)

    rest_windows = args.rest_windows
    gate_modes = args.gate_modes
    arm_names = args.arms
    tau = args.tau

    t0 = time.time()
    all_rows = []
    summary_arms = []

    for rest in rest_windows:
        pair_interval = args.gap + PULSE_DURATION + rest
        total_steps = WARMUP + args.num_pairs * pair_interval + TAIL_BUFFER
        label_rest = f"rest={rest}"
        print(f"\n{'#'*80}")
        print(f"#  {label_rest}  pair_interval={pair_interval}  total_steps={total_steps}")
        print(f"{'#'*80}")

        # ── OFF baseline (one per rest condition) ──
        cfg_off = AnivaConfig(unit_count=300, seed=args.seed)
        cfg_off.homeostasis_enabled = not args.no_homeostasis
        cfg_off.homeostatic_target_abs_weight = 0.30
        cfg_off.homeostatic_rate = 0.0 if args.no_homeostasis else 1.0
        cfg_off.temporal_plasticity_enabled = False

        off_ltr = None; off_rtl = None
        for arm in ["L_then_R", "R_then_L"]:
            if arm in arm_names:
                sched = _make_schedule(arm, args.gap, pair_interval, args.num_pairs)
                r = _run_gated(cfg_off, total_steps, sched, tau_trace=0, target_l1=0,
                               gate_mode="bare_l1_norm", trace_gate_ref=0,
                               gate_power=0, threshold=0, mode="OFF", arm=arm)
                r["rest_window"] = rest; r["gate_mode"] = "OFF"
                r["trace_gate_ref"] = 0; r["gate_power"] = 0
                di = r["final_DI"]
                print(f"  OFF {arm:>20s}  DI={di:+.6e}")
                if arm == "L_then_R": off_ltr = r
                else: off_rtl = r

        off_OS = (_compute_DI(off_ltr["final_readout"]["directional"]) -
                  _compute_DI(off_rtl["final_readout"]["directional"])) \
            if off_ltr and off_rtl else 0.0
        print(f"  OFF OS = {off_OS:+.2e}\n")

        # ── event_pair sweep ──
        for gmode in gate_modes:
            cfg_ep = AnivaConfig(unit_count=300, seed=args.seed)
            cfg_ep.homeostasis_enabled = not args.no_homeostasis
            cfg_ep.homeostatic_target_abs_weight = 0.30
            cfg_ep.homeostatic_rate = 0.0 if args.no_homeostasis else 1.0
            cfg_ep.temporal_plasticity_enabled = False

            results = {}
            for arm in arm_names:
                sched = _make_schedule(arm, args.gap, pair_interval, args.num_pairs)
                r = _run_gated(cfg_ep, total_steps, sched, tau_trace=tau,
                               target_l1=args.target, gate_mode=gmode,
                               trace_gate_ref=args.trace_gate_ref,
                               gate_power=args.gate_power,
                               threshold=args.threshold,
                               mode="event_pair", arm=arm)
                r["rest_window"] = rest; r["gate_mode"] = gmode
                r["trace_gate_ref"] = args.trace_gate_ref
                r["gate_power"] = args.gate_power
                results[arm] = r

            # Print per-arm summary
            for arm in arm_names:
                r = results[arm]
                print(f"  [{gmode:>18s}] {arm:>20s}  "
                      f"DI={r['final_DI']:+.6e}  "
                      f"within={r['within_total']:.2e}  "
                      f"cross={r['cross_total']:.2e}  "
                      f"contam={r['contamination_ratio']:.3f}  "
                      f"gate_w={r['mean_gate_within']:.3f}  "
                      f"gate_c={r['mean_gate_cross']:.3f}  "
                      f"trace_mass={r['mean_trace_mass']:.2e}")

            # Compute cross-arm metrics
            ltr = results.get("L_then_R", {})
            rtl = results.get("R_then_L", {})
            sim = results.get("simultaneous", {})
            sep = results.get("separated_control", {})

            acc_dW_OS = (ltr.get("acc_dW_DI", 0) - rtl.get("acc_dW_DI", 0)) if ltr and rtl else 0.0
            final_OS = (ltr.get("final_DI", 0) - rtl.get("final_DI", 0)) if ltr and rtl else 0.0

            print(f"  {'':>20s}  acc_dW_OS={acc_dW_OS:+.4e}  "
                  f"final_OS={final_OS:+.2e}  OFF_OS={off_OS:+.2e}")

            # Build CSV rows
            for arm in arm_names:
                r = results[arm]
                d = r["final_readout"]["directional"]
                all_rows.append({
                    "seed": args.seed, "gap": args.gap, "tau_trace": tau,
                    "rest_window": rest, "gate_mode": gmode,
                    "trace_gate_ref": args.trace_gate_ref,
                    "gate_power": args.gate_power,
                    "arm": arm, "target_event_update_l1": args.target,
                    "event_count_L": r["event_count_L"],
                    "event_count_R": r["event_count_R"],
                    "schedule_ok": (r["event_count_L"] == args.num_pairs and
                                    r["event_count_R"] == args.num_pairs),
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
                    "L_to_R_l1": d["L_to_R_l1"],
                    "R_to_L_l1": d["R_to_L_l1"],
                    "runtime_s": time.time() - t0,
                })
                summary_arms.append(r)

    # ── Final summary table ──
    wall_s = time.time() - t0
    print(f"\n{'='*100}")
    print(f"9C.1C — Trace-Gated Update Summary")
    print(f"{'='*100}")
    header = (f"  {'rest':>6s} {'gate_mode':>18s} {'arm':>20s} "
              f"{'trace_mass':>12s} {'gate_w':>7s} {'gate_c':>7s} "
              f"{'within':>10s} {'cross':>10s} {'contam':>7s} "
              f"{'acc_DI':>10s} {'final_DI':>12s}")
    print(header)
    print(f"  {'-'*130}")

    for rest in rest_windows:
        for gmode in gate_modes:
            for arm in arm_names:
                matches = [r for r in summary_arms
                          if r.get("rest_window") == rest
                          and r.get("gate_mode") == gmode
                          and r.get("arm") == arm]
                if matches:
                    r = matches[0]
                    print(f"  {rest:>6d} {gmode:>18s} {arm:>20s} "
                          f"{r['mean_trace_mass']:>12.2e} "
                          f"{r['mean_gate_within']:>7.3f} {r['mean_gate_cross']:>7.3f} "
                          f"{r['within_total']:>10.2e} {r['cross_total']:>10.2e} "
                          f"{r['contamination_ratio']:>7.4f} "
                          f"{r['acc_dW_DI']:>+10.4f} {r['final_DI']:>+12.6e}")

    # Sanity
    has_nan = any(np.isnan(r["final_DI"]) for r in summary_arms if isinstance(r.get("final_DI"), float))
    print(f"\n  NaN: {'YES [WARN]' if has_nan else 'none'}")
    print(f"  Wall time: {wall_s:.1f}s")

    # ── CSV ──
    if args.output_csv and all_rows:
        with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
            w.writeheader()
            w.writerows(all_rows)

    # ── JSON ──
    if args.summary_json:
        summary = {
            "experiment": "phase9C1C_trace_gated_update",
            "params": {
                "seed": args.seed, "gap": args.gap, "tau_trace": tau,
                "num_pairs": args.num_pairs, "target": args.target,
                "trace_gate_ref": args.trace_gate_ref,
                "gate_power": args.gate_power,
                "threshold": args.threshold,
            },
            "arms": [],
        }
        for r in summary_arms:
            entry = {
                "rest_window": r.get("rest_window"),
                "gate_mode": r.get("gate_mode"),
                "arm": r.get("arm"),
                "final_DI": r.get("final_DI"),
                "acc_dW_DI": r.get("acc_dW_DI"),
                "contamination_ratio": r.get("contamination_ratio"),
                "mean_trace_mass": r.get("mean_trace_mass"),
                "mean_gate_within": r.get("mean_gate_within"),
                "mean_gate_cross": r.get("mean_gate_cross"),
                "within_total": r.get("within_total"),
                "cross_total": r.get("cross_total"),
            }
            summary["arms"].append(entry)
        with open(args.summary_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False, default=str)

    print(f"\nDone. CSV: {args.output_csv}  JSON: {args.summary_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
