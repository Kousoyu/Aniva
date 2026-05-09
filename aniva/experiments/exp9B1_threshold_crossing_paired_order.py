"""Phase 9B.1: Threshold-Crossing Temporal Plasticity — Paired-Order Assay.

Tests whether discrete threshold-crossing events can distinguish L→R order
from R→L order, where both EMA-based formulas (activity and onset) failed.

Four modes:
  OFF:                temporal_plasticity_enabled=False
  activity:           EMA activation trace eligibility (9A baseline)
  onset:              EMA onset trace eligibility (9A.4 baseline)
  threshold_crossing: discrete crossing-event eligibility (9B target)

Four arms (identical total stimulation):
  L_then_R:          L pulse → gap → R pulse
  R_then_L:          R pulse → gap → L pulse
  simultaneous:       L+R same time
  separated_control:  L then R with long gap

Crossing diagnostics (10 metrics from design doc Section 5.2):
  1-4: structural (same as 9A.3/9A.4)
  5: crossing count per unit (min, median, max)
  6: crossing count by threshold quartile (Q4/Q1 ratio)
  7: fraction of steps with >=1 crossing
  8: mean inter-crossing interval
  9: crossing count L-region vs R-region
  10: crossing balance L vs R

Language discipline: no "preference", "reward", "choice", "agent".
"""
import argparse, csv, json, sys
import numpy as np

from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.environment.environment import Stimulus, StimulusEvent

L_STIM = Stimulus(position=(-0.5, 0.0, 0.0), intensity=0.02, radius=0.5)
R_STIM = Stimulus(position=(0.5, 0.0, 0.0), intensity=0.02, radius=0.5)

PULSE_DURATION = 80
PAIR_GAP = 80
PAIR_INTERVAL = 600


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
    """Compute 10 crossing diagnostic metrics (Section 5.2)."""
    n_units = core.config.unit_count
    positions = core._positions
    thresholds = core._thresholds

    # 5. Crossing count per unit distribution
    cc = crossing_counts
    cc_min = int(np.min(cc))
    cc_max = int(np.max(cc))
    cc_median = float(np.median(cc))
    cc_mean = float(np.mean(cc))

    # 6. Crossing count by threshold quartile
    q_edges = np.percentile(thresholds, [0, 25, 50, 75, 100])
    q_labels = ["Q1", "Q2", "Q3", "Q4"]
    quartile_bins = np.digitize(thresholds, q_edges[1:-1], right=True)  # 0=Q1, 1=Q2, 2=Q3, 3=Q4
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

    # 7. Fraction of steps with >=1 crossing
    frac_steps_with_crossing = float(np.mean(crossing_steps_mask))

    # 8. Mean inter-crossing interval (estimated from mean crossing rate)
    mean_interval = total_steps / cc_mean if cc_mean > 0 else float('inf')

    # 9. Crossing count L-region vs R-region
    l_mask = positions[:, 0] < -0.1
    r_mask = positions[:, 0] > 0.1
    cc_l = int(np.sum(cc[l_mask]))
    cc_r = int(np.sum(cc[r_mask]))
    n_l = int(np.sum(l_mask))
    n_r = int(np.sum(r_mask))

    # 10. Crossing balance L vs R
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


def _make_schedule(steps, order):
    events = []
    pair_start = 0
    while pair_start + PULSE_DURATION < steps:
        if order == "L_then_R":
            events.append((pair_start, "L", PULSE_DURATION))
            events.append((pair_start + PAIR_GAP, "R", PULSE_DURATION))
        elif order == "R_then_L":
            events.append((pair_start, "R", PULSE_DURATION))
            events.append((pair_start + PAIR_GAP, "L", PULSE_DURATION))
        elif order == "simultaneous":
            events.append((pair_start, "L", PULSE_DURATION))
            events.append((pair_start, "R", PULSE_DURATION))
        elif order == "separated_control":
            events.append((pair_start, "L", PULSE_DURATION))
            events.append((pair_start + PAIR_INTERVAL // 2, "R", PULSE_DURATION))
        pair_start += PAIR_INTERVAL
    return sorted(events, key=lambda x: x[0])


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


def _cos(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(np.dot(a, b) / (na * nb)) if na > 0 and nb > 0 else 0.0


def _l1(a, b): return float(np.mean(np.abs(a - b)))


def main(argv=None):
    # Ensure unbuffered output even when stdout is redirected to a file on Windows
    import sys as _sys
    _sys.stdout.reconfigure(line_buffering=True)

    p = argparse.ArgumentParser(description="Phase 9B.1: Threshold-Crossing Temporal Plasticity — Paired-Order Assay")
    p.add_argument("--steps", type=int, default=20000)
    p.add_argument("--seeds", type=int, nargs="+", default=[42, 77, 123, 999])
    p.add_argument("--beta", type=float, default=0.5)
    p.add_argument("--decay", type=float, default=0.05)
    p.add_argument("--crossing-window", type=int, default=200)
    p.add_argument("--crossing-strength", type=float, default=0.5)
    p.add_argument("--output-csv", type=str, default="results/phase9B1_threshold_crossing_paired_order_20k.csv")
    p.add_argument("--summary-json", type=str, default="results/phase9B1_threshold_crossing_paired_order_20k_summary.json")
    p.add_argument("--no-homeostasis", action="store_true")
    args = p.parse_args(argv)

    arm_names = ["L_then_R", "R_then_L", "simultaneous", "separated_control"]
    modes = ["OFF", "activity", "onset", "threshold_crossing"]

    print(f"Phase 9B.1: Threshold-Crossing Temporal Plasticity — Paired-Order Assay")
    print(f"  seeds={args.seeds}  steps={args.steps}  beta={args.beta}  decay={args.decay}")
    print(f"  crossing_window={args.crossing_window}  crossing_strength={args.crossing_strength}")
    print(f"  gap={PAIR_GAP}  interval={PAIR_INTERVAL}  pulse_dur={PULSE_DURATION}")
    print(f"  modes: {' | '.join(modes)}  ({len(args.seeds)} × {len(modes)} × {len(arm_names)} = {len(args.seeds)*len(modes)*len(arm_names)} arm-runs)")
    print()

    all_results = []

    for mode in modes:
        temporal_on = mode != "OFF"
        is_crossing_mode = mode == "threshold_crossing"
        is_activity = mode == "activity"
        is_onset = mode == "onset"
        print(f"{'='*70}\n  {mode}\n{'='*70}")

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
                sched = _make_schedule(args.steps, arm)
                collect = is_crossing_mode
                r = _run_schedule(cfg, args.steps, sched, collect_crossings=collect)
                r["arm"], r["seed"], r["mode"] = arm, seed, mode
                all_results.append(r)

            sres = {r["arm"]: r for r in all_results
                    if r["seed"] == seed and r["mode"] == mode}
            ltr = sres.get("L_then_R", {}).get("readout", {}).get("directional", {})
            rtl = sres.get("R_then_L", {}).get("readout", {}).get("directional", {})
            asym_ltr = ltr.get("L_to_R_signed_mean", 0) - ltr.get("R_to_L_signed_mean", 0)
            asym_rtl = rtl.get("L_to_R_signed_mean", 0) - rtl.get("R_to_L_signed_mean", 0)

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
            print(f"  s={seed:>4d}  ev={sres['L_then_R']['total_events']:>3d}  "
                  f"asym(L→R-R→L): L_then_R={asym_ltr:>+10.3e}  "
                  f"R_then_L={asym_rtl:>+10.3e}  "
                  f"|diff|={abs(asym_ltr-asym_rtl):.3e}{extra}")
        print()

    # ── KEY: L_then_R vs R_then_L directional comparison ──
    print(f"{'='*100}")
    print(f"Phase 9B.1 — KEY RESULT: L_then_R vs R_then_L by mode")
    print(f"{'='*100}")

    for mode in modes:
        print(f"\n--- {mode} ---")
        print(f"{'seed':>5s} {'cos':>12s} {'|L1|':>14s} {'|L2|':>14s} "
              f"{'asym(L_then_R)':>16s} {'asym(R_then_L)':>16s} {'|asym_diff|':>14s}")
        print("-" * 90)

        for seed in args.seeds:
            sres = {r["arm"]: r for r in all_results
                    if r["seed"] == seed and r["mode"] == mode}
            ltr = sres.get("L_then_R"); rtl = sres.get("R_then_L")
            if ltr is None or rtl is None: continue

            dv_ltr = np.array(ltr["readout"]["delta_vector"])
            dv_rtl = np.array(rtl["readout"]["delta_vector"])
            c = _cos(dv_ltr, dv_rtl)
            l1 = _l1(dv_ltr, dv_rtl)
            l2 = float(np.sqrt(np.mean((dv_ltr - dv_rtl) ** 2)))

            d_ltr = ltr["readout"]["directional"]
            d_rtl = rtl["readout"]["directional"]
            asym_ltr = d_ltr["L_to_R_signed_mean"] - d_ltr["R_to_L_signed_mean"]
            asym_rtl = d_rtl["L_to_R_signed_mean"] - d_rtl["R_to_L_signed_mean"]

            print(f"{seed:>5d} {c:>12.8f} {l1:>14.6e} {l2:>14.6e} "
                  f"{asym_ltr:>+16.6e} {asym_rtl:>+16.6e} {abs(asym_ltr - asym_rtl):>14.6e}")

    # ── Directional asymmetry by arm and mode ──
    print(f"\n{'='*90}")
    print(f"Phase 9B.1 — Directional Asymmetry: L→R sgn - R→L sgn")
    print(f"{'='*90}")

    for mode in modes:
        print(f"\n--- {mode} ---")
        print(f"{'seed':>5s} {'L_then_R':>14s} {'R_then_L':>14s} {'simultaneous':>14s} "
              f"{'separated':>14s} {'L>R - R>L':>14s}")
        print("-" * 75)

        for seed in args.seeds:
            sres = {r["arm"]: r for r in all_results
                    if r["seed"] == seed and r["mode"] == mode}
            asyms = {}
            for arm in arm_names:
                d = sres.get(arm, {}).get("readout", {}).get("directional", {})
                asyms[arm] = d.get("L_to_R_signed_mean", 0) - d.get("R_to_L_signed_mean", 0)
            diff = asyms.get("L_then_R", 0) - asyms.get("R_then_L", 0)
            print(f"{seed:>5d} {asyms.get('L_then_R', 0):>+14.6e} {asyms.get('R_then_L', 0):>+14.6e} "
                  f"{asyms.get('simultaneous', 0):>+14.6e} {asyms.get('separated_control', 0):>+14.6e} "
                  f"{diff:>+14.6e}")

    # ── Cross-mode comparison ──
    print(f"\n{'='*95}")
    print(f"Phase 9B.1 — Mode Comparison: which best separates L_then_R from R_then_L?")
    print(f"{'='*95}")
    header = f"{'seed':>5s} {'OFF |L1|':>14s} {'activity |L1|':>14s} {'onset |L1|':>14s} {'crossing |L1|':>16s} "
    header += f"{'OFF asym':>14s} {'act asym':>14s} {'ons asym':>14s} {'xing asym':>14s}"
    print(header)
    print("-" * len(header))

    for seed in args.seeds:
        vals = {}
        for mode in modes:
            sres = {r["arm"]: r for r in all_results
                    if r["seed"] == seed and r["mode"] == mode}
            ltr = sres.get("L_then_R"); rtl = sres.get("R_then_L")
            if ltr is None or rtl is None: continue
            l1 = _l1(np.array(ltr["readout"]["delta_vector"]),
                     np.array(rtl["readout"]["delta_vector"]))
            d_ltr = ltr["readout"]["directional"]
            d_rtl = rtl["readout"]["directional"]
            asym_diff = abs((d_ltr["L_to_R_signed_mean"] - d_ltr["R_to_L_signed_mean"]) -
                           (d_rtl["L_to_R_signed_mean"] - d_rtl["R_to_L_signed_mean"]))
            vals[mode] = {"l1": l1, "asym_diff": asym_diff}

        def _v(m, k): return vals.get(m, {}).get(k, 0)
        print(f"{seed:>5d} {_v('OFF','l1'):>14.6e} {_v('activity','l1'):>14.6e} "
              f"{_v('onset','l1'):>14.6e} {_v('threshold_crossing','l1'):>16.6e} "
              f"{_v('OFF','asym_diff'):>+14.6e} {_v('activity','asym_diff'):>+14.6e} "
              f"{_v('onset','asym_diff'):>+14.6e} {_v('threshold_crossing','asym_diff'):>+14.6e}")

    # ── Crossing diagnostics ──
    print(f"\n{'='*90}")
    print(f"Phase 9B.1 — Crossing Diagnostics (threshold_crossing mode only)")
    print(f"{'='*90}")

    for seed in args.seeds:
        for arm in arm_names:
            r = next((r for r in all_results
                      if r["seed"] == seed and r["arm"] == arm and r["mode"] == "threshold_crossing"), None)
            if r is None: continue
            cd = r.get("crossing_diagnostics")
            if cd is None: continue
            cpu = cd["crossing_per_unit"]
            tqb = cd["threshold_quartile_bias"]
            cl = cd["crossing_l_region"]
            cr = cd["crossing_r_region"]
            print(f"\n  s={seed}  arm={arm}")
            print(f"    crossings/unit: min={cpu['min']}  median={cpu['median']:.1f}  "
                  f"mean={cpu['mean']:.1f}  max={cpu['max']}")
            print(f"    frac steps with >=1 crossing: {cd['frac_steps_with_crossing']:.4f}")
            print(f"    mean inter-crossing interval: {cd['mean_inter_crossing_interval']:.1f} steps")
            print(f"    L-region: {cl['count']} crossings ({cl['n_units']} units, {cl['per_unit']:.1f}/unit)")
            print(f"    R-region: {cr['count']} crossings ({cr['n_units']} units, {cr['per_unit']:.1f}/unit)")
            print(f"    balance (L-R)/(L+R): {cd['crossing_balance_lr']:+.4f}")
            print(f"    Q4/Q1 threshold crossing ratio: {tqb['q4_q1_ratio']:.4f}"
                  + ("  ⚠ BIAS" if tqb.get("bias_warning") else ""))
            for ql in ["Q1", "Q2", "Q3", "Q4"]:
                qd = tqb["quartiles"][ql]
                print(f"      {ql}: thr=[{qd['threshold_range'][0]:.3f}, {qd['threshold_range'][1]:.3f}]  "
                      f"n={qd['n_units']:>3d}  crossings/unit={qd['crossing_mean']:.1f}")

    # Save
    if args.output_csv:
        rows = []
        for r in all_results:
            d = r["readout"]["directional"]
            row = {"seed": r["seed"], "mode": r["mode"], "arm": r["arm"],
                   "total_events": r["total_events"],
                   "event_count_L": r["event_count_L"], "event_count_R": r["event_count_R"],
                   "final_weight_l1": r["final_weight_l1"],
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
            "seed", "mode", "arm", "total_events", "event_count_L", "event_count_R",
            "final_weight_l1",
            "L_to_R_signed_mean", "R_to_L_signed_mean", "L_to_R_l1", "R_to_L_l1",
            "crossing_per_unit_mean", "crossing_per_unit_median",
            "crossing_per_unit_min", "crossing_per_unit_max",
            "frac_steps_with_crossing", "mean_inter_crossing_interval",
            "crossing_balance_lr", "crossing_q4_q1_ratio",
        ]
        with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames); w.writeheader(); w.writerows(rows)
    if args.summary_json:
        summary = {"experiment": "phase9B1_threshold_crossing_paired_order",
                   "params": {"steps": args.steps, "seeds": args.seeds,
                              "beta": args.beta, "decay": args.decay,
                              "crossing_window": args.crossing_window,
                              "crossing_strength": args.crossing_strength,
                              "pulse_duration": PULSE_DURATION, "pair_gap": PAIR_GAP,
                              "pair_interval": PAIR_INTERVAL}, "arms": []}
        for r in all_results:
            entry = {"seed": r["seed"], "arm": r["arm"], "mode": r["mode"],
                     "event_count_L": r["event_count_L"], "event_count_R": r["event_count_R"],
                     "total_events": r["total_events"], "final_weight_l1": r["final_weight_l1"]}
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
