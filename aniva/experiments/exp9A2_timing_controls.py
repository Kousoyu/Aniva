"""Phase 9A.2: Temporal Eligibility — 4-Arm Timing Controls.

Distinguishes the global plasticity shift caused by eligibility trace from
the specific signal of state-timed event feedback.

Four arms:
  open_loop_poisson:    Poisson events, no state feedback
  closed_loop_triggered: State-triggered events
  matched_time_shuffle:  Same events as triggered, times shuffled
  circular_shift:        Same events as triggered, times shifted by +N/2

Key question:
  With temporal eligibility ON, does closed_loop_triggered separate
  from matched_time_shuffle and circular_shift?

Language discipline: no "preference", "reward", "choice", "agent".
"""
import argparse, csv, json, sys
import numpy as np

from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.environment.environment import Stimulus, StimulusEvent

L_STIM = Stimulus(position=(-0.5, 0.0, 0.0), intensity=0.02, radius=0.5)
R_STIM = Stimulus(position=(0.5, 0.0, 0.0), intensity=0.02, radius=0.5)

EVENT_DURATION = 80
REFRACTORY = 400
SUSTAINED_WINDOW = 100
POISSON_MEAN_INTERVAL = 200
CALIB_STEPS = 2000
THRESHOLD_PERCENTILE = 85
SMOOTHING_ALPHA = 0.1


def _compute_imbalance(core):
    left_acts = [u.activation for uid, u in core.units.items() if u.position[0] < 0]
    right_acts = [u.activation for uid, u in core.units.items() if u.position[0] > 0]
    lm = float(np.mean(left_acts)) if left_acts else 0.0
    rm = float(np.mean(right_acts)) if right_acts else 0.0
    return lm, rm, lm - rm


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
    l_in = np.array(["→L" in r for r in regions]); l_out = np.array(["L→" in r for r in regions])
    r_in = np.array(["→R" in r for r in regions]); r_out = np.array(["R→" in r for r in regions])
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
        "delta_vector": deltas.tolist(), "n_connections": len(deltas),
    }


def _calibrate(cfg, pct, rng):
    core = LifeCore(cfg)
    vals = []
    for s in range(CALIB_STEPS):
        core.step(env_influences=None)
        if s >= 500: vals.append(abs(_compute_imbalance(core)[2]))
    return float(np.percentile(vals, pct))


def _poisson_stream(steps, mi, pL, rng):
    p = 1.0 / mi; evs = []
    for s in range(steps):
        if rng.random() < p:
            lb = "L" if rng.random() < pL else "R"
            evs.append({"step": s, "chosen": lb, "stimulus": L_STIM if lb == "L" else R_STIM, "duration": EVENT_DURATION})
    return evs


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


def _run_schedule(cfg, steps, schedule):
    """Run with pre-computed event schedule. Used by poisson, shuffle, shift."""
    core = LifeCore(cfg)
    w0 = np.array([c.weight for c in core.connections], dtype=np.float64)
    elog, aevs = [], []; idx = 0
    for s in range(steps):
        while idx < len(schedule) and schedule[idx][0] <= s:
            t, lb, dur = schedule[idx]
            if t == s:
                stim = L_STIM if lb == "L" else R_STIM
                aevs.append(StimulusEvent(stimulus=stim, start_step=s, duration_steps=dur))
                elog.append({"step": s, "chosen": lb, "duration": dur})
            idx += 1
        core.step(env_influences=_influences_at_step(aevs, s, core))
    return _pack(core, w0, elog)


def _run_triggered(cfg, steps, threshold, sw, refrac):
    core = LifeCore(cfg)
    w0 = np.array([c.weight for c in core.connections], dtype=np.float64)
    elog, aevs = [], []; simb, scnt, slast = 0.0, 0, refrac
    for s in range(steps):
        core.step(env_influences=_influences_at_step(aevs, s, core))
        _, _, raw = _compute_imbalance(core)
        simb = SMOOTHING_ALPHA * raw + (1 - SMOOTHING_ALPHA) * simb
        slast += 1; scnt = scnt + 1 if abs(simb) > threshold else 0
        if scnt >= sw and slast >= refrac:
            lb = "R" if simb > 0 else "L"; stim = R_STIM if simb > 0 else L_STIM
            aevs.append(StimulusEvent(stimulus=stim, start_step=s, duration_steps=EVENT_DURATION))
            elog.append({"step": s, "chosen": lb, "duration": EVENT_DURATION})
            scnt, slast = 0, 0
    return _pack(core, w0, elog)


def _pack(core, w0, elog):
    nL = sum(1 for e in elog if e["chosen"] == "L")
    nR = sum(1 for e in elog if e["chosen"] == "R")
    ieis = [elog[i+1]["step"]-elog[i]["step"] for i in range(len(elog)-1)]
    return {
        "event_log": elog, "total_events": len(elog),
        "event_count_L": nL, "event_count_R": nR,
        "mean_IEI": float(np.mean(ieis)) if ieis else 0.0,
        "final_weight_l1": float(np.mean(np.abs(
            np.array([c.weight for c in core.connections]) - w0))),
        "readout": _structural_readout(core, w0),
    }


def _cos(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(np.dot(a, b)/(na*nb)) if na > 0 and nb > 0 else 0.0

def _l1(a, b): return float(np.mean(np.abs(a - b)))


def main(argv=None):
    p = argparse.ArgumentParser(description="Phase 9A.2: 4-Arm Timing Controls")
    p.add_argument("--steps", type=int, default=20000)
    p.add_argument("--seeds", type=int, nargs="+", default=[42, 77, 123, 999])
    p.add_argument("--beta", type=float, default=0.5)
    p.add_argument("--decay", type=float, default=0.05)
    p.add_argument("--output-csv", type=str, default="results/phase9A2_timing_controls_20k.csv")
    p.add_argument("--summary-json", type=str, default="results/phase9A2_timing_controls_20k_summary.json")
    p.add_argument("--no-homeostasis", action="store_true")
    p.add_argument("--base-rng", type=int, default=20260504)
    args = p.parse_args(argv)

    print(f"Phase 9A.2: 4-Arm Timing Controls")
    print(f"  seeds={args.seeds}  steps={args.steps}  beta={args.beta}")
    print()

    all_results = []

    for temporal_on in [False, True]:
        label = "TEMPORAL ON" if temporal_on else "TEMPORAL OFF"
        print(f"{'='*70}\n  {label}\n{'='*70}")

        for seed in args.seeds:
            cfg = AnivaConfig(unit_count=300, seed=seed)
            cfg.homeostasis_enabled = not args.no_homeostasis
            cfg.homeostatic_target_abs_weight = 0.30
            cfg.homeostatic_rate = 1.0
            cfg.temporal_plasticity_enabled = temporal_on
            cfg.temporal_plasticity_rate = args.beta
            cfg.temporal_trace_decay = args.decay

            thr = _calibrate(cfg, THRESHOLD_PERCENTILE, np.random.default_rng(args.base_rng))
            ps = _poisson_stream(args.steps, POISSON_MEAN_INTERVAL, 0.5,
                                 np.random.default_rng(args.base_rng + seed))

            # Arm 1: open_loop_poisson
            ps_sched = [(e["step"], e["chosen"], e["duration"]) for e in ps]
            r_ol = _run_schedule(cfg, args.steps, ps_sched)
            r_ol["arm"], r_ol["seed"], r_ol["temporal"] = "open_loop_poisson", seed, temporal_on
            all_results.append(r_ol)

            # Arm 2: closed_loop_triggered (generates event log for arms 3 & 4)
            cfg.seed = seed
            r_cl = _run_triggered(cfg, args.steps, thr, SUSTAINED_WINDOW, REFRACTORY)
            r_cl["arm"], r_cl["seed"], r_cl["temporal"] = "closed_loop_triggered", seed, temporal_on
            all_results.append(r_cl)

            # Arm 3: matched_time_shuffle
            cl_times = [e["step"] for e in r_cl["event_log"]]
            rng_shuf = np.random.default_rng(args.base_rng + seed * 10 + 3)
            shuffled_times = cl_times.copy(); rng_shuf.shuffle(shuffled_times)
            ms_sched = sorted(
                [(shuffled_times[i], r_cl["event_log"][i]["chosen"], r_cl["event_log"][i]["duration"])
                 for i in range(len(cl_times))], key=lambda x: x[0])
            r_ms = _run_schedule(cfg, args.steps, ms_sched)
            r_ms["arm"], r_ms["seed"], r_ms["temporal"] = "matched_time_shuffle", seed, temporal_on
            all_results.append(r_ms)

            # Arm 4: circular_shift
            shift = args.steps // 2
            cs_sched = sorted(
                [((e["step"] + shift) % args.steps, e["chosen"], e["duration"])
                 for e in r_cl["event_log"]], key=lambda x: x[0])
            r_cs = _run_schedule(cfg, args.steps, cs_sched)
            r_cs["arm"], r_cs["seed"], r_cs["temporal"] = "circular_shift", seed, temporal_on
            all_results.append(r_cs)

            # Per-seed summary
            print(f"  s={seed:>4d}  ol={r_ol['total_events']:>4d}  cl={r_cl['total_events']:>4d}  "
                  f"ms={r_ms['total_events']:>4d}  cs={r_cs['total_events']:>4d}  "
                  f"|L1|(cl,ol)={_l1(np.array(r_cl['readout']['delta_vector']), np.array(r_ol['readout']['delta_vector'])):.4e}")
        print()

    # ── Cross-arm delta vector: full pair matrix ──
    print(f"{'='*100}")
    print(f"Phase 9A.2 — Delta Vector Pairwise Comparison")
    print(f"{'='*100}")

    arm_names = ["open_loop_poisson", "closed_loop_triggered", "matched_time_shuffle", "circular_shift"]

    for temporal_on in [False, True]:
        tlabel = "TEMPORAL ON" if temporal_on else "TEMPORAL OFF"
        print(f"\n--- {tlabel} ---")
        print(f"{'seed':>5s} {'pair':>35s}  {'cos':>12s} {'|L1|':>12s} {'|L2|':>12s}")
        print("-" * 82)

        for seed in args.seeds:
            sres = {r["arm"]: r for r in all_results
                    if r["seed"] == seed and r["temporal"] == temporal_on}
            for i in range(len(arm_names)):
                for j in range(i+1, len(arm_names)):
                    a_name, b_name = arm_names[i], arm_names[j]
                    a = sres.get(a_name); b = sres.get(b_name)
                    if a is None or b is None: continue
                    dv_a = np.array(a["readout"]["delta_vector"])
                    dv_b = np.array(b["readout"]["delta_vector"])
                    c = _cos(dv_a, dv_b); l1 = _l1(dv_a, dv_b)
                    l2 = float(np.sqrt(np.mean((dv_a - dv_b)**2)))
                    print(f"{seed:>5d} {f'{a_name} vs {b_name}':>35s}  "
                          f"{c:>12.8f} {l1:>12.6e} {l2:>12.6e}")

    # ── Key metric: cl-ms separation ──
    print(f"\n--- KEY METRIC: closed_loop vs matched_time_shuffle ---")
    print(f"{'seed':>5s} {'temporal':>9s} {'cos(cl,ms)':>14s} {'|cl-ms|_L1':>14s}")
    print("-" * 50)
    for seed in args.seeds:
        for t in [False, True]:
            sres = {r["arm"]: r for r in all_results if r["seed"] == seed and r["temporal"] == t}
            cl = sres.get("closed_loop_triggered"); ms = sres.get("matched_time_shuffle")
            if cl is None or ms is None: continue
            dv_cl = np.array(cl["readout"]["delta_vector"])
            dv_ms = np.array(ms["readout"]["delta_vector"])
            c = _cos(dv_cl, dv_ms); l = _l1(dv_cl, dv_ms)
            print(f"{seed:>5d} {'OFF' if not t else 'ON':>9s} {c:>14.8f} {l:>14.6e}")

    # ── Same-arm OFF vs ON global shift vs ON arm differences ──
    print(f"\n--- Global Shift vs Differential Signal ---")
    print(f"{'seed':>5s} {'same-arm off-on L1':>20s} {'ON cl-ms L1':>16s} {'ON cl-cs L1':>16s} {'ratio ms/global':>14s}")
    print("-" * 80)
    for seed in args.seeds:
        same_arm_l1s = []
        for arm in arm_names:
            r_off = next((r for r in all_results if r["seed"]==seed and r["arm"]==arm and not r["temporal"]), None)
            r_on = next((r for r in all_results if r["seed"]==seed and r["arm"]==arm and r["temporal"]), None)
            if r_off and r_on:
                same_arm_l1s.append(_l1(np.array(r_off["readout"]["delta_vector"]),
                                        np.array(r_on["readout"]["delta_vector"])))
        global_shift = float(np.mean(same_arm_l1s)) if same_arm_l1s else 0.0

        sres_on = {r["arm"]: r for r in all_results if r["seed"] == seed and r["temporal"]}
        cl_dv = np.array(sres_on["closed_loop_triggered"]["readout"]["delta_vector"])
        ms_dv = np.array(sres_on["matched_time_shuffle"]["readout"]["delta_vector"])
        cs_dv = np.array(sres_on["circular_shift"]["readout"]["delta_vector"])
        cl_ms_l1 = _l1(cl_dv, ms_dv); cl_cs_l1 = _l1(cl_dv, cs_dv)

        print(f"{seed:>5d} {global_shift:>20.6e} {cl_ms_l1:>16.6e} {cl_cs_l1:>16.6e} "
              f"{cl_ms_l1/global_shift if global_shift > 0 else 0:>13.2f}")

    # ── Regional ──
    print(f"\n--- Regional: cross-region L1 (ON mode, cl - ms) ---")
    print(f"{'seed':>5s} {'L→L_diff':>12s} {'R→R_diff':>12s} {'L→R_diff':>12s} {'R→L_diff':>12s}")
    print("-" * 60)
    for seed in args.seeds:
        sres = {r["arm"]: r for r in all_results if r["seed"] == seed and r["temporal"]}
        cl = sres.get("closed_loop_triggered"); ms = sres.get("matched_time_shuffle")
        if cl is None or ms is None: continue
        cl_reg = cl["readout"]["regional"]; ms_reg = ms["readout"]["regional"]
        for reg in ["L→L", "R→R", "L→R", "R→L"]:
            if reg in cl_reg and reg in ms_reg:
                diff = cl_reg[reg]["l1"] - ms_reg[reg]["l1"]
                print(f"{seed:>5d} {f'{reg}: {diff:>+.6e}':>12s}", end="")
        print()

    # Save
    if args.output_csv:
        rows = []
        for r in all_results:
            rows.append({"seed": r["seed"], "temporal": r["temporal"], "arm": r["arm"],
                         "total_events": r["total_events"],
                         "event_count_L": r["event_count_L"], "event_count_R": r["event_count_R"],
                         "final_weight_l1": r["final_weight_l1"], "mean_IEI": r.get("mean_IEI", 0)})
        with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    if args.summary_json:
        summary = {"experiment": "phase9A2_timing_controls",
                   "params": {"steps": args.steps, "seeds": args.seeds,
                              "beta": args.beta, "decay": args.decay}, "arms": []}
        for r in all_results:
            entry = {"seed": r["seed"], "arm": r["arm"], "temporal": r["temporal"],
                     "event_count_L": r["event_count_L"], "event_count_R": r["event_count_R"],
                     "total_events": r["total_events"], "final_weight_l1": r["final_weight_l1"]}
            ro = r.get("readout")
            if ro: entry["readout"] = {"global_l1": ro["global_l1"], "regional": ro["regional"],
                                        "aggregated": ro["aggregated"]}
            summary["arms"].append(entry)
        with open(args.summary_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False, default=str)

    print(f"\nDone. {len(all_results)} arm-runs.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
