"""Phase 9D.2B.1 — E3 + E4 Offline Pipeline Decomposition Diagnostic.

Trace simultaneous +0.1635 through the consolidation pipeline layer by layer:
  Layer 1: event-pair dW (Hebbian correlation output)
  Layer 2: tag = |dW| (absolute-value accumulation)
  Layer 3: capture → slow_weight (consolidation write)
  Layer 4: final slow_DI

Decision:
  - dW_DI biased → root in event-pair plasticity
  - dW_DI ~ 0, tag_DI biased → root in |dW| absolute-value operation
  - dW_DI ~ 0, tag_DI ~ 0, slow_DI biased → root in capture/slow_weight write
  - All layers small, slow_DI biased → small-denominator metric sensitivity
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


def _event_starts_map(schedule):
    m = {}
    for t, side, _dur in schedule:
        m.setdefault(t, []).append(side)
    return m


def _l1_on_mask(arr, mask):
    return float(np.sum(np.abs(arr[mask])))


def _nz_count(arr, mask):
    return int(np.sum((arr != 0) & mask))


def run_decomposition(cfg):
    """Run instrumented simultaneous combined-phi arm with per-layer snapshots."""

    core = LifeCore(cfg)
    n_units = cfg.unit_count

    # Connection classification
    src_regions = np.array([_unit_region(core.units[c.source_id].position)
                            for c in core.connections])
    tgt_regions = np.array([_unit_region(core.units[c.target_id].position)
                            for c in core.connections])
    is_LR = (src_regions == "L") & (tgt_regions == "R")
    is_RL = (src_regions == "R") & (tgt_regions == "L")
    is_all = is_LR | is_RL

    n_LR = int(np.sum(is_LR))
    n_RL = int(np.sum(is_RL))

    # Initial structure
    fast_init = core._weight_cache.copy()
    fast_LR_l1 = _l1_on_mask(fast_init, is_LR)
    fast_RL_l1 = _l1_on_mask(fast_init, is_RL)

    # Schedule
    schedule = _make_schedule_simultaneous(WARMUP, PULSE_DURATION, PAIR_INTERVAL, N_PAIRS)
    env_events = []
    for t, side, dur in schedule:
        env_events.append(StimulusEvent(
            stimulus=STIM_MAP[side], start_step=t, duration_steps=dur))
    env = Environment()
    for ev in env_events:
        env.add_event(ev)

    event_starts = _event_starts_map(schedule)
    phi_cache = {
        "L": np.array([L_STIM.influence_at(tuple(core._positions[uid]))
                        for uid in range(n_units)], dtype=np.float64),
        "R": np.array([R_STIM.influence_at(tuple(core._positions[uid]))
                        for uid in range(n_units)], dtype=np.float64),
    }

    # Per-event-pair snapshots
    pair_dW_snapshots = []   # [{dW_LR_l1, dW_RL_l1, dW_DI}, ...]
    pair_tag_snapshots = []  # [{tag_delta_LR_l1, tag_delta_RL_l1, tag_delta_DI}, ...]

    # Pre-capture tag snapshots
    tag_before_captures = []  # [{tag_LR_l1, tag_RL_l1, tag_DI}, ...]

    nan_hit = False
    total_updates = 0
    prev_ledger_len = 0

    for s in range(TOTAL_STEPS):
        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)

        # Check for NaN
        if not nan_hit:
            if (np.any(np.isnan(core._tag_cache))
                or np.any(np.isnan(core._slow_weight_cache))
                or np.any(np.isnan(core._weight_cache))):
                nan_hit = True

        # Check for new captures (fired during this step's _consolidation_step)
        current_ledger_len = len(core._consolidation_ledger)
        if current_ledger_len > prev_ledger_len:
            # Capture just fired — record tag state before next event
            tag_before_captures.append({
                "step": s,
                "capture_idx": current_ledger_len - 1,
                "tag_LR_l1": _l1_on_mask(core._tag_cache, is_LR),
                "tag_RL_l1": _l1_on_mask(core._tag_cache, is_RL),
            })
            prev_ledger_len = current_ledger_len

        if s in event_starts:
            sides = event_starts[s]  # ["L", "R"]

            # Snapshot BEFORE phi application
            w_before = core._weight_cache.copy()
            tag_before = core._tag_cache.copy()
            slow_before = core._slow_weight_cache.copy()

            # Apply combined phi
            phi = np.zeros(n_units, dtype=np.float64)
            for side in sides:
                phi += phi_cache[side]
            result = core.apply_event_pair_phi(phi)
            if result is not None:
                total_updates += 1

            # Snapshot AFTER phi application
            w_after = core._weight_cache
            tag_after = core._tag_cache

            dW = w_after - w_before
            tag_delta = tag_after - tag_before

            dW_LR_l1 = _l1_on_mask(dW, is_LR)
            dW_RL_l1 = _l1_on_mask(dW, is_RL)
            dW_DI = (dW_LR_l1 - dW_RL_l1) / (dW_LR_l1 + dW_RL_l1 + EPS)

            tag_delta_LR_l1 = _l1_on_mask(tag_delta, is_LR)
            tag_delta_RL_l1 = _l1_on_mask(tag_delta, is_RL)
            tag_delta_DI = (tag_delta_LR_l1 - tag_delta_RL_l1) / (tag_delta_LR_l1 + tag_delta_RL_l1 + EPS)

            pair_dW_snapshots.append({
                "pair_idx": len(pair_dW_snapshots),
                "step": s,
                "dW_LR_l1": dW_LR_l1,
                "dW_RL_l1": dW_RL_l1,
                "dW_DI": dW_DI,
                "dW_total_l1": float(np.sum(np.abs(dW))),
            })
            pair_tag_snapshots.append({
                "pair_idx": len(pair_tag_snapshots),
                "step": s,
                "tag_delta_LR_l1": tag_delta_LR_l1,
                "tag_delta_RL_l1": tag_delta_RL_l1,
                "tag_delta_DI": tag_delta_DI,
                "tag_total_l1": float(np.sum(np.abs(tag_after))),
            })

    # Final state
    slow_final = core._slow_weight_cache
    tag_final = core._tag_cache
    w_final = core._weight_cache

    slow_LR_l1 = _l1_on_mask(slow_final, is_LR)
    slow_RL_l1 = _l1_on_mask(slow_final, is_RL)
    slow_DI = (slow_LR_l1 - slow_RL_l1) / (slow_LR_l1 + slow_RL_l1 + EPS)

    tag_LR_l1 = _l1_on_mask(tag_final, is_LR)
    tag_RL_l1 = _l1_on_mask(tag_final, is_RL)
    tag_DI = (tag_LR_l1 - tag_RL_l1) / (tag_LR_l1 + tag_RL_l1 + EPS)

    n_captures = len(core._consolidation_ledger)
    n_tagged_LR = _nz_count(tag_final, is_LR)
    n_tagged_RL = _nz_count(tag_final, is_RL)

    return {
        "structure": {
            "n_LR": n_LR,
            "n_RL": n_RL,
            "n_total_connections": len(core.connections),
            "fast_LR_l1": fast_LR_l1,
            "fast_RL_l1": fast_RL_l1,
            "fast_LR_RL_ratio": fast_LR_l1 / fast_RL_l1 if fast_RL_l1 > 0 else float("inf"),
        },
        "pair_dW": pair_dW_snapshots,
        "pair_tag_delta": pair_tag_snapshots,
        "tag_before_captures": tag_before_captures,
        "final_tag": {
            "tag_LR_l1": tag_LR_l1,
            "tag_RL_l1": tag_RL_l1,
            "tag_DI": tag_DI,
            "tag_total_l1": float(np.sum(np.abs(tag_final))),
            "n_tagged_LR": n_tagged_LR,
            "n_tagged_RL": n_tagged_RL,
        },
        "final_slow": {
            "slow_LR_l1": slow_LR_l1,
            "slow_RL_l1": slow_RL_l1,
            "slow_DI": slow_DI,
            "slow_total_l1": float(np.sum(np.abs(slow_final))),
        },
        "captures": {
            "n_captures": n_captures,
            "ledger": core._consolidation_ledger,
        },
        "flags": {
            "nan_hit": nan_hit,
            "total_event_pair_updates": total_updates,
        },
    }


def _format_di(val):
    return f"{val:+.4f}"


def _format_sci(val):
    return f"{val:.4e}"


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Phase 9D.2B.1 Pipeline Decomposition Diagnostic")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--unit-count", type=int, default=300)
    p.add_argument("--dry-run", action="store_true",
                   help="Print what will be measured without running sim.")
    p.add_argument("--output-csv", type=str,
                   default="results/phase9D2B_decomposition_diagnostic.csv")
    p.add_argument("--summary-json", type=str,
                   default="results/phase9D2B_decomposition_diagnostic_summary.json")
    args = p.parse_args(argv)

    base_cfg = AnivaConfig(
        unit_count=args.unit_count, seed=args.seed,
        consolidation_enabled=True,
        consolidation_ledger_enabled=True,
        event_pair_plasticity_enabled=True,
        event_pair_trace_tau=1000.0,
        event_pair_ledger_enabled=False,
    )

    print(f"Phase 9D.2B.1 Pipeline Decomposition Diagnostic")
    print(f"  seed={args.seed}  unit_count={args.unit_count}")
    print()

    if args.dry_run:
        print("  [DRY-RUN] Would instrument simultaneous combined-phi arm:")
        print("    Per event pair: snapshot w_before → dW → tag_before → tag_delta")
        print("    Per step: watch consolidation_ledger for new captures")
        print("    Final: slow_LR/RL_l1, tag_LR/RL_l1")
        print()
        print("  Output layers:")
        print("    Layer 1: dW_DI per pair  (event-pair Hebbian correlation)")
        print("    Layer 2: tag_delta_DI per pair  (|dW| accumulation)")
        print("    Layer 3: capture events  (tag → slow_weight transfer)")
        print("    Layer 4: final slow_DI")
        print()
        print("  Expected runtime: ~95s (single 7500-step simultaneous arm)")
        return 0

    # Run
    print(f"  Running instrumented simultaneous combined-phi arm "
          f"({TOTAL_STEPS} steps) ...", end=" ", flush=True)
    t0 = time.time()
    sim_cfg = AnivaConfig(**{k: v for k, v in base_cfg.__dict__.items()
                              if not k.startswith("_")})
    sim_cfg.seed = args.seed
    result = run_decomposition(sim_cfg)
    wall_s = time.time() - t0
    print(f"{wall_s:.0f}s")
    print()

    # ── Structure ──
    st = result["structure"]
    print("  === Layer 0: Connection Structure ===")
    print(f"    n_LR: {st['n_LR']}   n_RL: {st['n_RL']}")
    print(f"    fast_LR_l1: {st['fast_LR_l1']:.4f}")
    print(f"    fast_RL_l1: {st['fast_RL_l1']:.4f}")
    print(f"    fast_LR/RL ratio: {st['fast_LR_RL_ratio']:.4f}")
    print()

    # ── Layer 1: dW ──
    print("  === Layer 1: Event-Pair dW (Hebbian correlation) ===")
    for snap in result["pair_dW"]:
        print(f"    Pair {snap['pair_idx']} (step {snap['step']}):"
              f"  dW_LR={_format_sci(snap['dW_LR_l1'])}"
              f"  dW_RL={_format_sci(snap['dW_RL_l1'])}"
              f"  dW_DI={_format_di(snap['dW_DI'])}"
              f"  dW_total={_format_sci(snap['dW_total_l1'])}")
    if result["pair_dW"]:
        last_dw = result["pair_dW"][-1]
    else:
        last_dw = {"dW_DI": 0.0}
    print()

    # ── Layer 2: tag delta ──
    print("  === Layer 2: Tag Delta (|dW|) ===")
    for snap in result["pair_tag_delta"]:
        print(f"    Pair {snap['pair_idx']} (step {snap['step']}):"
              f"  tag_dL={_format_sci(snap['tag_delta_LR_l1'])}"
              f"  tag_dR={_format_sci(snap['tag_delta_RL_l1'])}"
              f"  tag_delta_DI={_format_di(snap['tag_delta_DI'])}")
    if result["pair_tag_delta"]:
        last_tag = result["pair_tag_delta"][-1]
    else:
        last_tag = {"tag_delta_DI": 0.0}
    print()

    # ── Layer 2.5: pre-capture tag ──
    print("  === Layer 2.5: Tag Before Captures ===")
    for tc in result["tag_before_captures"]:
        tag_bc_DI = ((tc["tag_LR_l1"] - tc["tag_RL_l1"])
                     / (tc["tag_LR_l1"] + tc["tag_RL_l1"] + EPS))
        print(f"    step {tc['step']} (capture #{tc['capture_idx']}):"
              f"  tag_LR={_format_sci(tc['tag_LR_l1'])}"
              f"  tag_RL={_format_sci(tc['tag_RL_l1'])}"
              f"  tag_DI={_format_di(tag_bc_DI)}")
    if not result["tag_before_captures"]:
        print("    (no captures recorded)")
    print()

    # ── Layer 3: captures ──
    cap = result["captures"]
    print(f"  === Layer 3: Captures ({cap['n_captures']} total) ===")
    for i, entry in enumerate(cap["ledger"][:5]):
        print(f"    Capture {i}: signal={entry['capture_signal']:.4f}"
              f"  tag_mass={_format_sci(entry['tag_mass'])}"
              f"  slow_delta_l1={_format_sci(entry['slow_weight_delta_l1'])}"
              f"  n_tagged={entry['n_tagged_connections']}"
              f"  energy={entry['mean_energy']:.4f}"
              f"  trace={_format_sci(entry['trace_mass_at_capture'])}")
    if cap["n_captures"] > 5:
        print(f"    ... ({cap['n_captures'] - 5} more)")
        last_cap = cap["ledger"][-1]
        print(f"    Capture {cap['n_captures'] - 1}: signal={last_cap['capture_signal']:.4f}"
              f"  tag_mass={_format_sci(last_cap['tag_mass'])}"
              f"  slow_delta_l1={_format_sci(last_cap['slow_weight_delta_l1'])}")
    print()

    # ── Layer 2 Final: accumulated tag ──
    ft = result["final_tag"]
    print("  === Layer 2 Final: Accumulated Tag ===")
    print(f"    tag_LR_l1: {_format_sci(ft['tag_LR_l1'])}")
    print(f"    tag_RL_l1: {_format_sci(ft['tag_RL_l1'])}")
    print(f"    tag_DI:    {_format_di(ft['tag_DI'])}")
    print(f"    tag_total: {_format_sci(ft['tag_total_l1'])}")
    print(f"    n_tagged_LR: {ft['n_tagged_LR']}   n_tagged_RL: {ft['n_tagged_RL']}")
    print()

    # ── Layer 4: final slow ──
    fs = result["final_slow"]
    print("  === Layer 4: Final Slow Weight ===")
    print(f"    slow_LR_l1: {_format_sci(fs['slow_LR_l1'])}")
    print(f"    slow_RL_l1: {_format_sci(fs['slow_RL_l1'])}")
    print(f"    slow_DI:    {_format_di(fs['slow_DI'])}")
    print(f"    slow_total: {_format_sci(fs['slow_total_l1'])}")
    print()

    # ── Pipeline Summary ──
    dW_DI_last = last_dw["dW_DI"]
    tag_delta_DI_last = last_tag["tag_delta_DI"]
    tag_DI_final = ft["tag_DI"]
    slow_DI_final = fs["slow_DI"]

    print("  +--------------------------------------------------+")
    print("  |  Pipeline Layer Summary                          |")
    print("  +--------------------------------------------------+")
    print(f"  |  Layer 1  dW_DI (last pair):     {_format_di(dW_DI_last):>10}       |")
    print(f"  |  Layer 2  tag_delta_DI (last):    {_format_di(tag_delta_DI_last):>10}       |")
    print(f"  |  Layer 2  tag_DI (accumulated):   {_format_di(tag_DI_final):>10}       |")
    print(f"  |  Layer 4  slow_DI (final):        {_format_di(slow_DI_final):>10}       |")
    print("  +--------------------------------------------------+")
    print()

    # Verdict
    dW_bias = abs(dW_DI_last) > 0.02
    tag_bias = abs(tag_DI_final) > 0.02

    if dW_bias:
        verdict = (
            f"dW_level_bias: dW_DI={dW_DI_last:+.4f}. "
            "Bias originates in event-pair plasticity (trace·phi correlation). "
            "The |dW| operation then adds tag accumulation effect. "
            "Investigate event_pair_update directionality on L→R vs R→L connections."
        )
    elif tag_bias and abs(dW_DI_last) < 0.02:
        verdict = (
            f"tag_level_bias: dW_DI={dW_DI_last:+.4f} (near zero) but "
            f"tag_DI={tag_DI_final:+.4f}. "
            "Bias introduced by |dW| absolute-value operation — dW distribution "
            "has a skew/heavy-tail on one side that |dW| amplifies. "
            "Investigate dW distribution shape per connection group."
        )
    elif abs(tag_DI_final) < 0.02 and abs(slow_DI_final) > 0.02:
        verdict = (
            f"capture_level_bias: dW and tag are nearly symmetric "
            f"(dW_DI={dW_DI_last:+.4f}, tag_DI={tag_DI_final:+.4f}) "
            f"but slow_DI={slow_DI_final:+.4f}. "
            "Bias introduced during capture/slow_weight write. "
            "Check capture_signal distribution across L-hemi vs R-hemi source units."
        )
    elif abs(slow_DI_final) < 0.05:
        verdict = (
            f"near_zero_all_layers: slow_DI={slow_DI_final:+.4f}. "
            "All layers show near-zero DI. Original +0.16 caveat not reproduced "
            "in this seed/run — may be seed-dependent."
        )
    else:
        verdict = (
            f"diffuse_bias: dW_DI={dW_DI_last:+.4f}, tag_DI={tag_DI_final:+.4f}, "
            f"slow_DI={slow_DI_final:+.4f}. "
            "Bias accumulates diffusely across layers. No single layer dominates. "
            "Consider matched-mask normalization (E1/E2) or shuffled null (E5)."
        )

    print(f"  VERDICT: {verdict}")
    print()

    flags = result["flags"]
    print(f"  nan={flags['nan_hit']}  event_pair_updates={flags['total_event_pair_updates']}")
    print()

    # CSV
    row = {
        "seed": args.seed,
        "unit_count": args.unit_count,
        "n_LR": st["n_LR"],
        "n_RL": st["n_RL"],
        "fast_LR_l1": st["fast_LR_l1"],
        "fast_RL_l1": st["fast_RL_l1"],
        "dW_DI_last": dW_DI_last,
        "tag_delta_DI_last": tag_delta_DI_last,
        "tag_DI_final": tag_DI_final,
        "slow_DI_final": slow_DI_final,
        "n_captures": cap["n_captures"],
        "n_tagged_LR": ft["n_tagged_LR"],
        "n_tagged_RL": ft["n_tagged_RL"],
        "verdict": verdict,
        "wall_time_s": wall_s,
        "nan_hit": flags["nan_hit"],
    }
    if result["pair_dW"]:
        row["dW_DI_pair0"] = result["pair_dW"][0]["dW_DI"]
    if len(result["pair_dW"]) > 1:
        row["dW_DI_pair1"] = result["pair_dW"][1]["dW_DI"]
    if len(result["pair_dW"]) > 2:
        row["dW_DI_pair2"] = result["pair_dW"][2]["dW_DI"]
    if result["pair_tag_delta"]:
        row["tag_delta_DI_pair0"] = result["pair_tag_delta"][0]["tag_delta_DI"]
    if len(result["pair_tag_delta"]) > 1:
        row["tag_delta_DI_pair1"] = result["pair_tag_delta"][1]["tag_delta_DI"]
    if len(result["pair_tag_delta"]) > 2:
        row["tag_delta_DI_pair2"] = result["pair_tag_delta"][2]["tag_delta_DI"]

    if args.output_csv:
        with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(row.keys()))
            w.writeheader()
            w.writerows([row])
        print(f"  CSV: {args.output_csv}")

    if args.summary_json:
        with open(args.summary_json, "w", encoding="utf-8") as f:
            json.dump({
                "experiment": "phase9D2B_decomposition_diagnostic",
                "params": {"seed": args.seed, "unit_count": args.unit_count,
                           "total_steps": TOTAL_STEPS, "n_pairs": N_PAIRS},
                "structure": st,
                "pair_dW": result["pair_dW"],
                "pair_tag_delta": result["pair_tag_delta"],
                "tag_before_captures": result["tag_before_captures"],
                "final_tag": ft,
                "final_slow": fs,
                "captures": {"n_captures": cap["n_captures"]},
                "verdict": verdict,
                "wall_time_s": wall_s,
            }, f, indent=2, ensure_ascii=False, default=str)
        print(f"  JSON: {args.summary_json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
