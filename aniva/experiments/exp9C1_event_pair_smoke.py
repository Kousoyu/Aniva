"""Phase 9C.1: Event-Pair Eligibility Trace — Smoke.

Fixed gap=500, sweep tau_trace ∈ {80, 200, 500, 1000, 1500}.
Single seed=42, num_pairs=5.
Modes: OFF (amortized) + event_pair.
Arms: L_then_R, R_then_L, simultaneous, separated_control.

Event-pair mechanism (anti-cheat):
  - Each pulse produces a spatial event vector phi (O(N)).
  - A single trace vector r (O(N)) decays between pulses.
  - At pulse onset: eligibility = r × phi → masked outer product update.
  - No arm labels, no "if L_then_R", no last_event string, no threshold crossing.
  - Order signal emerges from which region's trace is warm when the next pulse arrives.

Design doc: docs/phase9C_event_pair_eligibility_design.md
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
ETA_EVENT_PAIR = 0.01
EPS = 1e-12

# ── Geometry & readout (same as 9B.2) ──────────────────────────────────

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


# ── Scheduling (same as 9B.2) ──────────────────────────────────────────

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


def _schedule_diagnostics(schedule, num_pairs, pair_interval):
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


# ── Event-pair mechanism ───────────────────────────────────────────────

def _compute_phi(core, stimulus):
    """Compute spatial event vector for a stimulus.

    Returns phi ∈ R^N where phi[uid] > 0 for units within stimulus radius.
    No labels — only the spatial pattern matters.
    """
    n = core.config.unit_count
    phi = np.zeros(n, dtype=np.float64)
    stim_pos = np.array(stimulus.position)
    for uid in range(n):
        u = core.units[uid]
        d = np.linalg.norm(np.array(u.position) - stim_pos)
        if d <= stimulus.radius:
            phi[uid] = stimulus.intensity * (1.0 - d / stimulus.radius)
    return phi


def _apply_event_pair_update(core, trace, phi, eta):
    """Masked outer product update: dW_{ij} = eta * trace[i] * phi[j] * A_{ij}.

    Only existing connections (A_{ij}=1) are updated.
    No labels, no arm names — only trace vector × current event vector.
    """
    for conn in core.connections:
        sid, tid = conn.source_id, conn.target_id
        dw = eta * trace[sid] * phi[tid]
        w = conn.weight + dw
        conn.weight = max(-1.0, min(1.0, w))


def _trace_diagnostics(trace, phi, connections, n_units):
    """Extract trace health metrics — no label-dependent logic."""
    trace_mass = float(np.sum(np.abs(trace)))
    phi_mass = float(np.sum(np.abs(phi)))

    # Which units have significant trace (> 1% of max)?
    t_max = float(np.max(trace)) if trace_mass > 0 else 0.0
    significant = trace >= t_max * 0.01 if t_max > 0 else np.zeros(n_units, dtype=bool)
    n_significant = int(np.sum(significant))

    # Overlap: trace-active units that are also phi-active
    phi_active = phi > EPS
    matched = float(np.sum(trace[phi_active]))
    matched_overlap = matched / (phi_mass + EPS)

    # Contamination: trace-active units outside phi region
    if n_significant > 0:
        contamination = float(np.sum(trace[~phi_active])) / (trace_mass + EPS)
    else:
        contamination = 0.0

    # Saturation: fraction of weights at boundaries
    weights = np.array([c.weight for c in connections])
    sat_frac = float(np.mean((np.abs(weights) >= 0.99)))

    return {
        "trace_mass": trace_mass,
        "phi_mass": phi_mass,
        "trace_significant_units": n_significant,
        "matched_overlap": matched_overlap,
        "contamination_overlap": contamination,
        "saturation_frac": sat_frac,
    }


# ── Directional metrics ────────────────────────────────────────────────

def _compute_DI(directional):
    """Direction Index: (|W_L→R|_1 - |W_R→L|_1) / (|W_L→R|_1 + |W_R→L|_1 + eps)."""
    lr = directional.get("L_to_R_l1", 0.0)
    rl = directional.get("R_to_L_l1", 0.0)
    return (lr - rl) / (lr + rl + EPS)


def _compute_OS(di_ltr, di_rtl):
    """Order Separation: DI(L_then_R) - DI(R_then_L).

    Positive OS means L_then_R preferentially shifts toward L→R,
    R_then_L preferentially shifts toward R→L (or at least less L→R).
    """
    return di_ltr - di_rtl


# ── Environment influence (same as 9B.2) ───────────────────────────────

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

def _run_9c_schedule(cfg, steps, schedule, tau_trace, mode):
    """Run one arm under OFF or event_pair mode."""
    core = LifeCore(cfg)
    w0 = np.array([c.weight for c in core.connections], dtype=np.float64)
    n_units = cfg.unit_count

    # Event-pair state (only used in event_pair mode)
    trace = np.zeros(n_units, dtype=np.float64) if mode == "event_pair" else None
    last_pulse_time = 0.0

    # Trace diagnostic accumulators (collected at each event-pair update)
    trace_diags = []
    lr_update_total = 0.0
    rl_update_total = 0.0

    elog = []
    aevs = []
    idx = 0

    # Pre-compute stimulus→phi mapping once (same for all pulses)
    phi_cache = {}
    if mode == "event_pair":
        phi_cache["L"] = _compute_phi(core, L_STIM)
        phi_cache["R"] = _compute_phi(core, R_STIM)

    # Build event-start lookup: step → [(side, stim)]
    event_starts = {}
    for t, side, dur in schedule:
        event_starts.setdefault(t, []).append(side)

    for s in range(steps):
        # ── Event-pair update at pulse ONSET ──
        if mode == "event_pair" and s in event_starts:
            sides = event_starts[s]

            # Decay trace
            dt = s - last_pulse_time if last_pulse_time > 0 else 0.0
            if dt > 0 and tau_trace > 0:
                decay_factor = math.exp(-dt / tau_trace)
                trace *= decay_factor

            # Compute combined phi for all pulses starting at this step
            phi = np.zeros(n_units, dtype=np.float64)
            for side in sides:
                phi += phi_cache[side]

            # Masked outer product update: r ⊗ phi
            if np.sum(np.abs(trace)) > EPS and np.sum(np.abs(phi)) > EPS:
                # Measure pre-update directional weights for logging
                pre_lr = sum(
                    abs(c.weight - w0[i])
                    for i, c in enumerate(core.connections)
                    if _classify_connection(
                        core.units[c.source_id].position,
                        core.units[c.target_id].position
                    ) == "L→R"
                ) / max(1, sum(1 for c in core.connections
                              if _classify_connection(
                                  core.units[c.source_id].position,
                                  core.units[c.target_id].position
                              ) == "L→R"))

                pre_rl = sum(
                    abs(c.weight - w0[i])
                    for i, c in enumerate(core.connections)
                    if _classify_connection(
                        core.units[c.source_id].position,
                        core.units[c.target_id].position
                    ) == "R→L"
                ) / max(1, sum(1 for c in core.connections
                              if _classify_connection(
                                  core.units[c.source_id].position,
                                  core.units[c.target_id].position
                              ) == "R→L"))

                _apply_event_pair_update(core, trace, phi, ETA_EVENT_PAIR)

                # Measure post-update directional deltas (for diagnostics only)
                post_lr = sum(
                    abs(c.weight - w0[i])
                    for i, c in enumerate(core.connections)
                    if _classify_connection(
                        core.units[c.source_id].position,
                        core.units[c.target_id].position
                    ) == "L→R"
                ) / max(1, sum(1 for c in core.connections
                              if _classify_connection(
                                  core.units[c.source_id].position,
                                  core.units[c.target_id].position
                              ) == "L→R"))

                post_rl = sum(
                    abs(c.weight - w0[i])
                    for i, c in enumerate(core.connections)
                    if _classify_connection(
                        core.units[c.source_id].position,
                        core.units[c.target_id].position
                    ) == "R→L"
                ) / max(1, sum(1 for c in core.connections
                              if _classify_connection(
                                  core.units[c.source_id].position,
                                  core.units[c.target_id].position
                              ) == "R→L"))

                lr_update_total += post_lr - pre_lr
                rl_update_total += post_rl - pre_rl

                # Record trace diagnostics
                diag = _trace_diagnostics(trace, phi, core.connections, n_units)
                diag["step"] = s
                diag["dt_since_last"] = dt
                trace_diags.append(diag)

            # Update trace: r += phi
            trace += phi
            last_pulse_time = float(s)

        # ── Feed active stimulus events to core ──
        while idx < len(schedule) and schedule[idx][0] <= s:
            t, lb, dur = schedule[idx]
            if t == s:
                stim = L_STIM if lb == "L" else R_STIM
                aevs.append(StimulusEvent(stimulus=stim, start_step=s, duration_steps=dur))
                elog.append({"step": s, "side": lb, "duration": dur})
            idx += 1

        core.step(env_influences=_influences_at_step(aevs, s, core))

    # ── Pack results ──
    result = _pack(core, w0, elog)
    result["trace_diagnostics"] = {
        "events": trace_diags,
        "lr_update_l1_total": lr_update_total,
        "rl_update_l1_total": rl_update_total,
    }
    # Aggregate trace diags
    if trace_diags:
        result["trace_summary"] = {
            "n_updates": len(trace_diags),
            "mean_trace_mass": float(np.mean([d["trace_mass"] for d in trace_diags])),
            "mean_matched_overlap": float(np.mean([d["matched_overlap"] for d in trace_diags])),
            "mean_contamination": float(np.mean([d["contamination_overlap"] for d in trace_diags])),
            "final_saturation_frac": trace_diags[-1]["saturation_frac"],
            "mean_dt_between_pulses": float(np.mean([d["dt_since_last"] for d in trace_diags if d["dt_since_last"] > 0])),
        }
    else:
        result["trace_summary"] = {}
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


# ── Main ────────────────────────────────────────────────────────────────

def main(argv=None):
    import sys as _sys
    _sys.stdout.reconfigure(line_buffering=True)

    p = argparse.ArgumentParser(description="Phase 9C.1: Event-Pair Eligibility Trace — Smoke")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--gap", type=int, default=DEFAULT_GAP,
                   help="Fixed paired-pulse gap (default: 500)")
    p.add_argument("--taus", type=int, nargs="+", default=[80, 200, 500, 1000, 1500])
    p.add_argument("--num-pairs", type=int, default=5)
    p.add_argument("--rest-window", type=int, default=500)
    p.add_argument("--eta", type=float, default=ETA_EVENT_PAIR,
                   help="Event-pair learning rate")
    p.add_argument("--output-csv", type=str, default="results/phase9C1_event_pair_smoke.csv")
    p.add_argument("--summary-json", type=str, default="results/phase9C1_event_pair_smoke_summary.json")
    p.add_argument("--no-homeostasis", action="store_true")
    args = p.parse_args(argv)

    arm_names = ["L_then_R", "R_then_L", "simultaneous", "separated_control"]
    modes = ["OFF", "event_pair"]
    taus = args.taus

    pair_interval, total_steps = _compute_scheduling_params(args.gap, args.num_pairs, args.rest_window)

    n_arms = len(arm_names)
    n_taus = len(taus)
    off_runs = n_arms  # OFF amortized: 1 run per arm
    ep_runs = n_arms * n_taus  # event_pair: per-arm × per-tau
    total_runs = off_runs + ep_runs

    print(f"Phase 9C.1: Event-Pair Eligibility Trace — Smoke")
    print(f"  seed={args.seed}  gap={args.gap}  taus={taus}  num_pairs={args.num_pairs}")
    print(f"  rest_window={args.rest_window}  warmup={WARMUP}  tail_buffer={TAIL_BUFFER}")
    print(f"  eta={args.eta}  pulse_dur={PULSE_DURATION}")
    print(f"  pair_interval={pair_interval}  total_steps={total_steps}")
    print(f"  modes: {' | '.join(modes)}")
    print(f"  (OFF amortized: {off_runs} arm-runs + event_pair: {ep_runs} arm-runs = {total_runs} total)")
    print()

    all_results = []
    t0_wall = time.time()

    # ── Phase 1: OFF baseline (amortized — independent of tau) ──
    print(f"{'='*70}\n  OFF baseline (amortized, gap={args.gap})\n{'='*70}")

    cfg_off = AnivaConfig(unit_count=300, seed=args.seed)
    cfg_off.homeostasis_enabled = not args.no_homeostasis
    cfg_off.homeostatic_target_abs_weight = 0.30
    cfg_off.homeostatic_rate = 1.0
    cfg_off.temporal_plasticity_enabled = False

    for arm in arm_names:
        sched = _make_schedule(arm, args.gap, pair_interval, args.num_pairs)
        r = _run_9c_schedule(cfg_off, total_steps, sched, tau_trace=0, mode="OFF")
        r["arm"], r["seed"], r["mode"], r["gap"] = arm, args.seed, "OFF", args.gap
        r["tau_trace"] = 0
        r["scheduling"] = _schedule_diagnostics(sched, args.num_pairs, pair_interval)
        all_results.append(r)

        di = _compute_DI(r["readout"]["directional"])
        print(f"  {arm:>20s}  DI={di:+.6e}  "
              f"L_to_R_l1={r['readout']['directional']['L_to_R_l1']:.4e}  "
              f"R_to_L_l1={r['readout']['directional']['R_to_L_l1']:.4e}  "
              f"ev_L={r['event_count_L']}  ev_R={r['event_count_R']}")
    print()

    # ── Phase 2: event_pair sweep ──
    for tau in taus:
        print(f"{'='*70}\n  event_pair  tau_trace={tau}  gap={args.gap}\n{'='*70}")

        cfg_ep = AnivaConfig(unit_count=300, seed=args.seed)
        cfg_ep.homeostasis_enabled = not args.no_homeostasis
        cfg_ep.homeostatic_target_abs_weight = 0.30
        cfg_ep.homeostatic_rate = 1.0
        cfg_ep.temporal_plasticity_enabled = False  # core temporal plasticity OFF; event-pair is manual

        for arm in arm_names:
            sched = _make_schedule(arm, args.gap, pair_interval, args.num_pairs)
            r = _run_9c_schedule(cfg_ep, total_steps, sched, tau_trace=tau, mode="event_pair")
            r["arm"], r["seed"], r["mode"], r["gap"] = arm, args.seed, "event_pair", args.gap
            r["tau_trace"] = tau
            r["scheduling"] = _schedule_diagnostics(sched, args.num_pairs, pair_interval)
            all_results.append(r)

            di = _compute_DI(r["readout"]["directional"])
            ts = r.get("trace_summary", {})
            sat = ts.get("final_saturation_frac", -1)
            n_up = ts.get("n_updates", 0)
            overlap = ts.get("mean_matched_overlap", -1)
            print(f"  {arm:>20s}  DI={di:+.6e}  "
                  f"L_to_R_l1={r['readout']['directional']['L_to_R_l1']:.4e}  "
                  f"R_to_L_l1={r['readout']['directional']['R_to_L_l1']:.4e}  "
                  f"updates={n_up}  overlap={overlap:.3f}  sat={sat:.3f}")
        print()

    wall_s = time.time() - t0_wall

    # ── KEY RESULT: OS by tau_trace ──
    print(f"{'='*90}")
    print(f"Phase 9C.1 — KEY RESULT: OS by tau_trace (gap={args.gap})")
    print(f"{'='*90}")
    print(f"  {'tau_trace':>10s} {'DI(L_then_R)':>14s} {'DI(R_then_L)':>14s} "
          f"{'OS':>12s} {'DI(simul)':>12s} {'DI(sep_ctrl)':>12s} {'OK?':>5s}")
    print(f"  {'-'*85}")

    off_ltr = next(r for r in all_results if r["arm"] == "L_then_R" and r["mode"] == "OFF")
    off_rtl = next(r for r in all_results if r["arm"] == "R_then_L" and r["mode"] == "OFF")
    off_di_ltr = _compute_DI(off_ltr["readout"]["directional"])
    off_di_rtl = _compute_DI(off_rtl["readout"]["directional"])
    off_os = _compute_OS(off_di_ltr, off_di_rtl)

    print(f"  {'OFF':>10s} {off_di_ltr:>+14.6e} {off_di_rtl:>+14.6e} {off_os:>+12.6e}")

    os_by_tau = {}
    for tau in taus:
        ltr = next(r for r in all_results
                   if r["arm"] == "L_then_R" and r["mode"] == "event_pair" and r["tau_trace"] == tau)
        rtl = next(r for r in all_results
                   if r["arm"] == "R_then_L" and r["mode"] == "event_pair" and r["tau_trace"] == tau)
        sim = next(r for r in all_results
                   if r["arm"] == "simultaneous" and r["mode"] == "event_pair" and r["tau_trace"] == tau)
        sep = next(r for r in all_results
                   if r["arm"] == "separated_control" and r["mode"] == "event_pair" and r["tau_trace"] == tau)

        di_ltr = _compute_DI(ltr["readout"]["directional"])
        di_rtl = _compute_DI(rtl["readout"]["directional"])
        di_sim = _compute_DI(sim["readout"]["directional"])
        di_sep = _compute_DI(sep["readout"]["directional"])
        os = _compute_OS(di_ltr, di_rtl)
        os_by_tau[tau] = os

        # Heuristic: OS should be non-trivial and > 3× OFF baseline
        os_ok = abs(os) > 3 * max(abs(off_os), EPS) and abs(di_sim) < abs(os) * 0.5
        print(f"  {tau:>10d} {di_ltr:>+14.6e} {di_rtl:>+14.6e} {os:>+12.6e} "
              f"{di_sim:>+12.6e} {di_sep:>+12.6e} {'OK' if os_ok else '':>5s}")

    # ── Trace diagnostics summary ──
    print(f"\n{'='*90}")
    print(f"Phase 9C.1 — Trace Diagnostics (event_pair mode, L_then_R arm)")
    print(f"{'='*90}")
    print(f"  {'tau_trace':>10s} {'n_updates':>10s} {'trace_mass':>12s} "
          f"{'overlap':>10s} {'contamination':>14s} {'saturation':>10s}")
    print(f"  {'-'*70}")
    for tau in taus:
        ltr = next(r for r in all_results
                   if r["arm"] == "L_then_R" and r["mode"] == "event_pair" and r["tau_trace"] == tau)
        ts = ltr.get("trace_summary", {})
        print(f"  {tau:>10d} {ts.get('n_updates', 0):>10d} "
              f"{ts.get('mean_trace_mass', 0):>12.4e} "
              f"{ts.get('mean_matched_overlap', 0):>10.4f} "
              f"{ts.get('mean_contamination', 0):>14.4f} "
              f"{ts.get('final_saturation_frac', 0):>10.4f}")

    # ── Scheduling verification ──
    print(f"\n{'='*90}")
    print(f"Phase 9C.1 — Scheduling Verification")
    print(f"{'='*90}")
    print(f"  {'arm':>20s} {'target':>7s} {'L_ev':>5s} {'R_ev':>5s} {'OK':>5s}")
    for arm in arm_names:
        r = next(r for r in all_results if r["arm"] == arm and r["mode"] == "OFF")
        ok = (r["event_count_L"] == args.num_pairs and r["event_count_R"] == args.num_pairs)
        print(f"  {arm:>20s} {args.num_pairs:>7d} {r['event_count_L']:>5d} "
              f"{r['event_count_R']:>5d} {'OK' if ok else 'FAIL':>5s}")

    # ── Sanity checks ──
    print(f"\n{'='*90}")
    print(f"Sanity Checks")
    print(f"{'='*90}")
    has_nan = any(
        np.isnan(r["final_weight_l1"]) for r in all_results
    )
    has_saturation = any(
        r.get("trace_summary", {}).get("final_saturation_frac", 0) > 0.9
        for r in all_results if r["mode"] == "event_pair"
    )
    all_ok = all(
        r["event_count_L"] == args.num_pairs and r["event_count_R"] == args.num_pairs
        for r in all_results if r["mode"] == "OFF"
    )
    print(f"  NaN detected: {'YES [WARN]' if has_nan else 'none'}")
    print(f"  Saturation > 0.9: {'YES [WARN]' if has_saturation else 'none'}")
    print(f"  Schedule OK (OFF): {'ALL OK' if all_ok else 'FAILURES DETECTED [WARN]'}")
    print(f"  Wall time: {wall_s:.1f}s")

    # ── Save CSV ──
    if args.output_csv:
        rows = []
        for r in all_results:
            d = r["readout"]["directional"]
            sd = r.get("scheduling", {})
            ts = r.get("trace_summary", {})
            td = r.get("trace_diagnostics", {})
            di = _compute_DI(d)
            row = {
                "seed": r["seed"], "gap": r["gap"], "tau_trace": r["tau_trace"],
                "mode": r["mode"], "arm": r["arm"],
                "num_pairs": args.num_pairs,
                "event_count_L": r["event_count_L"],
                "event_count_R": r["event_count_R"],
                "schedule_ok": (r["event_count_L"] == args.num_pairs and r["event_count_R"] == args.num_pairs),
                "lr_weight_l1": d["L_to_R_l1"],
                "rl_weight_l1": d["R_to_L_l1"],
                "DI": di,
                "trace_mass_before_second_event": ts.get("mean_trace_mass", 0),
                "matched_overlap": ts.get("mean_matched_overlap", 0),
                "contamination_overlap": ts.get("mean_contamination", 0),
                "lr_update_l1": td.get("lr_update_l1_total", 0),
                "rl_update_l1": td.get("rl_update_l1_total", 0),
                "saturation_frac": ts.get("final_saturation_frac", 0),
                "n_event_pair_updates": ts.get("n_updates", 0),
                "runtime_s": wall_s,
            }
            rows.append(row)
        fieldnames = list(rows[0].keys())
        with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)

    # ── Save JSON ──
    if args.summary_json:
        # Compute OS for summary
        os_summary = {}
        for tau in taus:
            ltr = next((r for r in all_results
                        if r["arm"] == "L_then_R" and r["mode"] == "event_pair" and r["tau_trace"] == tau), None)
            rtl = next((r for r in all_results
                        if r["arm"] == "R_then_L" and r["mode"] == "event_pair" and r["tau_trace"] == tau), None)
            if ltr and rtl:
                os_summary[str(tau)] = _compute_OS(
                    _compute_DI(ltr["readout"]["directional"]),
                    _compute_DI(rtl["readout"]["directional"])
                )

        summary = {
            "experiment": "phase9C1_event_pair_smoke",
            "params": {
                "seed": args.seed, "gap": args.gap, "taus": taus,
                "num_pairs": args.num_pairs, "rest_window": args.rest_window,
                "eta": args.eta, "pulse_duration": PULSE_DURATION,
                "warmup": WARMUP, "tail_buffer": TAIL_BUFFER,
            },
            "scheduling": {
                "pair_interval": pair_interval,
                "total_steps": total_steps,
            },
            "off_baseline": {
                "DI_L_then_R": off_di_ltr,
                "DI_R_then_L": off_di_rtl,
                "OS_off": off_os,
            },
            "os_by_tau": os_summary,
            "sanity": {
                "has_nan": has_nan,
                "has_saturation": has_saturation,
                "schedule_all_ok": all_ok,
                "wall_time_s": wall_s,
            },
            "arms": [],
        }
        for r in all_results:
            entry = {
                "seed": r["seed"], "gap": r["gap"], "tau_trace": r["tau_trace"],
                "arm": r["arm"], "mode": r["mode"],
                "event_count_L": r["event_count_L"], "event_count_R": r["event_count_R"],
                "total_events": r["total_events"], "final_weight_l1": r["final_weight_l1"],
                "scheduling": r.get("scheduling", {}),
            }
            ro = r.get("readout")
            if ro:
                entry["readout"] = {
                    "global_l1": ro["global_l1"],
                    "regional": ro["regional"],
                    "directional": ro["directional"],
                }
                entry["DI"] = _compute_DI(ro["directional"])
            ts = r.get("trace_summary", {})
            if ts:
                entry["trace_summary"] = ts
            summary["arms"].append(entry)
        with open(args.summary_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False, default=str)

    print(f"\nDone. {len(all_results)} arm-runs.  CSV: {args.output_csv}  JSON: {args.summary_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
