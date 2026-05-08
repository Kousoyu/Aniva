"""Phase 9D.2A Topology-Bias Diagnostic — diagnose simultaneous slow_DI=+0.164.

Candidates:
  A. Pre-consolidation topology baseline (fast weight L→R / R→L at step 0)
  B. Event-vector support diagnostic (phi coverage/mass asymmetry)
  C. Baseline-corrected slow_DI (corrected = slow_DI - baseline_fast_DI)
  D. Swapped L/R stimulus positions (spatial asymmetry check)
  9D.2A.1. Same-step event ordering diagnostic (combined vs LR vs RL)

Decision rules (pre-registered):
  - If simultaneous_slow_DI and baseline_fast_DI share sign,
    and |corrected_slow_DI| < 0.1 → topology baseline bias.
  - If |corrected_slow_DI| >= 0.1 → baseline cannot explain caveat,
    escalate to D (swapped L/R diagnostic).
  - If D does not flip DI sign, escalate to 9D.2A.1 ordering diagnostic.
  - 9D.2 original threshold is NEVER modified.
  - 9D.2 is NEVER rewritten as clean pass.
"""

import argparse, csv, json, sys, time
import numpy as np

from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.environment.environment import Stimulus, StimulusEvent, Environment

L_STIM = Stimulus(position=(-0.5, 0.0, 0.0), intensity=0.02, radius=0.5)
R_STIM = Stimulus(position=(0.5, 0.0, 0.0), intensity=0.02, radius=0.5)
STIM_MAP = {"L": L_STIM, "R": R_STIM}

PULSE_DURATION = 80
WARMUP = 2000
PAIR_INTERVAL = 1500
TOTAL_STEPS = 7500
N_PAIRS = 3
EPS = 1e-12


def _unit_region(pos):
    x = pos[0]
    if x < -0.1: return "L"
    elif x > 0.1: return "R"
    return "M"


def _make_schedule_simultaneous(warmup, pulse_dur, pair_interval, n_pairs):
    events = []
    for i in range(n_pairs):
        base = warmup + i * pair_interval
        events.append((base, "L", pulse_dur))
        events.append((base, "R", pulse_dur))
    return sorted(events, key=lambda x: x[0])


def _build_env_events(schedule):
    events = []
    for t, side, dur in schedule:
        events.append(StimulusEvent(
            stimulus=STIM_MAP[side], start_step=t, duration_steps=dur))
    return events


def _build_env_events_swappable(schedule, stim_map):
    events = []
    for t, side, dur in schedule:
        events.append(StimulusEvent(
            stimulus=stim_map[side], start_step=t, duration_steps=dur))
    return events


def _event_starts_map(schedule):
    m = {}
    for t, side, _dur in schedule:
        m.setdefault(t, []).append(side)
    return m


def measure_topology_baseline(cfg):
    """A: Measure pre-consolidation fast weight L→R / R→L baseline.

    Returns baseline at step 0 (before any Hebbian plasticity or events).
    """
    core = LifeCore(cfg)
    n_units = cfg.unit_count

    src_regions = np.array([_unit_region(core.units[c.source_id].position)
                            for c in core.connections])
    tgt_regions = np.array([_unit_region(core.units[c.target_id].position)
                            for c in core.connections])
    is_LR = (src_regions == "L") & (tgt_regions == "R")
    is_RL = (src_regions == "R") & (tgt_regions == "L")

    fast = core._weight_cache
    fast_LR_l1 = float(np.sum(np.abs(fast[is_LR])))
    fast_RL_l1 = float(np.sum(np.abs(fast[is_RL])))
    fast_DI = (fast_LR_l1 - fast_RL_l1) / (fast_LR_l1 + fast_RL_l1 + EPS)

    n_LR = int(np.sum(is_LR))
    n_RL = int(np.sum(is_RL))

    return {
        "n_LR_connections": n_LR,
        "n_RL_connections": n_RL,
        "fast_LR_l1": fast_LR_l1,
        "fast_RL_l1": fast_RL_l1,
        "baseline_fast_DI": fast_DI,
        "n_total_connections": len(core.connections),
    }


def measure_event_vector_support(cfg, l_stim=None, r_stim=None):
    """B: Measure L and R phi vector coverage and mass.

    Uses the phi_cache method (same as 9D.2 run_arm).
    """
    if l_stim is None:
        l_stim = L_STIM
    if r_stim is None:
        r_stim = R_STIM
    core = LifeCore(cfg)
    n_units = cfg.unit_count

    phi_L = np.array([l_stim.influence_at(tuple(core._positions[uid]))
                      for uid in range(n_units)], dtype=np.float64)
    phi_R = np.array([r_stim.influence_at(tuple(core._positions[uid]))
                      for uid in range(n_units)], dtype=np.float64)

    support_L = int(np.sum(phi_L > 0))
    support_R = int(np.sum(phi_R > 0))
    mass_L = float(np.sum(np.abs(phi_L)))
    mass_R = float(np.sum(np.abs(phi_R)))

    # Per-hemisphere breakdown
    positions = core._positions
    is_L_hemi = positions[:, 0] < -0.1
    is_R_hemi = positions[:, 0] > 0.1
    n_L_units = int(np.sum(is_L_hemi))
    n_R_units = int(np.sum(is_R_hemi))

    # L stimulus should primarily hit L-hemisphere units (position = -0.5)
    support_L_in_L = int(np.sum((phi_L > 0) & is_L_hemi))
    support_R_in_R = int(np.sum((phi_R > 0) & is_R_hemi))

    return {
        "n_units": n_units,
        "n_L_hemi_units": n_L_units,
        "n_R_hemi_units": n_R_units,
        "event_support_L": support_L,
        "event_support_R": support_R,
        "phi_mass_L": mass_L,
        "phi_mass_R": mass_R,
        "support_ratio": support_L / support_R if support_R > 0 else float("inf"),
        "mass_ratio": mass_L / mass_R if mass_R > 0 else float("inf"),
        "support_L_in_L_hemi": support_L_in_L,
        "support_R_in_R_hemi": support_R_in_R,
    }


def run_simultaneous_arm(cfg, total_steps, l_stim=None, r_stim=None,
                          event_order="combined"):
    """C: Run simultaneous arm and extract slow_DI.

    event_order:
      - "combined": sum L+R phi, apply once (true simultaneous, default)
      - "LR": apply L phi first, then R phi (sequential, L-before-R)
      - "RL": apply R phi first, then L phi (sequential, R-before-L)
    """
    if l_stim is None:
        l_stim = L_STIM
    if r_stim is None:
        r_stim = R_STIM
    core = LifeCore(cfg)
    n_units = cfg.unit_count

    src_regions = np.array([_unit_region(core.units[c.source_id].position)
                            for c in core.connections])
    tgt_regions = np.array([_unit_region(core.units[c.target_id].position)
                            for c in core.connections])
    is_LR = (src_regions == "L") & (tgt_regions == "R")
    is_RL = (src_regions == "R") & (tgt_regions == "L")

    schedule = _make_schedule_simultaneous(
        WARMUP, PULSE_DURATION, PAIR_INTERVAL, N_PAIRS)
    stim_map = {"L": l_stim, "R": r_stim}
    env_events = _build_env_events_swappable(schedule, stim_map)
    env = Environment()
    for ev in env_events:
        env.add_event(ev)

    event_starts = _event_starts_map(schedule)

    phi_cache = {
        "L": np.array([l_stim.influence_at(tuple(core._positions[uid]))
                        for uid in range(n_units)], dtype=np.float64),
        "R": np.array([r_stim.influence_at(tuple(core._positions[uid]))
                        for uid in range(n_units)], dtype=np.float64),
    }

    nan_hit = False
    n_updates = 0

    for s in range(total_steps):
        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)

        if not nan_hit:
            if (np.any(np.isnan(core._tag_cache))
                or np.any(np.isnan(core._slow_weight_cache))
                or np.any(np.isnan(core._weight_cache))):
                nan_hit = True

        if s in event_starts:
            sides = event_starts[s]  # always ["L", "R"] from sorted schedule
            if event_order == "combined":
                phi = np.zeros(n_units, dtype=np.float64)
                for side in sides:
                    phi += phi_cache[side]
                result = core.apply_event_pair_phi(phi)
                if result is not None:
                    n_updates += 1
            elif event_order == "LR":
                # L first, then R
                for side in sides:
                    result = core.apply_event_pair_phi(phi_cache[side])
                    if result is not None:
                        n_updates += 1
            elif event_order == "RL":
                # R first, then L
                for side in reversed(sides):
                    result = core.apply_event_pair_phi(phi_cache[side])
                    if result is not None:
                        n_updates += 1

    slow = core._slow_weight_cache
    slow_LR_l1 = float(np.sum(np.abs(slow[is_LR])))
    slow_RL_l1 = float(np.sum(np.abs(slow[is_RL])))
    slow_DI = (slow_LR_l1 - slow_RL_l1) / (slow_LR_l1 + slow_RL_l1 + EPS)
    slow_l1_total = float(np.sum(np.abs(slow)))
    tag_mass = float(np.sum(np.abs(core._tag_cache)))
    n_captures = len(core._consolidation_ledger)

    return {
        "slow_LR_l1": slow_LR_l1,
        "slow_RL_l1": slow_RL_l1,
        "simultaneous_slow_DI": slow_DI,
        "slow_l1_total": slow_l1_total,
        "tag_mass": tag_mass,
        "n_updates": n_updates,
        "n_captures": n_captures,
        "nan_hit": nan_hit,
    }


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Phase 9D.2A Topology-Bias Diagnostic")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--unit-count", type=int, default=300)
    p.add_argument("--dry-run", action="store_true",
                   help="Print diagnostic measurements without full sim run.")
    p.add_argument("--output-csv", type=str,
                   default="results/phase9D2A_topology_bias_diagnostic.csv")
    p.add_argument("--summary-json", type=str,
                   default="results/phase9D2A_topology_bias_diagnostic_summary.json")
    p.add_argument("--swap-lr", action="store_true",
                   help="Run candidate D: swapped L/R stimulus positions diagnostic. "
                        "Compares original vs swapped simultaneous slow_DI.")
    p.add_argument("--diagnose-ordering", action="store_true",
                   help="Run 9D.2A.1 same-step event ordering diagnostic. "
                        "Compares combined vs LR-order vs RL-order.")
    args = p.parse_args(argv)

    base_cfg = AnivaConfig(
        unit_count=args.unit_count, seed=args.seed,
        consolidation_enabled=True,
        consolidation_ledger_enabled=True,
        event_pair_plasticity_enabled=True,
        event_pair_trace_tau=1000.0,
        event_pair_ledger_enabled=True,
    )

    print(f"Phase 9D.2A Topology-Bias Diagnostic")
    print(f"  seed={args.seed}  unit_count={args.unit_count}")
    print()

    # A: Topology baseline
    print(f"  [A] Measuring pre-consolidation topology baseline ...")
    base = measure_topology_baseline(base_cfg)
    print(f"    L→R connections: {base['n_LR_connections']}")
    print(f"    R→L connections: {base['n_RL_connections']}")
    print(f"    fast_LR_l1: {base['fast_LR_l1']:.4f}")
    print(f"    fast_RL_l1: {base['fast_RL_l1']:.4f}")
    print(f"    baseline_fast_DI: {base['baseline_fast_DI']:+.4f}")
    print()

    # B: Event-vector support
    print(f"  [B] Measuring event-vector support ...")
    ev = measure_event_vector_support(base_cfg)
    print(f"    units: {ev['n_units']} (L hemi: {ev['n_L_hemi_units']}, R hemi: {ev['n_R_hemi_units']})")
    print(f"    event_support: L={ev['event_support_L']}  R={ev['event_support_R']}")
    print(f"    phi_mass: L={ev['phi_mass_L']:.4f}  R={ev['phi_mass_R']:.4f}")
    print(f"    support_ratio (L/R): {ev['support_ratio']:.3f}")
    print(f"    mass_ratio (L/R): {ev['mass_ratio']:.3f}")
    print(f"    support_L in L-hemi: {ev['support_L_in_L_hemi']}")
    print(f"    support_R in R-hemi: {ev['support_R_in_R_hemi']}")
    print()

    if args.dry_run:
        print(f"  [DRY-RUN] Skipping simultaneous arm run.")
        print(f"  A: baseline_fast_DI = {base['baseline_fast_DI']:+.4f}")
        print(f"  B: phi_mass ratio L/R = {ev['mass_ratio']:.3f}")
        print(f"  To complete diagnostic, run without --dry-run.")
        return 0

    # C: Run simultaneous arm
    print(f"  [C] Running simultaneous arm ({TOTAL_STEPS} steps) ...", end=" ", flush=True)
    t0 = time.time()
    sim_cfg = AnivaConfig(**{k: v for k, v in base_cfg.__dict__.items()
                              if not k.startswith("_")})
    sim_cfg.seed = args.seed
    sim = run_simultaneous_arm(sim_cfg, TOTAL_STEPS)
    wall_s = time.time() - t0
    print(f"{wall_s:.0f}s")
    print(f"    slow_LR_l1: {sim['slow_LR_l1']:.6e}")
    print(f"    slow_RL_l1: {sim['slow_RL_l1']:.6e}")
    print(f"    simultaneous_slow_DI: {sim['simultaneous_slow_DI']:+.4f}")
    print(f"    slow_l1_total: {sim['slow_l1_total']:.6e}")
    print(f"    updates={sim['n_updates']}  captures={sim['n_captures']}  nan={sim['nan_hit']}")
    print()

    # Baseline-corrected DI
    corrected_DI = sim["simultaneous_slow_DI"] - base["baseline_fast_DI"]
    sign_agree = (sim["simultaneous_slow_DI"] > 0) == (base["baseline_fast_DI"] > 0)

    print(f"  === Baseline-Corrected DI ===")
    print(f"  simultaneous_slow_DI: {sim['simultaneous_slow_DI']:+.4f}")
    print(f"  baseline_fast_DI:     {base['baseline_fast_DI']:+.4f}")
    print(f"  corrected_DI:         {corrected_DI:+.4f}")
    print(f"  sign agreement:       {sign_agree}")
    print(f"  |corrected_DI| < 0.1: {abs(corrected_DI) < 0.1}")
    print()

    # Decision
    if sign_agree and abs(corrected_DI) < 0.1:
        verdict = ("topology_baseline_bias: simultaneous slow_DI is consistent "
                   "with pre-existing network asymmetry. Corrected DI near zero.")
    elif sign_agree:
        verdict = ("baseline_partial: topology bias explains sign but not full "
                   "magnitude. |corrected_DI| >= 0.1. Consider D: swapped L/R.")
        if abs(corrected_DI) < 0.12:
            verdict += " (borderline)"
    else:
        verdict = ("not_explained_by_topology: baseline and slow_DI have "
                   "different signs. Consider D: swapped L/R diagnostic.")

    print(f"  VERDICT: {verdict}")
    print()

    # Summary row
    row = {
        "seed": args.seed,
        "unit_count": args.unit_count,
        "n_LR_connections": base["n_LR_connections"],
        "n_RL_connections": base["n_RL_connections"],
        "fast_LR_l1": base["fast_LR_l1"],
        "fast_RL_l1": base["fast_RL_l1"],
        "baseline_fast_DI": base["baseline_fast_DI"],
        "event_support_L": ev["event_support_L"],
        "event_support_R": ev["event_support_R"],
        "phi_mass_L": ev["phi_mass_L"],
        "phi_mass_R": ev["phi_mass_R"],
        "simultaneous_slow_DI": sim["simultaneous_slow_DI"],
        "corrected_slow_DI": corrected_DI,
        "sign_agreement": sign_agree,
        "verdict": verdict,
        "wall_time_s": wall_s,
        "nan_hit": sim["nan_hit"],
    }

    # CSV
    if args.output_csv:
        with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(row.keys()))
            w.writeheader()
            w.writerows([row])
        print(f"  CSV: {args.output_csv}")

    # JSON
    if args.summary_json:
        summary = {
            "experiment": "phase9D2A_topology_bias_diagnostic",
            "params": {
                "seed": args.seed,
                "unit_count": args.unit_count,
                "total_steps": TOTAL_STEPS,
                "n_pairs": N_PAIRS,
            },
            "topology_baseline": base,
            "event_vector_support": ev,
            "simultaneous_arm": sim,
            "corrected_DI": corrected_DI,
            "sign_agreement": sign_agree,
            "verdict": verdict,
            "wall_time_s": wall_s,
        }
        with open(args.summary_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
        print(f"  JSON: {args.summary_json}")

    # ── Candidate D: Swapped L/R Diagnostic ──
    if args.swap_lr:
        print()
        print("=" * 60)
        print("  [D] Swapped L/R Diagnostic")
        print("=" * 60)
        print()

        L_SWAP = Stimulus(position=(0.5, 0.0, 0.0), intensity=0.02, radius=0.5)
        R_SWAP = Stimulus(position=(-0.5, 0.0, 0.0), intensity=0.02, radius=0.5)

        # B-swapped
        print("  [D-B] Measuring event-vector support (swapped) ...")
        ev_sw = measure_event_vector_support(base_cfg,
                                             l_stim=L_SWAP, r_stim=R_SWAP)
        print(f"    units: {ev_sw['n_units']} (L hemi: {ev_sw['n_L_hemi_units']}, R hemi: {ev_sw['n_R_hemi_units']})")
        print(f"    event_support: L={ev_sw['event_support_L']}  R={ev_sw['event_support_R']}")
        print(f"    phi_mass: L={ev_sw['phi_mass_L']:.4f}  R={ev_sw['phi_mass_R']:.4f}")
        print(f"    mass_ratio (L/R): {ev_sw['mass_ratio']:.3f}")
        print(f"    support_L in L-hemi: {ev_sw['support_L_in_L_hemi']}")
        print(f"    support_R in R-hemi: {ev_sw['support_R_in_R_hemi']}")
        print()

        # C-swapped
        print(f"  [D-C] Running simultaneous arm SWAPPED ({TOTAL_STEPS} steps) ...",
              end=" ", flush=True)
        t0_sw = time.time()
        sw_cfg = AnivaConfig(**{k: v for k, v in base_cfg.__dict__.items()
                                 if not k.startswith("_")})
        sw_cfg.seed = args.seed
        sim_sw = run_simultaneous_arm(sw_cfg, TOTAL_STEPS,
                                       l_stim=L_SWAP, r_stim=R_SWAP)
        wall_sw = time.time() - t0_sw
        print(f"{wall_sw:.0f}s")
        print(f"    slow_LR_l1: {sim_sw['slow_LR_l1']:.6e}")
        print(f"    slow_RL_l1: {sim_sw['slow_RL_l1']:.6e}")
        print(f"    swapped_slow_DI: {sim_sw['simultaneous_slow_DI']:+.4f}")
        print(f"    slow_l1_total: {sim_sw['slow_l1_total']:.6e}")
        print(f"    updates={sim_sw['n_updates']}  captures={sim_sw['n_captures']}  nan={sim_sw['nan_hit']}")
        print()

        # Corrected DI for swapped
        corr_sw = sim_sw["simultaneous_slow_DI"] - base["baseline_fast_DI"]
        print(f"  === Swapped Corrected DI ===")
        print(f"  swapped_slow_DI:   {sim_sw['simultaneous_slow_DI']:+.4f}")
        print(f"  baseline_fast_DI:  {base['baseline_fast_DI']:+.4f}")
        print(f"  corrected_DI_swap: {corr_sw:+.4f}")
        print()

        # Comparison
        orig_di = sim["simultaneous_slow_DI"]
        sw_di = sim_sw["simultaneous_slow_DI"]
        di_shift = sw_di - orig_di
        sign_flipped = (orig_di > 0) != (sw_di > 0)
        substantial = abs(di_shift) > 0.05

        print("  +----------------------------------------------------------+")
        print("  |  Original  vs  Swapped L/R  Comparison                 |")
        print("  +----------------------------------------------------------+")
        print(f"  |  original simultaneous_slow_DI:  {orig_di:+.4f}                 |")
        print(f"  |  swapped  simultaneous_slow_DI:  {sw_di:+.4f}                 |")
        print(f"  |  DI shift (swapped - original):  {di_shift:+.4f}                 |")
        print(f"  |  sign flipped:                   {str(sign_flipped):5}                 |")
        print(f"  |  |shift| > 0.05:                 {str(substantial):5}                 |")
        print("  +----------------------------------------------------------+")
        print(f"  |  original phi_mass:  L={ev['phi_mass_L']:.4f}  R={ev['phi_mass_R']:.4f}         |")
        print(f"  |  swapped  phi_mass:  L={ev_sw['phi_mass_L']:.4f}  R={ev_sw['phi_mass_R']:.4f}         |")
        print(f"  |  original phi_mass_ratio L/R:  {ev['mass_ratio']:.3f}                |")
        print(f"  |  swapped  phi_mass_ratio L/R:  {ev_sw['mass_ratio']:.3f}                |")
        print("  +----------------------------------------------------------+")
        print(f"  |  baseline_fast_DI (same):  {base['baseline_fast_DI']:+.4f}                 |")
        print("  +----------------------------------------------------------+")
        print()

        # D verdict
        if sign_flipped:
            d_verdict = (
                "spatial_event_vector_asymmetry: slow_DI flipped sign under "
                "swapped L/R positions. The simultaneous caveat is explained by "
                "stimulus placement / phi coverage asymmetry, not by a "
                "consolidation-level false positive."
            )
        elif substantial:
            d_verdict = (
                "substantial_shift_without_flip: slow_DI shifted by "
                f"{di_shift:+.4f} under swapped positions but did not flip sign. "
                "Partial spatial asymmetry contribution. Consider shuffled/matched "
                "topology control (candidate E)."
            )
        else:
            d_verdict = (
                "possible_consolidation_false_positive: slow_DI did not flip "
                "sign and |shift| <= 0.05 under swapped L/R. The simultaneous "
                "bias is robust to stimulus placement. Escalate to shuffled/"
                "matched topology mask (candidate E)."
            )

        print(f"  D VERDICT: {d_verdict}")
        print()

        # Extend CSV row with swapped fields
        row.update({
            "swapped_slow_DI": sw_di,
            "swapped_corrected_DI": corr_sw,
            "DI_shift": di_shift,
            "sign_flipped": sign_flipped,
            "substantial_shift": substantial,
            "swapped_phi_mass_L": ev_sw["phi_mass_L"],
            "swapped_phi_mass_R": ev_sw["phi_mass_R"],
            "swapped_phi_mass_ratio": ev_sw["mass_ratio"],
            "swapped_wall_time_s": wall_sw,
            "D_verdict": d_verdict,
        })

        # Re-write CSV with extended columns
        if args.output_csv:
            with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(row.keys()))
                w.writeheader()
                w.writerows([row])
            print(f"  CSV (extended with D): {args.output_csv}")

        # Extend JSON
        if args.summary_json:
            summary.update({
                "swapped_event_vector_support": ev_sw,
                "swapped_simultaneous_arm": sim_sw,
                "swapped_corrected_DI": corr_sw,
                "comparison": {
                    "original_slow_DI": orig_di,
                    "swapped_slow_DI": sw_di,
                    "DI_shift": di_shift,
                    "sign_flipped": sign_flipped,
                    "substantial_shift": substantial,
                    "original_phi_mass_ratio": ev["mass_ratio"],
                    "swapped_phi_mass_ratio": ev_sw["mass_ratio"],
                },
                "D_verdict": d_verdict,
            })
            with open(args.summary_json, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
            print(f"  JSON (extended with D): {args.summary_json}")

    # ── 9D.2A.1 Same-Step Event Ordering Diagnostic ──
    if args.diagnose_ordering:
        print()
        print("=" * 60)
        print("  9D.2A.1 Same-Step Event Ordering Diagnostic")
        print("=" * 60)
        print()
        print("  Comparing three simultaneous phi-application modes:")
        print("    combined  — sum L+R phi, apply_event_pair_phi() once")
        print("    LR order  — apply L phi, then R phi (sequential)")
        print("    RL order  — apply R phi, then L phi (sequential)")
        print()

        ordering_results = {}
        ordering_results["combined"] = sim  # already measured in C
        print("  [combined] reusing original C run ...")
        print()

        for mode in ["LR", "RL"]:

            print(f"  [{mode}] Running simultaneous arm ({TOTAL_STEPS} steps) ...",
                  end=" ", flush=True)
            t0_mode = time.time()
            mode_cfg = AnivaConfig(**{k: v for k, v in base_cfg.__dict__.items()
                                       if not k.startswith("_")})
            mode_cfg.seed = args.seed
            res = run_simultaneous_arm(mode_cfg, TOTAL_STEPS,
                                        l_stim=L_STIM, r_stim=R_STIM,
                                        event_order=mode)
            wall_mode = time.time() - t0_mode
            print(f"{wall_mode:.0f}s")
            print(f"    slow_LR_l1: {res['slow_LR_l1']:.6e}")
            print(f"    slow_RL_l1: {res['slow_RL_l1']:.6e}")
            print(f"    slow_DI:    {res['simultaneous_slow_DI']:+.4f}")
            print(f"    slow_l1_total: {res['slow_l1_total']:.6e}")
            print(f"    updates={res['n_updates']}  captures={res['n_captures']}"
                  f"  tag_mass={res['tag_mass']:.4e}  nan={res['nan_hit']}")
            print()
            ordering_results[mode] = res
            ordering_results[mode + "_wall_time_s"] = wall_mode

        # Comparison
        di_combined = ordering_results["combined"]["simultaneous_slow_DI"]
        di_lr = ordering_results["LR"]["simultaneous_slow_DI"]
        di_rl = ordering_results["RL"]["simultaneous_slow_DI"]

        lr_shift = di_lr - di_combined
        rl_shift = di_rl - di_combined
        lr_rl_gap = di_lr - di_rl

        print("  Ordering Comparison:")
        print(f"    combined slow_DI:  {di_combined:+.4f}")
        print(f"    LR-order slow_DI:  {di_lr:+.4f}  (shift from combined: {lr_shift:+.4f})")
        print(f"    RL-order slow_DI:  {di_rl:+.4f}  (shift from combined: {rl_shift:+.4f})")
        print(f"    LR-RL gap:         {lr_rl_gap:+.4f}")
        print()

        # Detailed slow_LR/RL comparison
        print("  Per-direction L1 breakdown:")
        for mode in ["combined", "LR", "RL"]:
            r = ordering_results[mode]
            print(f"    {mode:10s}  slow_LR={r['slow_LR_l1']:.6e}  "
                  f"slow_RL={r['slow_RL_l1']:.6e}  "
                  f"tag={r['tag_mass']:.4e}  "
                  f"captures={r['n_captures']}  "
                  f"updates={r['n_updates']}")
        print()

        # Verdict
        gap_significant = abs(lr_rl_gap) > 0.03
        lr_rl_opposite = (di_lr > 0) != (di_rl > 0)

        if lr_rl_opposite:
            order_verdict = (
                "ordering_artifact_confirmed: LR and RL order produce opposite "
                "slow_DI signs. The simultaneous caveat is explained by same-step "
                "event processing order (not spatial asymmetry, not topology, "
                "not consolidation false positive). Combined-phi mode represents "
                "the true simultaneous control."
            )
        elif gap_significant:
            order_verdict = (
                "ordering_sensitivity_detected: LR and RL order produce "
                f"substantially different slow_DI (gap={lr_rl_gap:+.4f}). "
                "Same-step processing order contributes to the simultaneous caveat. "
                "Combined-phi is the correct simultaneous control."
            )
        else:
            order_verdict = (
                "ordering_not_primary_driver: LR, RL, and combined modes produce "
                f"similar slow_DI (gap={lr_rl_gap:+.4f}). Same-step processing "
                "order does NOT explain the +0.16 caveat. "
                "Escalate to candidate E (shuffled/matched topology)."
            )

        print(f"  ORDERING VERDICT: {order_verdict}")
        print()

        # Extend CSV row
        row.update({
            "combined_slow_DI": di_combined,
            "LR_order_slow_DI": di_lr,
            "RL_order_slow_DI": di_rl,
            "LR_RL_gap": lr_rl_gap,
            "LR_shift_from_combined": lr_shift,
            "RL_shift_from_combined": rl_shift,
            "ordering_verdict": order_verdict,
        })

        if args.output_csv:
            with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(row.keys()))
                w.writeheader()
                w.writerows([row])
            print(f"  CSV (extended with ordering): {args.output_csv}")

        if args.summary_json:
            summary["ordering_diagnostic"] = {
                "combined": {k: ordering_results["combined"][k] for k in
                    ["simultaneous_slow_DI", "slow_LR_l1", "slow_RL_l1",
                     "slow_l1_total", "tag_mass", "n_updates", "n_captures",
                     "nan_hit"]},
                "LR_order": {k: ordering_results["LR"][k] for k in
                    ["simultaneous_slow_DI", "slow_LR_l1", "slow_RL_l1",
                     "slow_l1_total", "tag_mass", "n_updates", "n_captures",
                     "nan_hit"]},
                "RL_order": {k: ordering_results["RL"][k] for k in
                    ["simultaneous_slow_DI", "slow_LR_l1", "slow_RL_l1",
                     "slow_l1_total", "tag_mass", "n_updates", "n_captures",
                     "nan_hit"]},
                "LR_RL_gap": lr_rl_gap,
                "verdict": order_verdict,
            }
            with open(args.summary_json, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
            print(f"  JSON (extended with ordering): {args.summary_json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
