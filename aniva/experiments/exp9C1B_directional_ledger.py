"""Phase 9C.1B: Directional Ledger Diagnostic.

NOT a new experiment. This is a surgical diagnostic to answer:
  Where exactly does the directional signal get lost?

  1. Within-pair — no directionality even at per-pulse level?
  2. Cross-pair contamination — direction exists but gets cancelled?
  3. Homeostasis / final-DI masking — dW has direction but final W doesn't?
  4. Event vector too wide — update is non-specific?

Plus two lightweight ablations:
  A. no-homeostasis: does turning off homeostasis unmask directional dW?
  B. long-rest (rest=5*tau): does eliminating cross-pair trace rescue direction?

Fixed: seed=42, gap=500, tau_trace=1000, num_pairs=5, target=1e-4.

Anti-cheat: arm/L/R labels used ONLY for offline ledger classification and
logging. The plasticity update path uses NO labels — same mechanism as 9C.1A.
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
EPS = 1e-12

# ── Geometry ────────────────────────────────────────────────────────────

def _unit_region(pos):
    """Return 'L', 'R', or 'M' for a unit position. Used for ANALYSIS only."""
    x = pos[0]
    if x < -0.1:
        return "L"
    elif x > 0.1:
        return "R"
    return "M"


def _classify_connection(sp, tp):
    s = _unit_region(sp)
    t = _unit_region(tp)
    return f"{s}→{t}"


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
                         "l1": float(np.mean(np.abs(rd))) if len(rd) > 0 else 0.0,
                         "signed_mean": float(np.mean(rd)) if len(rd) > 0 else 0.0}
    return {
        "global_l1": float(np.mean(np.abs(deltas))),
        "regional": regional,
        "directional": {
            "L_to_R_l1": regional.get("L→R", {}).get("l1", 0.0),
            "R_to_L_l1": regional.get("R→L", {}).get("l1", 0.0),
        },
    }


def _compute_DI(directional):
    lr = directional.get("L_to_R_l1", 0.0)
    rl = directional.get("R_to_L_l1", 0.0)
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


# ── Event-pair mechanism ────────────────────────────────────────────────

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


def _region_mask(core, region):
    """Boolean mask over units for a given region. ANALYSIS ONLY."""
    return np.array([_unit_region(core.units[uid].position) == region
                     for uid in range(core.config.unit_count)])


def _apply_update_and_ledger(core, trace, phi, target_l1, connections, conn_regions,
                              unit_regions):
    """Apply L1-normalized update AND return per-direction deltas.

    Returns (ledger_entry, accumulated_dW_LR, accumulated_dW_RL).
    Labels used ONLY for post-hoc ledger — NOT in the update rule.
    """
    n_conns = len(connections)

    # Compute raw deltas — NO labels in this loop
    raw = np.zeros(n_conns, dtype=np.float64)
    for k, conn in enumerate(connections):
        raw[k] = trace[conn.source_id] * phi[conn.target_id]

    raw_l1 = float(np.sum(np.abs(raw)))
    if raw_l1 < EPS:
        return None, 0.0, 0.0

    scale = target_l1 / raw_l1

    # Apply update — NO labels
    dW_by_conn = np.zeros(n_conns, dtype=np.float64)
    for k, conn in enumerate(connections):
        dw = scale * raw[k]
        w = conn.weight + dw
        conn.weight = max(-1.0, min(1.0, w))
        dW_by_conn[k] = dw

    # ── Per-direction accounting (analysis only, NOT in update path) ──
    dw_lr = 0.0
    dw_rl = 0.0
    for k, reg in enumerate(conn_regions):
        if reg == "L→R":
            dw_lr += abs(dW_by_conn[k])
        elif reg == "R→L":
            dw_rl += abs(dW_by_conn[k])

    return {
        "raw_l1": raw_l1,
        "scale": scale,
        "dW_L_to_R_l1": dw_lr,
        "dW_R_to_L_l1": dw_rl,
        "dW_total_l1": float(np.sum(np.abs(dW_by_conn))),
    }, dw_lr, dw_rl


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


# ── Core simulation with per-event ledger ───────────────────────────────

def _run_with_ledger(cfg, steps, schedule, tau_trace, target_l1, mode, arm):
    """Run simulation and produce per-event directional ledger."""
    core = LifeCore(cfg)
    w0 = np.array([c.weight for c in core.connections], dtype=np.float64)
    n_units = cfg.unit_count
    connections = list(core.connections)

    # Pre-compute region assignments (ANALYSIS ONLY)
    unit_regions = np.array([_unit_region(core.units[uid].position) for uid in range(n_units)])
    conn_regions = [_classify_connection(core.units[c.source_id].position,
                                          core.units[c.target_id].position)
                    for c in connections]
    mask_L = unit_regions == "L"
    mask_R = unit_regions == "R"

    trace = np.zeros(n_units, dtype=np.float64) if mode == "event_pair" else None
    last_pulse_time = 0.0

    # Accumulated dW ledger
    acc_dW_LR = 0.0  # total |dW| applied to L→R connections
    acc_dW_RL = 0.0  # total |dW| applied to R→L connections

    ledger = []
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

    # Track which event in the schedule we're at (1-indexed, for analysis)
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

            # ── Pre-update trace diagnostics (analysis only) ──
            trace_mass = float(np.sum(np.abs(trace)))
            trace_L_mass = float(np.sum(np.abs(trace[mask_L])))
            trace_R_mass = float(np.sum(np.abs(trace[mask_R])))
            phi_L_mass = float(np.sum(np.abs(phi[mask_L])))
            phi_R_mass = float(np.sum(np.abs(phi[mask_R])))

            if trace_mass > EPS and np.sum(np.abs(phi)) > EPS:
                # Determine pulse region for analysis classification
                if len(sides) == 1:
                    pulse_region = sides[0]
                else:
                    pulse_region = "LR"

                # Determine pair index (heuristic: each pair has 2 events)
                pair_idx = (update_event_idx + 1) // 2

                update_info, dw_lr, dw_rl = _apply_update_and_ledger(
                    core, trace, phi, target_l1, connections, conn_regions, unit_regions)

                if update_info is not None:
                    acc_dW_LR += dw_lr
                    acc_dW_RL += dw_rl

                    # Classify this update (analysis only, uses arm knowledge)
                    # within_pair: dW in the direction this arm EXPECTS
                    # cross_pair: dW in the OPPOSITE direction
                    # For sequential arms, R pulses produce dW_LR, L pulses produce dW_RL.
                    # The "expected" direction is L→R for L_then_R, R→L for R_then_L.
                    if arm == "L_then_R":
                        within_pair = dw_lr
                        cross_pair = dw_rl
                    elif arm == "R_then_L":
                        within_pair = dw_rl
                        cross_pair = dw_lr
                    elif arm == "simultaneous":
                        within_pair = (dw_lr + dw_rl) / 2.0
                        cross_pair = (dw_lr + dw_rl) / 2.0
                    else:  # separated_control — L always first, same expectation as L_then_R
                        within_pair = dw_lr
                        cross_pair = dw_rl

                    # Accumulated dW DI/OS
                    acc_dW_DI = ((acc_dW_LR - acc_dW_RL) /
                                 (acc_dW_LR + acc_dW_RL + EPS))

                    # Current structural DI (from connection weights)
                    w_now = np.array([c.weight for c in connections])
                    deltas = w_now - w0
                    lr_deltas = []
                    rl_deltas = []
                    for k, reg in enumerate(conn_regions):
                        if reg == "L→R":
                            lr_deltas.append(abs(deltas[k]))
                        elif reg == "R→L":
                            rl_deltas.append(abs(deltas[k]))
                    lr_l1 = float(np.mean(lr_deltas)) if lr_deltas else 0.0
                    rl_l1 = float(np.mean(rl_deltas)) if rl_deltas else 0.0
                    current_DI = (lr_l1 - rl_l1) / (lr_l1 + rl_l1 + EPS)

                    ledger.append({
                        "event_index": update_event_idx,
                        "pair_index": pair_idx,
                        "pulse_step": s,
                        "pulse_region": pulse_region,
                        "is_within_pair_event": (update_event_idx % 2 == 1),
                        "dt_since_last_pulse": dt,
                        "trace_mass_before": trace_mass,
                        "trace_L_mass_before": trace_L_mass,
                        "trace_R_mass_before": trace_R_mass,
                        "current_L_mass": phi_L_mass,
                        "current_R_mass": phi_R_mass,
                        "raw_update_l1": update_info["raw_l1"],
                        "normalized_update_l1": update_info["dW_total_l1"],
                        "dW_L_to_R_l1": dw_lr,
                        "dW_R_to_L_l1": dw_rl,
                        "within_pair_directional": within_pair,
                        "cross_pair_contamination": cross_pair,
                        "contamination_ratio": cross_pair / (within_pair + cross_pair + EPS),
                        "current_DI": current_DI,
                        "accumulated_dW_DI": acc_dW_DI,
                        "accumulated_dW_LR_total": acc_dW_LR,
                        "accumulated_dW_RL_total": acc_dW_RL,
                    })

                update_event_idx += 1

            # Update trace with current phi
            trace += phi
            last_pulse_time = float(s)

        # Feed active stimulus events to core
        while idx < len(schedule) and schedule[idx][0] <= s:
            t, lb, dur = schedule[idx]
            if t == s:
                stim = L_STIM if lb == "L" else R_STIM
                aevs.append(StimulusEvent(stimulus=stim, start_step=s, duration_steps=dur))
                elog.append({"step": s, "side": lb, "duration": dur})
            idx += 1

        core.step(env_influences=_influences_at_step(aevs, s, core))

    # Final structural readout
    final_readout = _structural_readout(core, w0)
    final_DI = _compute_DI(final_readout["directional"])

    # Accumulated dW metrics
    acc_DI = ((acc_dW_LR - acc_dW_RL) / (acc_dW_LR + acc_dW_RL + EPS))
    acc_OS = acc_DI  # For single-arm, OS ≡ DI

    # Tally within-pair vs cross-pair from ledger
    total_within = sum(e["within_pair_directional"] for e in ledger)
    total_cross = sum(e["cross_pair_contamination"] for e in ledger)
    overall_contamination = total_cross / (total_within + total_cross + EPS)

    nL = sum(1 for e in elog if e["side"] == "L")
    nR = sum(1 for e in elog if e["side"] == "R")

    return {
        "arm": arm,
        "event_count_L": nL,
        "event_count_R": nR,
        "total_events": len(elog),
        "ledger": ledger,
        "final_readout": final_readout,
        "final_DI": final_DI,
        "acc_dW_LR_total": acc_dW_LR,
        "acc_dW_RL_total": acc_dW_RL,
        "acc_dW_DI": acc_DI,
        "total_within_pair_dW": total_within,
        "total_cross_pair_dW": total_cross,
        "overall_contamination_ratio": overall_contamination,
        "n_ledger_entries": len(ledger),
    }


# ── Main ────────────────────────────────────────────────────────────────

def main(argv=None):
    import sys as _sys
    _sys.stdout.reconfigure(line_buffering=True)

    p = argparse.ArgumentParser(
        description="Phase 9C.1B: Directional Ledger Diagnostic")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--gap", type=int, default=500)
    p.add_argument("--tau", type=int, default=1000)
    p.add_argument("--num-pairs", type=int, default=5)
    p.add_argument("--rest-window", type=int, default=500)
    p.add_argument("--target", type=float, default=1e-4)
    p.add_argument("--output-csv", type=str,
                   default="results/phase9C1B_directional_ledger.csv")
    p.add_argument("--summary-json", type=str,
                   default="results/phase9C1B_directional_ledger_summary.json")
    p.add_argument("--no-homeostasis", action="store_true")
    p.add_argument("--long-rest", action="store_true",
                   help="Use rest_window = 5*tau_trace to eliminate cross-pair trace")
    args = p.parse_args(argv)

    rest_window = args.rest_window
    arm_names = ["L_then_R", "R_then_L", "simultaneous", "separated_control"]

    if args.long_rest:
        rest_window = 5 * args.tau
        arm_names = ["L_then_R", "R_then_L"]  # only paired arms

    pair_interval = args.gap + PULSE_DURATION + rest_window
    total_steps = WARMUP + args.num_pairs * pair_interval + TAIL_BUFFER

    n_arms = len(arm_names)
    n_runs = n_arms + 1  # +1 OFF baseline

    label = "LONG-REST" if args.long_rest else (
        "NO-HOMEOSTASIS" if args.no_homeostasis else "BASELINE")
    print(f"Phase 9C.1B: Directional Ledger Diagnostic [{label}]")
    print(f"  seed={args.seed}  gap={args.gap}  tau_trace={args.tau}")
    print(f"  num_pairs={args.num_pairs}  target={args.target:.0e}")
    print(f"  rest_window={rest_window}  pair_interval={pair_interval}")
    print(f"  total_steps={total_steps}  arms={arm_names}")
    print()

    t0 = time.time()
    all_ledgers = {}

    # ── OFF baseline ──
    cfg_off = AnivaConfig(unit_count=300, seed=args.seed)
    cfg_off.homeostasis_enabled = not args.no_homeostasis
    cfg_off.homeostatic_target_abs_weight = 0.30
    cfg_off.homeostatic_rate = 0.0 if args.no_homeostasis else 1.0
    cfg_off.temporal_plasticity_enabled = False

    # Run one arm in OFF mode for baseline DI reference
    sched_off = _make_schedule("L_then_R", args.gap, pair_interval, args.num_pairs)
    off_result = _run_with_ledger(cfg_off, total_steps, sched_off,
                                   tau_trace=0, target_l1=0, mode="OFF", arm="L_then_R")
    off_DI = off_result["final_DI"]
    print(f"  OFF baseline DI (L_then_R): {off_DI:+.6e}")

    sched_off2 = _make_schedule("R_then_L", args.gap, pair_interval, args.num_pairs)
    off_r2 = _run_with_ledger(cfg_off, total_steps, sched_off2,
                               tau_trace=0, target_l1=0, mode="OFF", arm="R_then_L")
    off_DI_rtl = off_r2["final_DI"]
    off_OS = off_DI - off_DI_rtl
    print(f"  OFF baseline DI (R_then_L): {off_DI_rtl:+.6e}")
    print(f"  OFF baseline OS: {off_OS:+.2e}")
    print()

    # ── event_pair per arm ──
    cfg_ep = AnivaConfig(unit_count=300, seed=args.seed)
    cfg_ep.homeostasis_enabled = not args.no_homeostasis
    cfg_ep.homeostatic_target_abs_weight = 0.30
    cfg_ep.homeostatic_rate = 0.0 if args.no_homeostasis else 1.0
    cfg_ep.temporal_plasticity_enabled = False

    final_DIs = {}

    for arm in arm_names:
        print(f"{'='*70}")
        print(f"  {arm}")
        print(f"{'='*70}")

        sched = _make_schedule(arm, args.gap, pair_interval, args.num_pairs)
        result = _run_with_ledger(cfg_ep, total_steps, sched,
                                   tau_trace=args.tau, target_l1=args.target,
                                   mode="event_pair", arm=arm)
        all_ledgers[arm] = result
        final_DIs[arm] = result["final_DI"]

        # Print per-event ledger
        print(f"  {'Ev#':>4s} {'Pair':>5s} {'Step':>6s} {'Reg':>3s} "
              f"{'trace_L':>10s} {'trace_R':>10s} {'cur_L':>10s} {'cur_R':>10s} "
              f"{'dW_LR':>10s} {'dW_RL':>10s} {'within':>10s} {'cross':>10s} "
              f"{'contam%':>8s} {'acc_DI':>12s} {'cur_DI':>12s}")
        print(f"  {'-'*120}")
        for e in result["ledger"]:
            print(f"  {e['event_index']:>4d} {e['pair_index']:>5d} {e['pulse_step']:>6d} "
                  f"{e['pulse_region']:>3s} "
                  f"{e['trace_L_mass_before']:>10.2e} {e['trace_R_mass_before']:>10.2e} "
                  f"{e['current_L_mass']:>10.2e} {e['current_R_mass']:>10.2e} "
                  f"{e['dW_L_to_R_l1']:>10.2e} {e['dW_R_to_L_l1']:>10.2e} "
                  f"{e['within_pair_directional']:>10.2e} {e['cross_pair_contamination']:>10.2e} "
                  f"{e['contamination_ratio']*100:>7.1f}% "
                  f"{e['accumulated_dW_DI']:>+12.6e} {e['current_DI']:>+12.6e}")

        print(f"\n  Summary:")
        print(f"    within-pair total dW:    {result['total_within_pair_dW']:.2e}")
        print(f"    cross-pair total dW:     {result['total_cross_pair_dW']:.2e}")
        print(f"    contamination ratio:     {result['overall_contamination_ratio']:.4f}")
        print(f"    acc_dW_LR_total:         {result['acc_dW_LR_total']:.2e}")
        print(f"    acc_dW_RL_total:         {result['acc_dW_RL_total']:.2e}")
        print(f"    acc_dW_DI:               {result['acc_dW_DI']:+.6e}")
        print(f"    final_DI:                {result['final_DI']:+.6e}")
        print(f"    OFF baseline DI (L→R):   {off_DI:+.6e}")
        print()

    # ── Cross-arm analysis ──
    print(f"{'='*90}")
    print(f"DIAGNOSTIC SUMMARY [{label}]")
    print(f"{'='*90}")

    ltr = all_ledgers.get("L_then_R", {})
    rtl = all_ledgers.get("R_then_L", {})
    sim = all_ledgers.get("simultaneous", {})
    sep = all_ledgers.get("separated_control", {})

    # Q1: Within-pair directionality
    if ltr and rtl:
        ltr_within = ltr.get("total_within_pair_dW", 0)
        ltr_cross = ltr.get("total_cross_pair_dW", 0)
        rtl_within = rtl.get("total_within_pair_dW", 0)
        rtl_cross = rtl.get("total_cross_pair_dW", 0)

        print(f"\n  Q1: Does within-pair update carry directional signal?")
        print(f"    L_then_R:  within={ltr_within:.2e}  cross={ltr_cross:.2e}  "
              f"contam={ltr.get('overall_contamination_ratio',0):.3f}")
        print(f"    R_then_L:  within={rtl_within:.2e}  cross={rtl_cross:.2e}  "
              f"contam={rtl.get('overall_contamination_ratio',0):.3f}")

    # Q2: Cross-pair contamination
    print(f"\n  Q2: Is cross-pair contamination present?")
    if ltr:
        contam = ltr.get("overall_contamination_ratio", 0)
        if contam > 0.3:
            print(f"    YES — contamination ratio={contam:.3f} (>0.3). Cross-pair trace is significant.")
        elif contam > 0.1:
            print(f"    MODERATE — contamination ratio={contam:.3f} (0.1-0.3).")
        else:
            print(f"    LOW — contamination ratio={contam:.3f} (<0.1). Cross-pair trace is minimal.")

    # Q3: accumulated_dW_OS vs final_DI
    print(f"\n  Q3: Does accumulated dW show direction that final DI misses?")
    if ltr and rtl:
        acc_dW_OS = ltr.get("acc_dW_DI", 0) - rtl.get("acc_dW_DI", 0)
        final_OS = ltr.get("final_DI", 0) - rtl.get("final_DI", 0)
        print(f"    acc_dW_OS  =  {acc_dW_OS:+.6e}")
        print(f"    final_OS   =  {final_OS:+.6e}")
        print(f"    OFF_OS     =  {off_OS:+.2e}")
        if abs(acc_dW_OS) > 3 * max(abs(off_OS), EPS) and abs(final_OS) < abs(acc_dW_OS) * 0.3:
            print(f"    ** MISMATCH: dW has direction but final W doesn't → homeostasis/initial bias masking **")
        elif abs(acc_dW_OS) > 3 * max(abs(off_OS), EPS):
            print(f"    ** dW has direction AND final W partially reflects it **")
        else:
            print(f"    ** Neither dW nor final W shows directional signal **")

    # Q4: Simultaneous / separated_control false positives
    print(f"\n  Q4: Do simultaneous / separated_control show false directional signal?")
    if sim:
        print(f"    simultaneous final_DI:     {sim.get('final_DI', 0):+.6e}")
    if sep:
        print(f"    separated_control final_DI: {sep.get('final_DI', 0):+.6e}")

    # Q5: BTSP recommendation
    print(f"\n  Q5: Recommendation")
    has_within_direction = False
    has_dW_vs_final_mismatch = False
    if ltr and rtl:
        acc_dW_OS = ltr.get("acc_dW_DI", 0) - rtl.get("acc_dW_DI", 0)
        has_within_direction = abs(acc_dW_OS) > 3 * max(abs(off_OS), EPS)
        has_dW_vs_final_mismatch = (abs(acc_dW_OS) > 3 * max(abs(off_OS), EPS) and
                                     abs(final_DIs.get("L_then_R", 0) - final_DIs.get("R_then_L", 0))
                                     < abs(acc_dW_OS) * 0.3)

    if has_dW_vs_final_mismatch:
        print(f"    → Fix homeostasis / final-weight metric. Do NOT pivot to BTSP.")
    elif has_within_direction and ltr and ltr.get("overall_contamination_ratio", 0) > 0.3:
        print(f"    → Fix cross-pair contamination (longer rest). Do NOT pivot to BTSP.")
    elif has_within_direction:
        print(f"    → dW has direction. Investigate why final W doesn't reflect it.")
    else:
        print(f"    → accumulated dW has NO directional signal.")
        print(f"    → Current event-pair outer-product shape may be insufficient.")
        print(f"    → BTSP fallback should be considered if long-rest ablation also fails.")

    wall_s = time.time() - t0
    print(f"\n  Wall time: {wall_s:.1f}s")

    # ── Save CSV ──
    if args.output_csv:
        rows = []
        for arm, result in all_ledgers.items():
            for e in result["ledger"]:
                rows.append({
                    "arm": arm,
                    "config": label,
                    "seed": args.seed, "gap": args.gap, "tau_trace": args.tau,
                    "target_event_update_l1": args.target,
                    "rest_window": rest_window,
                    "homeostasis": not args.no_homeostasis,
                    "event_index": e["event_index"],
                    "pair_index": e["pair_index"],
                    "pulse_step": e["pulse_step"],
                    "pulse_region": e["pulse_region"],
                    "is_within_pair_event": e["is_within_pair_event"],
                    "dt_since_last_pulse": e["dt_since_last_pulse"],
                    "trace_mass_before": e["trace_mass_before"],
                    "trace_L_mass_before": e["trace_L_mass_before"],
                    "trace_R_mass_before": e["trace_R_mass_before"],
                    "current_L_mass": e["current_L_mass"],
                    "current_R_mass": e["current_R_mass"],
                    "raw_update_l1": e["raw_update_l1"],
                    "normalized_update_l1": e["normalized_update_l1"],
                    "dW_L_to_R_l1": e["dW_L_to_R_l1"],
                    "dW_R_to_L_l1": e["dW_R_to_L_l1"],
                    "within_pair_directional": e["within_pair_directional"],
                    "cross_pair_contamination": e["cross_pair_contamination"],
                    "contamination_ratio": e["contamination_ratio"],
                    "current_DI": e["current_DI"],
                    "accumulated_dW_DI": e["accumulated_dW_DI"],
                    "accumulated_dW_LR_total": e["accumulated_dW_LR_total"],
                    "accumulated_dW_RL_total": e["accumulated_dW_RL_total"],
                })
        if rows:
            with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)

    # ── Save JSON ──
    if args.summary_json:
        summary = {
            "experiment": "phase9C1B_directional_ledger",
            "config": label,
            "params": {
                "seed": args.seed, "gap": args.gap, "tau_trace": args.tau,
                "num_pairs": args.num_pairs, "target_event_update_l1": args.target,
                "rest_window": rest_window, "homeostasis": not args.no_homeostasis,
            },
            "off_baseline": {"DI_L_then_R": off_DI, "DI_R_then_L": off_DI_rtl, "OS": off_OS},
            "arms": {},
        }
        for arm, result in all_ledgers.items():
            summary["arms"][arm] = {
                "final_DI": result["final_DI"],
                "acc_dW_LR_total": result["acc_dW_LR_total"],
                "acc_dW_RL_total": result["acc_dW_RL_total"],
                "acc_dW_DI": result["acc_dW_DI"],
                "total_within_pair_dW": result["total_within_pair_dW"],
                "total_cross_pair_dW": result["total_cross_pair_dW"],
                "overall_contamination_ratio": result["overall_contamination_ratio"],
                "n_ledger_entries": result["n_ledger_entries"],
                "ledger": result["ledger"],
            }
        with open(args.summary_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False, default=str)

    print(f"\nDone. CSV: {args.output_csv}  JSON: {args.summary_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
