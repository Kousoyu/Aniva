"""Phase 9C.1A: Event-Pair Update-Gain Calibration.

NOT a scientific experiment. This is an engineering calibration step:
find the target_event_update_l1 range where the event-pair outer-product
update produces measurable (but not saturating) weight changes.

Fixed: gap=500, tau_trace=1000, seed=42, num_pairs=5.
Sweep: target_event_update_l1 ∈ {1e-6, 1e-5, 1e-4, 1e-3}.

Key change from 9C.1: L1-normalized update.
  raw = masked_outer(r, phi, A)         # per-connection raw delta
  dW = target * raw / (sum(|raw|) + eps) # total L1 budget = target

This decouples update magnitude from trace/phi absolute scale.
No labels, no arm names, no "if L_then_R" — same anti-cheat as 9C.1.
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
DEFAULT_TAU_TRACE = 1000
EPS = 1e-12

# ── Geometry & readout (shared with 9C.1 / 9B.2) ───────────────────────

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
    return {
        "global_l1": float(np.mean(absd)),
        "signed_mean": float(np.mean(deltas)),
        "regional": regional,
        "directional": {
            "L_to_R_signed_mean": regional.get("L→R", {}).get("signed_mean", 0.0),
            "R_to_L_signed_mean": regional.get("R→L", {}).get("signed_mean", 0.0),
            "L_to_R_l1": regional.get("L→R", {}).get("l1", 0.0),
            "R_to_L_l1": regional.get("R→L", {}).get("l1", 0.0),
        },
    }


# ── Scheduling ──────────────────────────────────────────────────────────

def _compute_scheduling_params(gap, num_pairs, rest_window):
    pair_interval = gap + PULSE_DURATION + rest_window
    total_steps = WARMUP + num_pairs * pair_interval + TAIL_BUFFER
    return pair_interval, total_steps


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


# ── Event-pair mechanism (L1-normalized) ────────────────────────────────

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


def _apply_event_pair_update_normalized(core, trace, phi, target_l1):
    """L1-normalized masked outer product update.

    raw_{ij} = trace[i] * phi[j] * A_{ij}
    scale = target_l1 / (sum(|raw|) + eps)
    dW_{ij} = scale * raw_{ij}

    Returns: raw_l1 (pre-normalization), scale factor.
    """
    conns = list(core.connections)
    n_conns = len(conns)

    # Compute raw deltas
    raw = np.zeros(n_conns, dtype=np.float64)
    for k, conn in enumerate(conns):
        raw[k] = trace[conn.source_id] * phi[conn.target_id]

    raw_l1 = float(np.sum(np.abs(raw)))
    if raw_l1 < EPS:
        return raw_l1, 0.0

    scale = target_l1 / raw_l1

    # Apply clamped update
    for k, conn in enumerate(conns):
        dw = scale * raw[k]
        w = conn.weight + dw
        conn.weight = max(-1.0, min(1.0, w))

    return raw_l1, scale


# ── Environment influence ───────────────────────────────────────────────

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


# ── Core simulation ────────────────────────────────────────────────────

def _run_calibration_schedule(cfg, steps, schedule, tau_trace, target_l1, mode):
    core = LifeCore(cfg)
    w0 = np.array([c.weight for c in core.connections], dtype=np.float64)
    n_units = cfg.unit_count

    trace = np.zeros(n_units, dtype=np.float64) if mode == "event_pair" else None
    last_pulse_time = 0.0

    update_log = []
    elog = []
    aevs = []
    idx = 0

    phi_cache = {}
    if mode == "event_pair":
        phi_cache["L"] = _compute_phi(core, L_STIM)
        phi_cache["R"] = _compute_phi(core, R_STIM)

    event_starts = {}
    for t, side, dur in schedule:
        event_starts.setdefault(t, []).append(side)

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
                raw_l1, scale = _apply_event_pair_update_normalized(
                    core, trace, phi, target_l1)

                update_log.append({
                    "step": s,
                    "dt": dt,
                    "trace_mass": float(np.sum(np.abs(trace))),
                    "phi_mass": float(np.sum(np.abs(phi))),
                    "raw_l1": raw_l1,
                    "scale": scale,
                    "target_l1": target_l1,
                })

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

    result = _pack(core, w0, elog)
    result["update_log"] = update_log
    if update_log:
        result["update_summary"] = {
            "n_updates": len(update_log),
            "mean_raw_l1": float(np.mean([u["raw_l1"] for u in update_log])),
            "mean_scale": float(np.mean([u["scale"] for u in update_log])),
            "mean_trace_mass": float(np.mean([u["trace_mass"] for u in update_log])),
            "mean_phi_mass": float(np.mean([u["phi_mass"] for u in update_log])),
        }
    else:
        result["update_summary"] = {}
    return result


def _pack(core, w0, elog):
    nL = sum(1 for e in elog if e["side"] == "L")
    nR = sum(1 for e in elog if e["side"] == "R")
    return {
        "event_log": elog,
        "total_events": len(elog),
        "event_count_L": nL,
        "event_count_R": nR,
        "final_weight_l1": float(np.mean(np.abs(
            np.array([c.weight for c in core.connections]) - w0))),
        "readout": _structural_readout(core, w0),
    }


# ── Metrics ─────────────────────────────────────────────────────────────

def _compute_DI(directional):
    lr = directional.get("L_to_R_l1", 0.0)
    rl = directional.get("R_to_L_l1", 0.0)
    return (lr - rl) / (lr + rl + EPS)


def _compute_OS(di_ltr, di_rtl):
    return di_ltr - di_rtl


# ── Main ────────────────────────────────────────────────────────────────

def main(argv=None):
    import sys as _sys
    _sys.stdout.reconfigure(line_buffering=True)

    p = argparse.ArgumentParser(
        description="Phase 9C.1A: Event-Pair Update-Gain Calibration")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--gap", type=int, default=DEFAULT_GAP)
    p.add_argument("--tau", type=int, default=DEFAULT_TAU_TRACE)
    p.add_argument("--num-pairs", type=int, default=5)
    p.add_argument("--rest-window", type=int, default=500)
    p.add_argument("--targets", type=float, nargs="+",
                   default=[1e-6, 1e-5, 1e-4, 1e-3])
    p.add_argument("--output-csv", type=str,
                   default="results/phase9C1A_calibration.csv")
    p.add_argument("--summary-json", type=str,
                   default="results/phase9C1A_calibration_summary.json")
    p.add_argument("--no-homeostasis", action="store_true")
    args = p.parse_args(argv)

    arm_names = ["L_then_R", "R_then_L", "simultaneous", "separated_control"]
    targets = args.targets
    tau = args.tau

    pair_interval, total_steps = _compute_scheduling_params(
        args.gap, args.num_pairs, args.rest_window)

    off_runs = len(arm_names)
    ep_runs = len(arm_names) * len(targets)
    total_runs = off_runs + ep_runs

    print(f"Phase 9C.1A: Event-Pair Update-Gain Calibration")
    print(f"  seed={args.seed}  gap={args.gap}  tau_trace={tau}")
    print(f"  num_pairs={args.num_pairs}  targets={targets}")
    print(f"  pair_interval={pair_interval}  total_steps={total_steps}")
    print(f"  OFF: {off_runs} arm-runs  +  event_pair: {ep_runs} arm-runs")
    print(f"           = {total_runs} total")
    print()

    all_results = []
    t0_wall = time.time()

    # ── OFF baseline ──
    print(f"{'='*70}\n  OFF baseline\n{'='*70}")

    cfg_off = AnivaConfig(unit_count=300, seed=args.seed)
    cfg_off.homeostasis_enabled = not args.no_homeostasis
    cfg_off.homeostatic_target_abs_weight = 0.30
    cfg_off.homeostatic_rate = 1.0
    cfg_off.temporal_plasticity_enabled = False

    for arm in arm_names:
        sched = _make_schedule(arm, args.gap, pair_interval, args.num_pairs)
        r = _run_calibration_schedule(
            cfg_off, total_steps, sched, tau_trace=0, target_l1=0, mode="OFF")
        r["arm"], r["seed"], r["mode"], r["gap"] = arm, args.seed, "OFF", args.gap
        r["tau_trace"] = 0
        r["target_event_update_l1"] = 0.0
        all_results.append(r)

        di = _compute_DI(r["readout"]["directional"])
        print(f"  {arm:>20s}  DI={di:+.6e}  "
              f"L_to_R_l1={r['readout']['directional']['L_to_R_l1']:.4e}  "
              f"R_to_L_l1={r['readout']['directional']['R_to_L_l1']:.4e}")
    print()

    # ── event_pair calibration sweep ──
    for target in targets:
        print(f"{'='*70}\n  event_pair  target_event_update_l1={target:.0e}  "
              f"tau_trace={tau}  gap={args.gap}\n{'='*70}")

        cfg_ep = AnivaConfig(unit_count=300, seed=args.seed)
        cfg_ep.homeostasis_enabled = not args.no_homeostasis
        cfg_ep.homeostatic_target_abs_weight = 0.30
        cfg_ep.homeostatic_rate = 1.0
        cfg_ep.temporal_plasticity_enabled = False

        for arm in arm_names:
            sched = _make_schedule(arm, args.gap, pair_interval, args.num_pairs)
            r = _run_calibration_schedule(
                cfg_ep, total_steps, sched, tau_trace=tau,
                target_l1=target, mode="event_pair")
            r["arm"], r["seed"], r["mode"], r["gap"] = arm, args.seed, "event_pair", args.gap
            r["tau_trace"] = tau
            r["target_event_update_l1"] = target
            all_results.append(r)

            di = _compute_DI(r["readout"]["directional"])
            us = r.get("update_summary", {})
            n_up = us.get("n_updates", 0)
            raw_l1 = us.get("mean_raw_l1", 0)
            scale = us.get("mean_scale", 0)

            # Compute per-region update l1 from the final weight deltas
            # (more accurate than summing per-update deltas)
            print(f"  {arm:>20s}  DI={di:+.6e}  "
                  f"updates={n_up}  raw_l1={raw_l1:.2e}  scale={scale:.2e}")

    wall_s = time.time() - t0_wall

    # ── KEY OUTPUT: Calibration table ──
    print(f"\n{'='*90}")
    print(f"Phase 9C.1A — Calibration Table")
    print(f"  gap={args.gap}  tau_trace={tau}  seed={args.seed}  num_pairs={args.num_pairs}")
    print(f"{'='*90}")

    off_ltr = next(r for r in all_results
                   if r["arm"] == "L_then_R" and r["mode"] == "OFF")
    off_rtl = next(r for r in all_results
                   if r["arm"] == "R_then_L" and r["mode"] == "OFF")
    off_di_ltr = _compute_DI(off_ltr["readout"]["directional"])
    off_di_rtl = _compute_DI(off_rtl["readout"]["directional"])
    off_os = _compute_OS(off_di_ltr, off_di_rtl)

    print(f"  OFF baseline:  DI(L_then_R)={off_di_ltr:+.6e}  "
          f"DI(R_then_L)={off_di_rtl:+.6e}  OS={off_os:+.2e}")
    print()

    header = (f"  {'target_l1':>10s} {'raw_l1':>10s} {'scale':>10s} "
              f"{'DI(L→R)':>14s} {'DI(R→L)':>14s} {'OS':>12s} "
              f"{'DI(simul)':>12s} {'DI(sep)':>12s} "
              f"{'sat':>6s} {'OS>3×OFF?':>10s}")
    print(header)
    print(f"  {'-'*(len(header)-2)}")

    for target in targets:
        ltr = next(r for r in all_results
                   if r["arm"] == "L_then_R" and r["mode"] == "event_pair"
                   and r["target_event_update_l1"] == target)
        rtl = next(r for r in all_results
                   if r["arm"] == "R_then_L" and r["mode"] == "event_pair"
                   and r["target_event_update_l1"] == target)
        sim = next(r for r in all_results
                   if r["arm"] == "simultaneous" and r["mode"] == "event_pair"
                   and r["target_event_update_l1"] == target)
        sep = next(r for r in all_results
                   if r["arm"] == "separated_control" and r["mode"] == "event_pair"
                   and r["target_event_update_l1"] == target)

        di_ltr = _compute_DI(ltr["readout"]["directional"])
        di_rtl = _compute_DI(rtl["readout"]["directional"])
        di_sim = _compute_DI(sim["readout"]["directional"])
        di_sep = _compute_DI(sep["readout"]["directional"])
        os_val = _compute_OS(di_ltr, di_rtl)

        us = ltr.get("update_summary", {})
        raw_l1 = us.get("mean_raw_l1", 0)
        scale = us.get("mean_scale", 0)

        os_ok = abs(os_val) > 3 * max(abs(off_os), EPS)
        sim_ok = abs(di_sim) < abs(os_val) * 0.5 if abs(os_val) > EPS else True

        print(f"  {target:>10.0e} {raw_l1:>10.2e} {scale:>10.2e} "
              f"{di_ltr:>+14.6e} {di_rtl:>+14.6e} {os_val:>+12.2e} "
              f"{di_sim:>+12.2e} {di_sep:>+12.2e} "
              f"{'':>6s} {'YES' if os_ok else 'no':>10s}")

    # ── Scheduling verification ──
    print(f"\n{'='*70}")
    print(f"  Scheduling Verification")
    print(f"  {'arm':>20s} {'L_ev':>5s} {'R_ev':>5s} {'OK':>5s}")
    for arm in arm_names:
        r = next(r for r in all_results if r["arm"] == arm and r["mode"] == "OFF")
        ok = (r["event_count_L"] == args.num_pairs
              and r["event_count_R"] == args.num_pairs)
        print(f"  {arm:>20s} {r['event_count_L']:>5d} "
              f"{r['event_count_R']:>5d} {'OK' if ok else 'FAIL':>5s}")

    # ── Sanity ──
    has_nan = any(np.isnan(r["final_weight_l1"]) for r in all_results)
    all_sched_ok = all(
        r["event_count_L"] == args.num_pairs and r["event_count_R"] == args.num_pairs
        for r in all_results if r["mode"] == "OFF")

    print(f"\n  NaN: {'YES [WARN]' if has_nan else 'none'}")
    print(f"  Schedule: {'ALL OK' if all_sched_ok else 'FAILURES [WARN]'}")
    print(f"  Wall time: {wall_s:.1f}s")

    # ── CSV ──
    if args.output_csv:
        rows = []
        for r in all_results:
            d = r["readout"]["directional"]
            us = r.get("update_summary", {})
            di = _compute_DI(d)
            rows.append({
                "seed": r["seed"], "gap": r["gap"], "tau_trace": r["tau_trace"],
                "target_event_update_l1": r["target_event_update_l1"],
                "mode": r["mode"], "arm": r["arm"],
                "num_pairs": args.num_pairs,
                "event_count_L": r["event_count_L"],
                "event_count_R": r["event_count_R"],
                "schedule_ok": (r["event_count_L"] == args.num_pairs
                                and r["event_count_R"] == args.num_pairs),
                "lr_weight_l1": d["L_to_R_l1"],
                "rl_weight_l1": d["R_to_L_l1"],
                "DI": di,
                "n_event_pair_updates": us.get("n_updates", 0),
                "mean_raw_l1": us.get("mean_raw_l1", 0),
                "mean_scale": us.get("mean_scale", 0),
                "mean_trace_mass": us.get("mean_trace_mass", 0),
                "runtime_s": wall_s,
            })
        fieldnames = list(rows[0].keys())
        with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)

    # ── JSON ──
    if args.summary_json:
        os_by_target = {}
        for target in targets:
            ltr = next((r for r in all_results
                        if r["arm"] == "L_then_R" and r["mode"] == "event_pair"
                        and r["target_event_update_l1"] == target), None)
            rtl = next((r for r in all_results
                        if r["arm"] == "R_then_L" and r["mode"] == "event_pair"
                        and r["target_event_update_l1"] == target), None)
            if ltr and rtl:
                os_by_target[str(target)] = _compute_OS(
                    _compute_DI(ltr["readout"]["directional"]),
                    _compute_DI(rtl["readout"]["directional"]))

        summary = {
            "experiment": "phase9C1A_update_gain_calibration",
            "params": {
                "seed": args.seed, "gap": args.gap, "tau_trace": tau,
                "num_pairs": args.num_pairs, "rest_window": args.rest_window,
                "targets": targets,
                "pulse_duration": PULSE_DURATION,
                "warmup": WARMUP, "tail_buffer": TAIL_BUFFER,
            },
            "scheduling": {"pair_interval": pair_interval, "total_steps": total_steps},
            "off_baseline": {
                "DI_L_then_R": off_di_ltr,
                "DI_R_then_L": off_di_rtl,
                "OS_off": off_os,
            },
            "os_by_target_l1": os_by_target,
            "sanity": {
                "has_nan": has_nan,
                "schedule_all_ok": all_sched_ok,
                "wall_time_s": wall_s,
            },
            "arms": [],
        }
        for r in all_results:
            entry = {
                "seed": r["seed"], "gap": r["gap"], "tau_trace": r["tau_trace"],
                "target_event_update_l1": r["target_event_update_l1"],
                "arm": r["arm"], "mode": r["mode"],
                "event_count_L": r["event_count_L"],
                "event_count_R": r["event_count_R"],
                "total_events": r["total_events"],
                "final_weight_l1": r["final_weight_l1"],
            }
            ro = r.get("readout")
            if ro:
                entry["readout"] = {
                    "global_l1": ro["global_l1"],
                    "directional": ro["directional"],
                }
                entry["DI"] = _compute_DI(ro["directional"])
            us = r.get("update_summary", {})
            if us:
                entry["update_summary"] = us
            summary["arms"].append(entry)
        with open(args.summary_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False, default=str)

    print(f"\nDone. CSV: {args.output_csv}  JSON: {args.summary_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
