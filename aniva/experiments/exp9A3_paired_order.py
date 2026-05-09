"""Phase 9A.3: Paired-Order Temporal Plasticity Assay.

Tests whether the eligibility trace formula itself can distinguish
"L fires before R" from "R fires before L" — the minimal directional
assay for temporal plasticity.

Four arms, identical total stimulation:
  L_then_R:          L pulse → gap → R pulse
  R_then_L:          R pulse → gap → L pulse
  simultaneous:       L+R same time
  separated_control:  L then R with long gap (reduced eligibility overlap)

All arms matched: same L/R count, intensity, duration. Only ORDER differs.

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


def _make_schedule(steps, order):
    """Generate fixed paired-pulse schedule. All arms get same total L/R count."""
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


def _run_schedule(cfg, steps, schedule):
    core = LifeCore(cfg)
    w0 = np.array([c.weight for c in core.connections], dtype=np.float64)
    elog, aevs = [], []; idx = 0
    for s in range(steps):
        while idx < len(schedule) and schedule[idx][0] <= s:
            t, lb, dur = schedule[idx]
            if t == s:
                stim = L_STIM if lb == "L" else R_STIM
                aevs.append(StimulusEvent(stimulus=stim, start_step=s, duration_steps=dur))
                elog.append({"step": s, "side": lb, "duration": dur})
            idx += 1
        core.step(env_influences=_influences_at_step(aevs, s, core))
    return _pack(core, w0, elog)


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
    p = argparse.ArgumentParser(description="Phase 9A.3: Paired-Order Temporal Plasticity Assay")
    p.add_argument("--steps", type=int, default=20000)
    p.add_argument("--seeds", type=int, nargs="+", default=[42, 77, 123, 999])
    p.add_argument("--beta", type=float, default=0.5)
    p.add_argument("--decay", type=float, default=0.05)
    p.add_argument("--output-csv", type=str, default="results/phase9A3_paired_order_20k.csv")
    p.add_argument("--summary-json", type=str, default="results/phase9A3_paired_order_20k_summary.json")
    p.add_argument("--no-homeostasis", action="store_true")
    args = p.parse_args(argv)

    arm_names = ["L_then_R", "R_then_L", "simultaneous", "separated_control"]

    print(f"Phase 9A.3: Paired-Order Temporal Plasticity Assay")
    print(f"  seeds={args.seeds}  steps={args.steps}  beta={args.beta}  decay={args.decay}")
    print(f"  gap={PAIR_GAP}  interval={PAIR_INTERVAL}  pulse_dur={PULSE_DURATION}")
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

            for arm in arm_names:
                sched = _make_schedule(args.steps, arm)
                r = _run_schedule(cfg, args.steps, sched)
                r["arm"], r["seed"], r["temporal"] = arm, seed, temporal_on
                all_results.append(r)

            # Per-seed summary: key directional metrics
            sres = {r["arm"]: r for r in all_results
                    if r["seed"] == seed and r["temporal"] == temporal_on}
            ltr = sres.get("L_then_R", {}).get("readout", {}).get("directional", {})
            rtl = sres.get("R_then_L", {}).get("readout", {}).get("directional", {})
            asym_ltr = ltr.get("L_to_R_signed_mean", 0) - ltr.get("R_to_L_signed_mean", 0)
            asym_rtl = rtl.get("L_to_R_signed_mean", 0) - rtl.get("R_to_L_signed_mean", 0)
            sim = sres.get("simultaneous", {}).get("readout", {}).get("directional", {})
            asym_sim = sim.get("L_to_R_signed_mean", 0) - sim.get("R_to_L_signed_mean", 0)

            print(f"  s={seed:>4d}  "
                  f"ev={sres['L_then_R']['total_events']:>3d}  "
                  f"asym(L→R-R→L): L_then_R={asym_ltr:>+10.3e}  "
                  f"R_then_L={asym_rtl:>+10.3e}  "
                  f"simul={asym_sim:>+10.3e}")
        print()

    # ── Core result: L_then_R vs R_then_L ──
    print(f"{'='*90}")
    print(f"Phase 9A.3 — KEY RESULT: L_then_R vs R_then_L")
    print(f"{'='*90}")

    for temporal_on in [False, True]:
        tlabel = "TEMPORAL ON" if temporal_on else "TEMPORAL OFF"
        print(f"\n--- {tlabel} ---")
        print(f"{'seed':>5s} {'cos':>12s} {'|L1|':>14s} {'|L2|':>14s} {'L→R_sgn(L)':>14s} {'L→R_sgn(R)':>14s} "
              f"{'R→L_sgn(L)':>14s} {'R→L_sgn(R)':>14s} {'asym(L)':>12s} {'asym(R)':>12s}")
        print("-" * 130)

        for seed in args.seeds:
            sres = {r["arm"]: r for r in all_results
                    if r["seed"] == seed and r["temporal"] == temporal_on}
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
                  f"{d_ltr['L_to_R_signed_mean']:>+14.6e} {d_rtl['L_to_R_signed_mean']:>+14.6e} "
                  f"{d_ltr['R_to_L_signed_mean']:>+14.6e} {d_rtl['R_to_L_signed_mean']:>+14.6e} "
                  f"{asym_ltr:>+12.6e} {asym_rtl:>+12.6e}")

    # ── Full pairwise matrix ──
    print(f"\n{'='*100}")
    print(f"Phase 9A.3 — Full Delta Vector Pairwise Comparison")
    print(f"{'='*100}")

    for temporal_on in [False, True]:
        tlabel = "TEMPORAL ON" if temporal_on else "TEMPORAL OFF"
        print(f"\n--- {tlabel} ---")
        print(f"{'seed':>5s} {'pair':>35s}  {'cos':>12s} {'|L1|':>14s} {'|L2|':>14s}")
        print("-" * 82)

        for seed in args.seeds:
            sres = {r["arm"]: r for r in all_results
                    if r["seed"] == seed and r["temporal"] == temporal_on}
            for i in range(len(arm_names)):
                for j in range(i + 1, len(arm_names)):
                    a_name, b_name = arm_names[i], arm_names[j]
                    a = sres.get(a_name); b = sres.get(b_name)
                    if a is None or b is None: continue
                    dv_a = np.array(a["readout"]["delta_vector"])
                    dv_b = np.array(b["readout"]["delta_vector"])
                    c = _cos(dv_a, dv_b); l1 = _l1(dv_a, dv_b)
                    l2 = float(np.sqrt(np.mean((dv_a - dv_b) ** 2)))
                    print(f"{seed:>5d} {f'{a_name} vs {b_name}':>35s}  "
                          f"{c:>12.8f} {l1:>14.6e} {l2:>14.6e}")

    # ── Directional asymmetry summary ──
    print(f"\n{'='*90}")
    print(f"Phase 9A.3 — Directional Asymmetry: L→R signed_mean minus R→L signed_mean")
    print(f"{'='*90}")

    for temporal_on in [False, True]:
        tlabel = "TEMPORAL ON" if temporal_on else "TEMPORAL OFF"
        print(f"\n--- {tlabel} ---")
        print(f"{'seed':>5s} {'L_then_R':>14s} {'R_then_L':>14s} {'simultaneous':>14s} {'separated':>14s} "
              f"{'L>R - R>L':>14s}")
        print("-" * 75)

        for seed in args.seeds:
            sres = {r["arm"]: r for r in all_results
                    if r["seed"] == seed and r["temporal"] == temporal_on}
            asyms = {}
            for arm in arm_names:
                d = sres.get(arm, {}).get("readout", {}).get("directional", {})
                asyms[arm] = d.get("L_to_R_signed_mean", 0) - d.get("R_to_L_signed_mean", 0)

            diff = asyms.get("L_then_R", 0) - asyms.get("R_then_L", 0)
            print(f"{seed:>5d} {asyms.get('L_then_R', 0):>+14.6e} {asyms.get('R_then_L', 0):>+14.6e} "
                  f"{asyms.get('simultaneous', 0):>+14.6e} {asyms.get('separated_control', 0):>+14.6e} "
                  f"{diff:>+14.6e}")

    # ── Global shift vs differential signal ──
    print(f"\n{'='*90}")
    print(f"Phase 9A.3 — Global Shift vs L_then_R/R_then_L Differential")
    print(f"{'='*90}")
    print(f"{'seed':>5s} {'same-arm off-on L1':>20s} {'ON L_then_R vs R_then_L L1':>28s} {'ratio':>10s}")
    print("-" * 70)

    for seed in args.seeds:
        same_arm_l1s = []
        for arm in arm_names:
            r_off = next((r for r in all_results if r["seed"] == seed and r["arm"] == arm and not r["temporal"]), None)
            r_on = next((r for r in all_results if r["seed"] == seed and r["arm"] == arm and r["temporal"]), None)
            if r_off and r_on:
                same_arm_l1s.append(_l1(np.array(r_off["readout"]["delta_vector"]),
                                        np.array(r_on["readout"]["delta_vector"])))
        global_shift = float(np.mean(same_arm_l1s)) if same_arm_l1s else 0.0

        r_ltr_on = next((r for r in all_results if r["seed"] == seed and r["arm"] == "L_then_R" and r["temporal"]), None)
        r_rtl_on = next((r for r in all_results if r["seed"] == seed and r["arm"] == "R_then_L" and r["temporal"]), None)
        if r_ltr_on and r_rtl_on:
            pair_l1 = _l1(np.array(r_ltr_on["readout"]["delta_vector"]),
                          np.array(r_rtl_on["readout"]["delta_vector"]))
            ratio = pair_l1 / global_shift if global_shift > 0 else 0
            print(f"{seed:>5d} {global_shift:>20.6e} {pair_l1:>28.6e} {ratio:>9.2f}")

    # ── Regional cross-region detail ──
    print(f"\n--- Regional: ON mode L→R and R→L signed_mean by arm ---")
    print(f"{'seed':>5s} {'arm':>20s} {'L→R_sgn':>14s} {'R→L_sgn':>14s} {'L→R_l1':>14s} {'R→L_l1':>14s}")
    print("-" * 80)
    for seed in args.seeds:
        for arm in arm_names:
            r = next((r for r in all_results if r["seed"] == seed and r["arm"] == arm and r["temporal"]), None)
            if r is None: continue
            d = r["readout"]["directional"]
            print(f"{seed:>5d} {arm:>20s} {d['L_to_R_signed_mean']:>+14.6e} {d['R_to_L_signed_mean']:>+14.6e} "
                  f"{d['L_to_R_l1']:>14.6e} {d['R_to_L_l1']:>14.6e}")

    # Save
    if args.output_csv:
        rows = []
        for r in all_results:
            d = r["readout"]["directional"]
            rows.append({"seed": r["seed"], "temporal": r["temporal"], "arm": r["arm"],
                         "total_events": r["total_events"],
                         "event_count_L": r["event_count_L"], "event_count_R": r["event_count_R"],
                         "final_weight_l1": r["final_weight_l1"],
                         "L_to_R_signed_mean": d["L_to_R_signed_mean"],
                         "R_to_L_signed_mean": d["R_to_L_signed_mean"],
                         "L_to_R_l1": d["L_to_R_l1"],
                         "R_to_L_l1": d["R_to_L_l1"]})
        with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    if args.summary_json:
        summary = {"experiment": "phase9A3_paired_order",
                   "params": {"steps": args.steps, "seeds": args.seeds,
                              "beta": args.beta, "decay": args.decay,
                              "pulse_duration": PULSE_DURATION, "pair_gap": PAIR_GAP,
                              "pair_interval": PAIR_INTERVAL}, "arms": []}
        for r in all_results:
            entry = {"seed": r["seed"], "arm": r["arm"], "temporal": r["temporal"],
                     "event_count_L": r["event_count_L"], "event_count_R": r["event_count_R"],
                     "total_events": r["total_events"], "final_weight_l1": r["final_weight_l1"]}
            ro = r.get("readout")
            if ro:
                entry["readout"] = {"global_l1": ro["global_l1"], "regional": ro["regional"],
                                    "aggregated": ro["aggregated"], "directional": ro["directional"]}
            summary["arms"].append(entry)
        with open(args.summary_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False, default=str)

    print(f"\nDone. {len(all_results)} arm-runs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
