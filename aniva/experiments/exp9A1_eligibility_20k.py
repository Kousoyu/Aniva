"""Phase 9A.1: Temporal Eligibility Trace — 20k 4-Seed Validation.

Validates the Phase 9A 5k smoke signal across 4 seeds at 20k steps.
Compares temporal_plasticity_enabled=False vs True using the 8B.4
state-triggered timing experiment structure.

Two arms per mode per seed:
  open_loop_poisson:    Poisson events, no state feedback
  closed_loop_triggered: State-triggered events

Key question:
  Does the 4-5x |ol-cl|_L1 amplification from 9A smoke hold across
  all 4 seeds? Is temporal sensitivity seed-specific?

Language discipline: no "preference", "reward", "choice", "agent".
"""
import argparse, csv, json, sys
import numpy as np

from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.environment.environment import Stimulus, StimulusEvent, Environment

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
    n = len(deltas)
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
    def _s(a, m):
        return float(np.mean(np.abs(a[m]))) if m.any() else 0.0
    return {
        "global_l1": float(np.mean(absd)), "signed_mean": float(np.mean(deltas)),
        "regional": regional,
        "aggregated": {
            "L_in": _s(absd, l_in), "L_out": _s(absd, l_out),
            "R_in": _s(absd, r_in), "R_out": _s(absd, r_out),
            "within": _s(absd, within), "cross": _s(absd, cross),
        },
        "delta_vector": deltas.tolist(), "n_connections": n,
    }


def _calibrate(cfg, pct, rng):
    core = LifeCore(cfg)
    vals = []
    for s in range(CALIB_STEPS):
        core.step(env_influences=None)
        if s >= 500:
            vals.append(abs(_compute_imbalance(core)[2]))
    return float(np.percentile(vals, pct))


def _poisson_stream(steps, mi, pL, rng):
    p = 1.0 / mi
    evs = []
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


def _run_poisson(cfg, steps, stream):
    core = LifeCore(cfg)
    w0 = np.array([c.weight for c in core.connections], dtype=np.float64)
    elog, aevs = [], []
    idx = 0
    for s in range(steps):
        while idx < len(stream) and stream[idx]["step"] <= s:
            se = stream[idx]
            if se["step"] == s:
                aevs.append(StimulusEvent(stimulus=se["stimulus"], start_step=s, duration_steps=se["duration"]))
                elog.append({"step": s, "chosen": se["chosen"], "duration": se["duration"]})
            idx += 1
        core.step(env_influences=_influences_at_step(aevs, s, core))
    return _pack(core, w0, elog, "open_loop_poisson")


def _run_triggered(cfg, steps, threshold, sw, refrac):
    core = LifeCore(cfg)
    w0 = np.array([c.weight for c in core.connections], dtype=np.float64)
    elog, aevs = [], []
    simb, scnt, slast = 0.0, 0, refrac
    for s in range(steps):
        core.step(env_influences=_influences_at_step(aevs, s, core))
        _, _, raw = _compute_imbalance(core)
        simb = SMOOTHING_ALPHA * raw + (1 - SMOOTHING_ALPHA) * simb
        slast += 1
        scnt = scnt + 1 if abs(simb) > threshold else 0
        if scnt >= sw and slast >= refrac:
            lb = "R" if simb > 0 else "L"
            stim = R_STIM if simb > 0 else L_STIM
            aevs.append(StimulusEvent(stimulus=stim, start_step=s, duration_steps=EVENT_DURATION))
            elog.append({"step": s, "chosen": lb, "duration": EVENT_DURATION})
            scnt, slast = 0, 0
    return _pack(core, w0, elog, "closed_loop_triggered")


def _pack(core, w0, elog, arm):
    nL = sum(1 for e in elog if e["chosen"] == "L")
    nR = sum(1 for e in elog if e["chosen"] == "R")
    return {
        "arm": arm,
        "event_log": elog, "total_events": len(elog),
        "event_count_L": nL, "event_count_R": nR,
        "final_weight_l1": float(np.mean(np.abs(
            np.array([c.weight for c in core.connections]) - w0))),
        "readout": _structural_readout(core, w0),
    }


def _cos(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(np.dot(a, b) / (na * nb)) if na > 0 and nb > 0 else 0.0

def _l1(a, b):
    return float(np.mean(np.abs(a - b)))


def main(argv=None):
    p = argparse.ArgumentParser(description="Phase 9A.1: 20k 4-Seed Validation")
    p.add_argument("--steps", type=int, default=20000)
    p.add_argument("--seeds", type=int, nargs="+", default=[42, 77, 123, 999])
    p.add_argument("--beta", type=float, default=0.5)
    p.add_argument("--decay", type=float, default=0.05)
    p.add_argument("--output-csv", type=str, default="results/phase9A1_eligibility_20k_4seed.csv")
    p.add_argument("--summary-json", type=str, default="results/phase9A1_eligibility_20k_4seed_summary.json")
    p.add_argument("--no-homeostasis", action="store_true")
    p.add_argument("--base-rng", type=int, default=20260504)
    args = p.parse_args(argv)

    print(f"Phase 9A.1: Temporal Eligibility 20k 4-Seed Validation")
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

            r_ol = _run_poisson(cfg, args.steps, ps)
            cfg.seed = seed  # re-seed identical init
            r_cl = _run_triggered(cfg, args.steps, thr, SUSTAINED_WINDOW, REFRACTORY)

            for r in [r_ol, r_cl]:
                r["seed"] = seed; r["temporal"] = temporal_on
                all_results.append(r)

            dv_ol, dv_cl = np.array(r_ol["readout"]["delta_vector"]), np.array(r_cl["readout"]["delta_vector"])
            c = _cos(dv_ol, dv_cl)
            l = _l1(dv_ol, dv_cl)
            print(f"  s={seed:>4d}  ol_ev={r_ol['total_events']:>4d}  cl_ev={r_cl['total_events']:>4d}  "
                  f"cos(ol,cl)={c:.8f}  |L1|={l:.6e}  "
                  f"ΔwL1={r_cl['final_weight_l1']-r_ol['final_weight_l1']:>+.4e}")
        print()

    # ── Cross-mode summary ──
    print(f"{'='*90}")
    print(f"Phase 9A.1 — Cross-Mode Comparison")
    print(f"{'='*90}")
    print(f"{'seed':>5s} {'arm_pair':>15s}  "
          f"{'cos_off':>12s} {'cos_on':>12s} {'|L1|_off':>12s} {'|L1|_on':>12s} "
          f"{'L1_ratio':>9s}")
    print("-" * 85)

    for seed in args.seeds:
        off_ol = next(r for r in all_results if r["seed"]==seed and r["arm"]=="open_loop_poisson" and not r["temporal"])
        off_cl = next(r for r in all_results if r["seed"]==seed and r["arm"]=="closed_loop_triggered" and not r["temporal"])
        on_ol = next(r for r in all_results if r["seed"]==seed and r["arm"]=="open_loop_poisson" and r["temporal"])
        on_cl = next(r for r in all_results if r["seed"]==seed and r["arm"]=="closed_loop_triggered" and r["temporal"])

        def _dv(r): return np.array(r["readout"]["delta_vector"])
        cos_off = _cos(_dv(off_ol), _dv(off_cl))
        cos_on = _cos(_dv(on_ol), _dv(on_cl))
        l1_off = _l1(_dv(off_ol), _dv(off_cl))
        l1_on = _l1(_dv(on_ol), _dv(on_cl))
        ratio = l1_on / l1_off if l1_off > 0 else 0

        print(f"{seed:>5d} {'ol vs cl':>15s}  "
              f"{cos_off:>12.8f} {cos_on:>12.8f} {l1_off:>12.6e} {l1_on:>12.6e} "
              f"{ratio:>8.2f}x")

        # same-arm temporal off vs on
        for arm in ["open_loop_poisson", "closed_loop_triggered"]:
            r_off = next(r for r in all_results if r["seed"]==seed and r["arm"]==arm and not r["temporal"])
            r_on = next(r for r in all_results if r["seed"]==seed and r["arm"]==arm and r["temporal"])
            l1_same = _l1(_dv(r_off), _dv(r_on))
            print(f"{seed:>5d} {'  same '+arm:>15s}  {'':>12s} {'':>12s} {'':>12s} {l1_same:>12.6e}")

    # ── Regional comparison ──
    print(f"\n--- Regional Readout: L_out - L_in asymmetry ---")
    print(f"{'seed':>5s} {'temporal':>8s} {'arm':>25s}  "
          f"{'L_out-L_in':>12s} {'R_out-R_in':>12s} {'within-cross':>14s}")
    print("-" * 85)
    for r in all_results:
        agg = r["readout"]["aggregated"]
        lo = agg["L_out"] - agg["L_in"]
        ro = agg["R_out"] - agg["R_in"]
        wc = agg["within"] - agg["cross"]
        print(f"{r['seed']:>5d} {'ON' if r['temporal'] else 'OFF':>8s} {r['arm']:>25s}  "
              f"{lo:>+12.6e} {ro:>+12.6e} {wc:>+14.6e}")

    # ── Stability check ──
    print(f"\n--- Stability Check ---")
    print(f"{'seed':>5s} {'temporal':>8s} {'arm':>25s}  "
          f"{'ΔwL1_abs':>12s} {'global_l1':>12s}")
    print("-" * 70)
    for r in all_results:
        ro = r["readout"]
        print(f"{r['seed']:>5d} {'ON' if r['temporal'] else 'OFF':>8s} {r['arm']:>25s}  "
              f"{r['final_weight_l1']:>12.6e} {ro['global_l1']:>12.6e}")

    # Save
    if args.output_csv:
        rows = []
        for r in all_results:
            rows.append({
                "seed": r["seed"], "temporal": r["temporal"], "arm": r["arm"],
                "total_events": r["total_events"],
                "event_count_L": r["event_count_L"], "event_count_R": r["event_count_R"],
                "final_weight_l1": r["final_weight_l1"],
            })
        with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
    if args.summary_json:
        summary = {"experiment": "phase9A1_eligibility_20k_4seed",
                   "params": {"steps": args.steps, "seeds": args.seeds,
                              "beta": args.beta, "decay": args.decay}, "arms": []}
        for r in all_results:
            entry = {
                "seed": r["seed"], "arm": r["arm"], "temporal": r["temporal"],
                "event_count_L": r["event_count_L"], "event_count_R": r["event_count_R"],
                "total_events": r["total_events"], "final_weight_l1": r["final_weight_l1"],
            }
            ro = r.get("readout")
            if ro:
                entry["readout"] = {"global_l1": ro["global_l1"], "signed_mean": ro["signed_mean"],
                                    "regional": ro["regional"], "aggregated": ro["aggregated"]}
            summary["arms"].append(entry)
        with open(args.summary_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False, default=str)

    print(f"\nDone. {len(all_results)} arm-runs.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
