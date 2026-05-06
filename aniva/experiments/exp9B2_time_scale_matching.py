"""Phase 9B.2: Time-Scale Matching — Paired-Pulse Gap Sweep.

Tests whether aligning paired-pulse gap with crossing-event timescale
enables threshold-crossing eligibility to distinguish L→R from R→L order.

Single knob: paired-pulse gap ∈ {80, 500, 1000, 1500}.
Threshold-crossing mechanism and all other parameters unchanged from 9B.1.

Scheduling: each gap gets a dynamic pair_interval to ensure clean non-overlapping
paired-pulse structure:
  pair_interval = gap + pulse_duration + rest_window
  steps = warmup + num_pairs * pair_interval + tail_buffer

Design doc: docs/phase9B2_time_scale_matching_design.md
"""

import argparse, csv, json, sys
import numpy as np

from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.environment.environment import Stimulus, StimulusEvent

L_STIM = Stimulus(position=(-0.5, 0.0, 0.0), intensity=0.02, radius=0.5)
R_STIM = Stimulus(position=(0.5, 0.0, 0.0), intensity=0.02, radius=0.5)

PULSE_DURATION = 80
WARMUP = 200
TAIL_BUFFER = 200


def _classify_connection(sp, tp):
    s = "L" if sp[0] < -0.1 else ("R" if sp[0] > 0.1 else "M")
    t = "L" if tp[0] < -0.1 else ("R" if tp[0] > 0.1 else "M")
    return f"{s}→{t}"


def _structural_readout(core, w0):
    conns = list(core.connections)
    wf = np.array([c.weight for c in conns], dtype=np.float64)
    deltas = wf - w0
    regions = [_classify_connection(core.units[c.source_id].position,
                                     core.units[c.target_id].position) for c in conns]
    uregs = sorted(set(regions))
    absd = np.abs(deltas)
    regional = {}
    for reg in uregs:
        m = np.array([r == reg for r in regions])
        rd = deltas[m]
        regional[reg] = {"count": int(np.sum(m)),
                         "l1": float(np.mean(np.abs(rd))) if len(rd) > 0 else 0.0,
                         "signed_mean": float(np.mean(rd)) if len(rd) > 0 else 0.0}
    l_in = np.array(["→L" in r for r in regions])
    l_out = np.array(["L→" in r for r in regions])
    r_in = np.array(["→R" in r for r in regions])
    r_out = np.array(["R→" in r for r in regions])
    within = np.array([r in ("L→L", "R→R") for r in regions])
    cross = np.array([r in ("L→R", "R→L") for r in regions])
    def _s(a, m): return float(np.mean(np.abs(a[m]))) if m.any() else 0.0
    return {
        "global_l1": float(np.mean(absd)), "signed_mean": float(np.mean(deltas)),
        "regional": regional,
        "aggregated": {
            "L_in": _s(absd, l_in), "L_out": _s(absd, l_out),
            "R_in": _s(absd, r_in), "R_out": _s(absd, r_out),
            "within": _s(absd, within), "cross": _s(absd, cross),
        },
        "directional": {
            "L_to_R_signed_mean": regional.get("L→R", {}).get("signed_mean", 0.0),
            "R_to_L_signed_mean": regional.get("R→L", {}).get("signed_mean", 0.0),
            "L_to_R_l1": regional.get("L→R", {}).get("l1", 0.0),
            "R_to_L_l1": regional.get("R→L", {}).get("l1", 0.0),
        },
        "delta_vector": deltas.tolist(), "n_connections": len(deltas),
    }


def _crossing_diagnostics(core, crossing_counts, crossing_steps_mask, total_steps):
    n_units = core.config.unit_count
    positions = core._positions
    thresholds = core._thresholds
    cc = crossing_counts
    cc_min = int(np.min(cc))
    cc_max = int(np.max(cc))
    cc_median = float(np.median(cc))
    cc_mean = float(np.mean(cc))
    q_edges = np.percentile(thresholds, [0, 25, 50, 75, 100])
    q_labels = ["Q1", "Q2", "Q3", "Q4"]
    quartile_bins = np.digitize(thresholds, q_edges[1:-1], right=True)
    quartile_crossings = {}
    for qi, ql in enumerate(q_labels):
        mask = quartile_bins == qi
        qc = cc[mask]
        quartile_crossings[ql] = {
            "n_units": int(np.sum(mask)),
            "threshold_range": [float(q_edges[qi]), float(q_edges[qi + 1])],
            "crossing_mean": float(np.mean(qc)) if len(qc) > 0 else 0.0,
            "crossing_sum": int(np.sum(qc)),
        }
    q1_mean = quartile_crossings["Q1"]["crossing_mean"]
    q4_mean = quartile_crossings["Q4"]["crossing_mean"]
    q4_q1_ratio = q4_mean / q1_mean if q1_mean > 0 else 0.0
    frac_steps_with_crossing = float(np.mean(crossing_steps_mask))
    mean_interval = total_steps / cc_mean if cc_mean > 0 else float('inf')
    l_mask = positions[:, 0] < -0.1
    r_mask = positions[:, 0] > 0.1
    cc_l = int(np.sum(cc[l_mask]))
    cc_r = int(np.sum(cc[r_mask]))
    n_l = int(np.sum(l_mask))
    n_r = int(np.sum(r_mask))
    balance = (cc_l - cc_r) / (cc_l + cc_r) if (cc_l + cc_r) > 0 else 0.0
    return {
        "crossing_per_unit": {"min": cc_min, "median": cc_median, "max": cc_max, "mean": cc_mean},
        "threshold_quartile_bias": {
            "quartiles": quartile_crossings,
            "q4_q1_ratio": float(q4_q1_ratio),
            "bias_warning": q4_q1_ratio < 0.1,
        },
        "frac_steps_with_crossing": float(frac_steps_with_crossing),
        "mean_inter_crossing_interval": float(mean_interval),
        "crossing_l_region": {"count": cc_l, "n_units": n_l, "per_unit": float(cc_l / n_l) if n_l > 0 else 0.0},
        "crossing_r_region": {"count": cc_r, "n_units": n_r, "per_unit": float(cc_r / n_r) if n_r > 0 else 0.0},
        "crossing_balance_lr": float(balance),
    }


def _make_schedule(order, pair_gap, pair_interval, num_pairs):
    """Build clean non-overlapping paired-pulse schedule.

    Each pair i starts at warmup + i * pair_interval.
    pair_interval >= gap + pulse_dur + rest_window ensures no overlap.
    """
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
            # Put R at half the pair interval — always within the pair window
            events.append((pair_start, "L", PULSE_DURATION))
            events.append((pair_start + pair_interval // 2, "R", PULSE_DURATION))
    return sorted(events, key=lambda x: x[0])


def _compute_scheduling_params(gap, num_pairs, rest_window):
    pair_interval = gap + PULSE_DURATION + rest_window
    total_steps = WARMUP + num_pairs * pair_interval + TAIL_BUFFER
    return pair_interval, total_steps


def _influences_at_step(active_events, step, core):
    inf = {}
    for ev in active_events:
        if ev.start_step <= step < ev.start_step + ev.duration_steps:
            for uid, u in core.units.items():
                d = np.linalg.norm(np.array(u.position) - np.array(ev.stimulus.position))
                if d <= ev.stimulus.radius:
                    v = ev.stimulus.intensity * (1.0 - d / ev.stimulus.radius)
                    inf[uid] = inf.get(uid, 0.0) + v
    return inf if inf else None


def _run_schedule(cfg, steps, schedule, collect_crossings=False):
    core = LifeCore(cfg)
    w0 = np.array([c.weight for c in core.connections], dtype=np.float64)
    elog, aevs = [], []; idx = 0
    n_units = cfg.unit_count
    crossing_counts = np.zeros(n_units, dtype=np.int64) if collect_crossings else None
    crossing_steps = np.zeros(steps, dtype=bool) if collect_crossings else None
    for s in range(steps):
        while idx < len(schedule) and schedule[idx][0] <= s:
            t, lb, dur = schedule[idx]
            if t == s:
                stim = L_STIM if lb == "L" else R_STIM
                aevs.append(StimulusEvent(stimulus=stim, start_step=s, duration_steps=dur))
                elog.append({"step": s, "side": lb, "duration": dur})
            idx += 1
        core.step(env_influences=_influences_at_step(aevs, s, core))
        if collect_crossings and cfg.temporal_plasticity_enabled and cfg.temporal_eligibility_mode == "threshold_crossing":
            is_cross = core._is_crossing
            crossing_counts += is_cross.astype(np.int64)
            if np.any(is_cross):
                crossing_steps[s] = True
    result = _pack(core, w0, elog)
    if collect_crossings:
        result["crossing_diagnostics"] = _crossing_diagnostics(core, crossing_counts, crossing_steps, steps)
    return result


def _pack(core, w0, elog):
    nL = sum(1 for e in elog if e["side"] == "L")
    nR = sum(1 for e in elog if e["side"] == "R")
    return {
        "event_log": elog, "total_events": len(elog),
        "event_count_L": nL, "event_count_R": nR,
        "final_weight_l1": float(np.mean(np.abs(
            np.array([c.weight for c in core.connections]) - w0))),
        "readout": _structural_readout(core, w0),
    }


def _schedule_diagnostics(schedule, num_pairs, pair_interval):
    """Extract scheduling verification info from event list."""
    l_steps = sorted([t for t, lb, d in schedule if lb == "L"])
    r_steps = sorted([t for t, lb, d in schedule if lb == "R"])
    completed = min(len(l_steps), len(r_steps))
    return {
        "pair_interval": pair_interval,
        "num_pairs_target": num_pairs,
        "completed_pairs": completed,
        "first_L_step": l_steps[0] if l_steps else -1,
        "first_R_step": r_steps[0] if r_steps else -1,
        "last_L_step": l_steps[-1] if l_steps else -1,
        "last_R_step": r_steps[-1] if r_steps else -1,
    }


def _cos(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(np.dot(a, b) / (na * nb)) if na > 0 and nb > 0 else 0.0


def _l1(a, b): return float(np.mean(np.abs(a - b)))


def main(argv=None):
    import sys as _sys
    _sys.stdout.reconfigure(line_buffering=True)

    p = argparse.ArgumentParser(description="Phase 9B.2: Time-Scale Matching — Gap Sweep")
    p.add_argument("--num-pairs", type=int, default=30,
                   help="Number of pulse pairs per arm (default: 30, ~20k steps)")
    p.add_argument("--rest-window", type=int, default=500,
                   help="Rest steps between end of pair N and start of pair N+1 (default: 500)")
    p.add_argument("--seeds", type=int, nargs="+", default=[42, 77, 123, 999])
    p.add_argument("--gaps", type=int, nargs="+", default=[80, 500, 1000, 1500])
    p.add_argument("--beta", type=float, default=0.5)
    p.add_argument("--decay", type=float, default=0.05)
    p.add_argument("--crossing-window", type=int, default=200)
    p.add_argument("--crossing-strength", type=float, default=0.5)
    p.add_argument("--output-csv", type=str, default="results/phase9B2_time_scale_matching.csv")
    p.add_argument("--summary-json", type=str, default="results/phase9B2_time_scale_matching_summary.json")
    p.add_argument("--no-homeostasis", action="store_true")
    args = p.parse_args(argv)

    arm_names = ["L_then_R", "R_then_L", "simultaneous", "separated_control"]
    modes = ["OFF", "activity", "onset", "threshold_crossing"]

    n_seeds = len(args.seeds)
    n_gaps = len(args.gaps)
    n_modes = len(modes)
    n_arms = len(arm_names)
    total_runs = n_seeds * n_gaps * n_modes * n_arms

    # Pre-compute scheduling params per gap
    gap_params = {}
    for gap in args.gaps:
        pair_interval, total_steps = _compute_scheduling_params(gap, args.num_pairs, args.rest_window)
        gap_params[gap] = {"pair_interval": pair_interval, "total_steps": total_steps}

    print(f"Phase 9B.2: Time-Scale Matching — Paired-Pulse Gap Sweep")
    print(f"  seeds={args.seeds}  gaps={args.gaps}  num_pairs={args.num_pairs}")
    print(f"  rest_window={args.rest_window}  warmup={WARMUP}  tail_buffer={TAIL_BUFFER}")
    print(f"  beta={args.beta}  decay={args.decay}")
    print(f"  crossing_window={args.crossing_window}  crossing_strength={args.crossing_strength}")
    print(f"  pulse_dur={PULSE_DURATION}")
    print(f"  modes: {' | '.join(modes)}")
    print(f"  ({n_seeds} seeds × {n_gaps} gaps × {n_modes} modes × {n_arms} arms = {total_runs} arm-runs)")
    print()

    # Scheduling summary
    print(f"  Scheduling per gap:")
    for gap in args.gaps:
        pi = gap_params[gap]["pair_interval"]
        ts = gap_params[gap]["total_steps"]
        print(f"    gap={gap:>4d} → pair_interval={pi}  total_steps={ts}")
    print()

    all_results = []

    for gap in args.gaps:
        pair_interval = gap_params[gap]["pair_interval"]
        total_steps = gap_params[gap]["total_steps"]

        print(f"{'#'*70}\n  GAP = {gap} steps  (pair_interval={pair_interval}, steps={total_steps})\n{'#'*70}\n")

        for mode in modes:
            temporal_on = mode != "OFF"
            is_crossing_mode = mode == "threshold_crossing"
            is_activity = mode == "activity"
            is_onset = mode == "onset"
            print(f"{'='*70}\n  gap={gap}  mode={mode}\n{'='*70}")

            for seed in args.seeds:
                cfg = AnivaConfig(unit_count=300, seed=seed)
                cfg.homeostasis_enabled = not args.no_homeostasis
                cfg.homeostatic_target_abs_weight = 0.30
                cfg.homeostatic_rate = 1.0
                cfg.temporal_plasticity_enabled = temporal_on
                cfg.temporal_plasticity_rate = args.beta
                cfg.temporal_trace_decay = args.decay
                if is_activity:
                    cfg.temporal_eligibility_mode = "activity"
                elif is_onset:
                    cfg.temporal_eligibility_mode = "onset"
                elif is_crossing_mode:
                    cfg.temporal_eligibility_mode = "threshold_crossing"
                    cfg.temporal_crossing_window = args.crossing_window
                    cfg.temporal_crossing_strength = args.crossing_strength

                for arm in arm_names:
                    sched = _make_schedule(arm, gap, pair_interval, args.num_pairs)
                    collect = is_crossing_mode
                    r = _run_schedule(cfg, total_steps, sched, collect_crossings=collect)
                    r["arm"], r["seed"], r["mode"], r["gap"] = arm, seed, mode, gap
                    r["scheduling"] = _schedule_diagnostics(sched, args.num_pairs, pair_interval)
                    all_results.append(r)

                sres = {r["arm"]: r for r in all_results
                        if r["seed"] == seed and r["mode"] == mode and r["gap"] == gap}
                ltr = sres.get("L_then_R", {}).get("readout", {}).get("directional", {})
                rtl = sres.get("R_then_L", {}).get("readout", {}).get("directional", {})
                asym_ltr = ltr.get("L_to_R_signed_mean", 0) - ltr.get("R_to_L_signed_mean", 0)
                asym_rtl = rtl.get("L_to_R_signed_mean", 0) - rtl.get("R_to_L_signed_mean", 0)

                # Scheduling health check
                sched_info = sres.get("L_then_R", {}).get("scheduling", {})
                ev_ltr = sres["L_then_R"]["total_events"]
                ev_rtl = sres["R_then_L"]["total_events"]
                ev_ok = (ev_ltr == 2 * args.num_pairs and ev_rtl == 2 * args.num_pairs)
                sched_flag = "" if ev_ok else f"  [SCHED WARN] L_then_R ev={ev_ltr} R_then_L ev={ev_rtl} (expected {2*args.num_pairs})"

                extra = ""
                if is_crossing_mode:
                    cd = sres.get("L_then_R", {}).get("crossing_diagnostics", {})
                    if cd:
                        cpu = cd.get("crossing_per_unit", {})
                        bal = cd.get("crossing_balance_lr", 0)
                        qr = cd.get("threshold_quartile_bias", {}).get("q4_q1_ratio", 0)
                        extra = (f"  xing/unit={cpu.get('mean', 0):.1f}  "
                                 f"frac_steps={cd.get('frac_steps_with_crossing', 0):.4f}  "
                                 f"bal_LR={bal:+.4f}  Q4/Q1={qr:.3f}")
                print(f"  s={seed:>4d}  ev={ev_ltr:>3d}  "
                      f"asym(L→R-R→L): L_then_R={asym_ltr:>+10.3e}  "
                      f"R_then_L={asym_rtl:>+10.3e}  "
                      f"|diff|={abs(asym_ltr-asym_rtl):.3e}{extra}{sched_flag}")
            print()

    # ── Scheduling verification ──
    print(f"{'='*90}")
    print(f"Phase 9B.2 — Scheduling Verification")
    print(f"{'='*90}")
    print(f"  {'gap':>5s} {'arm':>18s} {'pair_interval':>14s} {'target_pairs':>13s} "
          f"{'completed':>10s} {'first_L':>8s} {'first_R':>8s} {'last_L':>8s} {'last_R':>8s} {'OK':>5s}")
    print(f"  {'-'*95}")
    for gap in args.gaps:
        for arm in arm_names:
            r = next((r for r in all_results
                      if r["arm"] == arm and r["mode"] == "OFF" and r["gap"] == gap), None)
            if r is None: continue
            sd = r.get("scheduling", {})
            ok = (r["event_count_L"] == args.num_pairs and r["event_count_R"] == args.num_pairs)
            print(f"  {gap:>5d} {arm:>18s} {sd.get('pair_interval', 0):>14d} "
                  f"{sd.get('num_pairs_target', 0):>13d} {sd.get('completed_pairs', 0):>10d} "
                  f"{sd.get('first_L_step', 0):>8d} {sd.get('first_R_step', 0):>8d} "
                  f"{sd.get('last_L_step', 0):>8d} {sd.get('last_R_step', 0):>8d} "
                  f"{'OK' if ok else 'FAIL':>5s}")

    # ── KEY RESULT: Gap × Mode comparison ──
    print(f"\n{'='*110}")
    print(f"Phase 9B.2 — KEY RESULT: |asym_diff| by gap × mode")
    print(f"{'='*110}")

    for gap in args.gaps:
        print(f"\n--- GAP = {gap} (pair_interval={gap_params[gap]['pair_interval']}) ---")
        header = f"{'seed':>5s} {'OFF':>14s} {'activity':>14s} {'onset':>14s} {'crossing':>14s}"
        print(header)
        print("-" * 70)
        for seed in args.seeds:
            vals = {}
            for mode in modes:
                sres = {r["arm"]: r for r in all_results
                        if r["seed"] == seed and r["mode"] == mode and r["gap"] == gap}
                ltr = sres.get("L_then_R"); rtl = sres.get("R_then_L")
                if ltr is None or rtl is None: continue
                d_ltr = ltr["readout"]["directional"]
                d_rtl = rtl["readout"]["directional"]
                asym_diff = abs((d_ltr["L_to_R_signed_mean"] - d_ltr["R_to_L_signed_mean"]) -
                               (d_rtl["L_to_R_signed_mean"] - d_rtl["R_to_L_signed_mean"]))
                vals[mode] = asym_diff
            print(f"{seed:>5d} {vals.get('OFF', 0):>+14.6e} {vals.get('activity', 0):>+14.6e} "
                  f"{vals.get('onset', 0):>+14.6e} {vals.get('threshold_crossing', 0):>+14.6e}")

    # ── Crossing diagnostics by gap ──
    print(f"\n{'='*90}")
    print(f"Phase 9B.2 — Crossing Diagnostics (threshold_crossing mode, by gap)")
    print(f"{'='*90}")

    for gap in args.gaps:
        print(f"\n  GAP = {gap} (pair_interval={gap_params[gap]['pair_interval']}, "
              f"steps={gap_params[gap]['total_steps']})")
        print(f"  {'seed':>5s} {'arm':>18s} {'xing/unit':>10s} {'frac_steps':>11s} "
              f"{'mean_interval':>14s} {'bal_LR':>9s} {'Q4/Q1':>7s}")
        print(f"  {'-'*75}")
        for seed in args.seeds:
            for arm in arm_names:
                r = next((r for r in all_results
                          if r["seed"] == seed and r["arm"] == arm
                          and r["mode"] == "threshold_crossing" and r["gap"] == gap), None)
                if r is None: continue
                cd = r.get("crossing_diagnostics")
                if cd is None: continue
                cpu = cd["crossing_per_unit"]
                print(f"  {seed:>5d} {arm:>18s} {cpu['mean']:>10.1f} "
                      f"{cd['frac_steps_with_crossing']:>11.4f} "
                      f"{cd['mean_inter_crossing_interval']:>14.1f} "
                      f"{cd['crossing_balance_lr']:>+9.4f} "
                      f"{cd['threshold_quartile_bias']['q4_q1_ratio']:>7.4f}")

    # ── Save CSV ──
    if args.output_csv:
        rows = []
        for r in all_results:
            d = r["readout"]["directional"]
            sd = r.get("scheduling", {})
            row = {"seed": r["seed"], "gap": r["gap"], "mode": r["mode"], "arm": r["arm"],
                   "total_events": r["total_events"],
                   "event_count_L": r["event_count_L"], "event_count_R": r["event_count_R"],
                   "final_weight_l1": r["final_weight_l1"],
                   "pair_interval": sd.get("pair_interval", 0),
                   "num_pairs_target": sd.get("num_pairs_target", 0),
                   "completed_pairs": sd.get("completed_pairs", 0),
                   "first_L_step": sd.get("first_L_step", -1),
                   "first_R_step": sd.get("first_R_step", -1),
                   "last_L_step": sd.get("last_L_step", -1),
                   "last_R_step": sd.get("last_R_step", -1),
                   "L_to_R_signed_mean": d["L_to_R_signed_mean"],
                   "R_to_L_signed_mean": d["R_to_L_signed_mean"],
                   "L_to_R_l1": d["L_to_R_l1"],
                   "R_to_L_l1": d["R_to_L_l1"]}
            cd = r.get("crossing_diagnostics")
            if cd:
                cpu = cd["crossing_per_unit"]
                tqb = cd["threshold_quartile_bias"]
                row.update({
                    "crossing_per_unit_mean": cpu["mean"],
                    "crossing_per_unit_median": cpu["median"],
                    "crossing_per_unit_min": cpu["min"],
                    "crossing_per_unit_max": cpu["max"],
                    "frac_steps_with_crossing": cd["frac_steps_with_crossing"],
                    "mean_inter_crossing_interval": cd["mean_inter_crossing_interval"],
                    "crossing_balance_lr": cd["crossing_balance_lr"],
                    "crossing_q4_q1_ratio": tqb["q4_q1_ratio"],
                })
            rows.append(row)
        fieldnames = [
            "seed", "gap", "mode", "arm",
            "total_events", "event_count_L", "event_count_R",
            "final_weight_l1",
            "pair_interval", "num_pairs_target", "completed_pairs",
            "first_L_step", "first_R_step", "last_L_step", "last_R_step",
            "L_to_R_signed_mean", "R_to_L_signed_mean", "L_to_R_l1", "R_to_L_l1",
            "crossing_per_unit_mean", "crossing_per_unit_median",
            "crossing_per_unit_min", "crossing_per_unit_max",
            "frac_steps_with_crossing", "mean_inter_crossing_interval",
            "crossing_balance_lr", "crossing_q4_q1_ratio",
        ]
        with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames); w.writeheader(); w.writerows(rows)

    # ── Save JSON ──
    if args.summary_json:
        summary = {"experiment": "phase9B2_time_scale_matching",
                   "params": {"num_pairs": args.num_pairs, "rest_window": args.rest_window,
                              "seeds": args.seeds, "gaps": args.gaps,
                              "beta": args.beta, "decay": args.decay,
                              "crossing_window": args.crossing_window,
                              "crossing_strength": args.crossing_strength,
                              "pulse_duration": PULSE_DURATION,
                              "warmup": WARMUP, "tail_buffer": TAIL_BUFFER},
                   "gap_scheduling": {str(gap): gap_params[gap] for gap in args.gaps},
                   "arms": []}
        for r in all_results:
            entry = {"seed": r["seed"], "gap": r["gap"], "arm": r["arm"], "mode": r["mode"],
                     "event_count_L": r["event_count_L"], "event_count_R": r["event_count_R"],
                     "total_events": r["total_events"], "final_weight_l1": r["final_weight_l1"],
                     "scheduling": r.get("scheduling", {})}
            ro = r.get("readout")
            if ro:
                entry["readout"] = {"global_l1": ro["global_l1"], "regional": ro["regional"],
                                    "aggregated": ro["aggregated"], "directional": ro["directional"]}
            cd = r.get("crossing_diagnostics")
            if cd:
                entry["crossing_diagnostics"] = cd
            summary["arms"].append(entry)
        with open(args.summary_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False, default=str)

    print(f"\nDone. {len(all_results)} arm-runs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
