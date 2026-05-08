"""Phase 9D.2C — Event-Pair Projection Diagnostic.

Inspect raw eligibility = trace[source] * phi[target] on LR/RL connection masks.
Verify whether raw_DI == dW_DI (L1 normalization invariant) and whether the bias
exists at the raw projection level.

Offline diagnostic only. No mechanism changes, no parameter tuning.
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


def _l1(arr):
    return float(np.sum(np.abs(arr)))


def _l1_mask(arr, mask):
    return float(np.sum(np.abs(arr[mask])))


def _mean_mask(arr, mask):
    n = int(np.sum(mask))
    return _l1_mask(arr, mask) / n if n > 0 else 0.0


def build_matched_mask(is_LR, is_RL, initial_weights):
    """Greedy nearest-neighbor matching on |initial_weight|.

    Returns (matched_LR_mask, matched_RL_mask, n_matched).
    Only the matched subset of each group is True in the returned masks.
    """
    lr_indices = np.where(is_LR)[0]
    rl_indices = np.where(is_RL)[0]
    n_min = min(len(lr_indices), len(rl_indices))
    if n_min == 0:
        return np.zeros_like(is_LR), np.zeros_like(is_RL), 0

    lr_weights = np.abs(initial_weights[lr_indices])
    rl_weights = np.abs(initial_weights[rl_indices])

    # Sort by weight magnitude
    lr_order = np.argsort(lr_weights)
    rl_order = np.argsort(rl_weights)

    # Greedy: pair sorted lists, pick closest weight from RL for each LR
    matched_lr = np.zeros(len(lr_indices), dtype=bool)
    matched_rl = np.zeros(len(rl_indices), dtype=bool)
    rl_avail = set(range(len(rl_indices)))

    for lr_pos in lr_order:
        w_lr = lr_weights[lr_pos]
        best_rl = None
        best_diff = float("inf")
        for rl_pos in list(rl_avail):
            diff = abs(w_lr - rl_weights[rl_pos])
            if diff < best_diff:
                best_diff = diff
                best_rl = rl_pos
        if best_rl is not None:
            matched_lr[lr_pos] = True
            matched_rl[best_rl] = True
            rl_avail.discard(best_rl)

    n_matched = min(int(np.sum(matched_lr)), int(np.sum(matched_rl)))

    matched_LR_mask = np.zeros_like(is_LR)
    matched_RL_mask = np.zeros_like(is_RL)
    matched_LR_mask[lr_indices[matched_lr]] = True
    matched_RL_mask[rl_indices[matched_rl]] = True

    return matched_LR_mask, matched_RL_mask, n_matched


def run_projection_diagnostic(cfg):
    """Run simultaneous combined-phi arm, extract raw eligibility at each event pair."""

    core = LifeCore(cfg)
    n_units = cfg.unit_count
    src_idx = core._source_indices
    tgt_idx = core._target_indices
    positions = core._positions
    init_weights = core._weight_cache.copy()

    # Connection classification
    src_regions = np.array([_unit_region(core.units[c.source_id].position)
                            for c in core.connections])
    tgt_regions = np.array([_unit_region(core.units[c.target_id].position)
                            for c in core.connections])
    is_LR = (src_regions == "L") & (tgt_regions == "R")
    is_RL = (src_regions == "R") & (tgt_regions == "L")
    n_LR = int(np.sum(is_LR))
    n_RL = int(np.sum(is_RL))

    fast_LR_l1 = _l1_mask(init_weights, is_LR)
    fast_RL_l1 = _l1_mask(init_weights, is_RL)

    # Matched mask (offline only)
    matched_LR_mask, matched_RL_mask, n_matched = build_matched_mask(
        is_LR, is_RL, init_weights)

    # Unit hemisphere masks
    is_L_unit = positions[:, 0] < -0.1
    is_R_unit = positions[:, 0] > 0.1

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
        "L": np.array([L_STIM.influence_at(tuple(positions[uid]))
                        for uid in range(n_units)], dtype=np.float64),
        "R": np.array([R_STIM.influence_at(tuple(positions[uid]))
                        for uid in range(n_units)], dtype=np.float64),
    }

    # Per-event-pair projection snapshots
    pair_snapshots = []
    nan_hit = False

    for s in range(TOTAL_STEPS):
        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)

        if not nan_hit:
            if (np.any(np.isnan(core._tag_cache))
                or np.any(np.isnan(core._slow_weight_cache))
                or np.any(np.isnan(core._weight_cache))):
                nan_hit = True

        if s in event_starts:
            sides = event_starts[s]

            # Snapshot pre-update state
            trace_before = core._event_trace.copy()
            w_before = core._weight_cache.copy()

            # Build combined phi
            phi = np.zeros(n_units, dtype=np.float64)
            for side in sides:
                phi += phi_cache[side]

            # Apply
            core.apply_event_pair_phi(phi)

            # Snapshot post-update state
            w_after = core._weight_cache
            dW = w_after - w_before

            trace_mass = float(np.sum(np.abs(trace_before)))
            phi_mass = float(np.sum(np.abs(phi)))

            if trace_mass > 1e-30 and phi_mass > 1e-30:
                # Compute raw eligibility = trace[src] * phi[tgt]
                raw = trace_before[src_idx] * phi[tgt_idx]

                raw_LR_l1 = _l1_mask(raw, is_LR)
                raw_RL_l1 = _l1_mask(raw, is_RL)
                raw_DI = (raw_LR_l1 - raw_RL_l1) / (raw_LR_l1 + raw_RL_l1 + EPS)
                raw_total_l1 = _l1(raw)

                # Per-connection means
                raw_LR_per_conn = raw_LR_l1 / n_LR if n_LR > 0 else 0.0
                raw_RL_per_conn = raw_RL_l1 / n_RL if n_RL > 0 else 0.0
                raw_DI_per_conn = ((raw_LR_per_conn - raw_RL_per_conn)
                                   / (raw_LR_per_conn + raw_RL_per_conn + EPS))

                # Normalized by initial weight mass
                raw_LR_norm = raw_LR_l1 / fast_LR_l1 if fast_LR_l1 > 0 else 0.0
                raw_RL_norm = raw_RL_l1 / fast_RL_l1 if fast_RL_l1 > 0 else 0.0
                raw_DI_norm = ((raw_LR_norm - raw_RL_norm)
                               / (raw_LR_norm + raw_RL_norm + EPS))

                # dW
                dW_LR_l1 = _l1_mask(dW, is_LR)
                dW_RL_l1 = _l1_mask(dW, is_RL)
                dW_DI = (dW_LR_l1 - dW_RL_l1) / (dW_LR_l1 + dW_RL_l1 + EPS)

                # Trace at sources of LR / RL connections
                trace_src_LR_l1 = _l1_mask(trace_before[src_idx], is_LR)
                trace_src_RL_l1 = _l1_mask(trace_before[src_idx], is_RL)

                # Phi at targets of LR / RL connections
                phi_tgt_LR_l1 = _l1_mask(phi[tgt_idx], is_LR)
                phi_tgt_RL_l1 = _l1_mask(phi[tgt_idx], is_RL)

                # Hemisphere breakdown
                trace_L_mass = _l1_mask(trace_before, is_L_unit)
                trace_R_mass = _l1_mask(trace_before, is_R_unit)
                phi_L_mass = _l1_mask(phi, is_L_unit)
                phi_R_mass = _l1_mask(phi, is_R_unit)

                # Matched mask
                raw_LR_l1_matched = _l1_mask(raw, matched_LR_mask)
                raw_RL_l1_matched = _l1_mask(raw, matched_RL_mask)
                raw_DI_matched = ((raw_LR_l1_matched - raw_RL_l1_matched)
                                  / (raw_LR_l1_matched + raw_RL_l1_matched + EPS))

                # Signed sums (for sign analysis)
                raw_LR_sum = float(np.sum(raw[is_LR]))
                raw_RL_sum = float(np.sum(raw[is_RL]))
                raw_LR_pos_frac = float(np.sum(raw[is_LR] > 0)) / max(n_LR, 1)
                raw_RL_pos_frac = float(np.sum(raw[is_RL] > 0)) / max(n_RL, 1)

                pair_snapshots.append({
                    "pair_idx": len(pair_snapshots),
                    "step": s,
                    "trace_mass": trace_mass,
                    "phi_mass": phi_mass,
                    # Raw eligibility
                    "raw_LR_l1": raw_LR_l1,
                    "raw_RL_l1": raw_RL_l1,
                    "raw_DI": raw_DI,
                    "raw_total_l1": raw_total_l1,
                    "raw_LR_sum": raw_LR_sum,
                    "raw_RL_sum": raw_RL_sum,
                    "raw_LR_pos_frac": raw_LR_pos_frac,
                    "raw_RL_pos_frac": raw_RL_pos_frac,
                    # Per-connection
                    "raw_LR_per_conn": raw_LR_per_conn,
                    "raw_RL_per_conn": raw_RL_per_conn,
                    "raw_DI_per_conn": raw_DI_per_conn,
                    # Normalized by initial weight
                    "raw_LR_norm": raw_LR_norm,
                    "raw_RL_norm": raw_RL_norm,
                    "raw_DI_norm": raw_DI_norm,
                    # dW
                    "dW_LR_l1": dW_LR_l1,
                    "dW_RL_l1": dW_RL_l1,
                    "dW_DI": dW_DI,
                    # Trace/phi projection
                    "trace_src_LR_l1": trace_src_LR_l1,
                    "trace_src_RL_l1": trace_src_RL_l1,
                    "phi_tgt_LR_l1": phi_tgt_LR_l1,
                    "phi_tgt_RL_l1": phi_tgt_RL_l1,
                    # Hemisphere
                    "trace_L_mass": trace_L_mass,
                    "trace_R_mass": trace_R_mass,
                    "phi_L_mass": phi_L_mass,
                    "phi_R_mass": phi_R_mass,
                    # Matched mask
                    "raw_LR_l1_matched": raw_LR_l1_matched,
                    "raw_RL_l1_matched": raw_RL_l1_matched,
                    "raw_DI_matched": raw_DI_matched,
                })

    return {
        "structure": {
            "n_LR": n_LR, "n_RL": n_RL,
            "fast_LR_l1": fast_LR_l1, "fast_RL_l1": fast_RL_l1,
            "fast_LR_RL_ratio": fast_LR_l1 / fast_RL_l1 if fast_RL_l1 > 0 else float("inf"),
            "connection_count_ratio": n_LR / n_RL if n_RL > 0 else float("inf"),
        },
        "matched": {
            "n_matched": n_matched,
            "method": "greedy nearest-neighbor on |initial_weight|",
        },
        "pair_snapshots": pair_snapshots,
        "flags": {"nan_hit": nan_hit},
    }


def _fmt_di(v):
    return f"{v:+.4f}"


def _fmt_sci(v):
    return f"{v:.4e}"


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Phase 9D.2C Event-Pair Projection Diagnostic")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--unit-count", type=int, default=300)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--output-csv", type=str,
                   default="results/phase9D2C_event_pair_projection_diagnostic.csv")
    p.add_argument("--summary-json", type=str,
                   default="results/phase9D2C_event_pair_projection_diagnostic_summary.json")
    args = p.parse_args(argv)

    base_cfg = AnivaConfig(
        unit_count=args.unit_count, seed=args.seed,
        consolidation_enabled=True,
        consolidation_ledger_enabled=True,
        event_pair_plasticity_enabled=True,
        event_pair_trace_tau=1000.0,
        event_pair_ledger_enabled=False,
    )

    print(f"Phase 9D.2C Event-Pair Projection Diagnostic")
    print(f"  seed={args.seed}  unit_count={args.unit_count}")
    print()

    if args.dry_run:
        print("  [DRY-RUN] Would extract raw eligibility at each event pair:")
        print("    raw_ij = trace[src] * phi[tgt]  (per connection)")
        print("    Aggregate by LR/RL masks")
        print("    Compare raw_DI vs dW_DI")
        print("    Matched mask analysis (greedy on |initial_weight|)")
        print("    Per-connection and per-weight-mass normalization")
        print()
        print("  Expected runtime: ~95s (single 7500-step simultaneous arm)")
        return 0

    # Run
    print(f"  Running instrumented simultaneous arm "
          f"({TOTAL_STEPS} steps) ...", end=" ", flush=True)
    t0 = time.time()
    sim_cfg = AnivaConfig(**{k: v for k, v in base_cfg.__dict__.items()
                              if not k.startswith("_")})
    sim_cfg.seed = args.seed
    result = run_projection_diagnostic(sim_cfg)
    wall_s = time.time() - t0
    print(f"{wall_s:.0f}s")
    print()

    st = result["structure"]
    mt = result["matched"]

    # ── Structure ──
    print("  === Connection Structure ===")
    print(f"    n_LR: {st['n_LR']}   n_RL: {st['n_RL']}")
    print(f"    connection_count_ratio (LR/RL): {st['connection_count_ratio']:.4f}")
    print(f"    fast_LR_l1: {st['fast_LR_l1']:.4f}")
    print(f"    fast_RL_l1: {st['fast_RL_l1']:.4f}")
    print(f"    initial_weight_mass_ratio (LR/RL): {st['fast_LR_RL_ratio']:.4f}")
    print()

    # ── Matched mask ──
    print(f"  === Matched Mask ===")
    print(f"    method: {mt['method']}")
    print(f"    n_matched: {mt['n_matched']}")
    print()

    # ── Per-pair snapshots ──
    for snap in result["pair_snapshots"]:
        pi = snap["pair_idx"]
        print(f"  {'='*60}")
        print(f"  === Event Pair {pi} (step {snap['step']}) ===")
        print(f"    trace_mass: {_fmt_sci(snap['trace_mass'])}  "
              f"phi_mass: {_fmt_sci(snap['phi_mass'])}")
        print()

        # Raw eligibility
        print(f"  --- Raw Eligibility ---")
        print(f"    raw_LR_l1:     {_fmt_sci(snap['raw_LR_l1'])}")
        print(f"    raw_RL_l1:     {_fmt_sci(snap['raw_RL_l1'])}")
        print(f"    raw_DI:        {_fmt_di(snap['raw_DI'])}")
        print(f"    raw_total_l1:  {_fmt_sci(snap['raw_total_l1'])}")
        print(f"    raw_LR_sum:    {_fmt_sci(snap['raw_LR_sum'])}  "
              f"(signed, pos_frac={snap['raw_LR_pos_frac']:.3f})")
        print(f"    raw_RL_sum:    {_fmt_sci(snap['raw_RL_sum'])}  "
              f"(signed, pos_frac={snap['raw_RL_pos_frac']:.3f})")
        print()

        # dW comparison
        print(f"  --- dW Comparison ---")
        print(f"    dW_LR_l1:      {_fmt_sci(snap['dW_LR_l1'])}")
        print(f"    dW_RL_l1:      {_fmt_sci(snap['dW_RL_l1'])}")
        print(f"    dW_DI:         {_fmt_di(snap['dW_DI'])}")
        di_diff = snap["dW_DI"] - snap["raw_DI"]
        print(f"    raw_DI vs dW_DI:  raw={_fmt_di(snap['raw_DI'])}  "
              f"dW={_fmt_di(snap['dW_DI'])}  diff={di_diff:+.2e}")
        print()

        # Trace/phi projection
        print(f"  --- Trace/Phi Projection ---")
        print(f"    trace_src_LR_l1: {_fmt_sci(snap['trace_src_LR_l1'])}")
        print(f"    trace_src_RL_l1: {_fmt_sci(snap['trace_src_RL_l1'])}")
        print(f"    phi_tgt_LR_l1:   {_fmt_sci(snap['phi_tgt_LR_l1'])}")
        print(f"    phi_tgt_RL_l1:   {_fmt_sci(snap['phi_tgt_RL_l1'])}")
        print(f"    trace_L_mass:    {_fmt_sci(snap['trace_L_mass'])}")
        print(f"    trace_R_mass:    {_fmt_sci(snap['trace_R_mass'])}")
        print(f"    phi_L_mass:      {_fmt_sci(snap['phi_L_mass'])}")
        print(f"    phi_R_mass:      {_fmt_sci(snap['phi_R_mass'])}")
        # Product comparison
        prod_LR = snap['trace_src_LR_l1'] * snap['phi_tgt_LR_l1']
        prod_RL = snap['trace_src_RL_l1'] * snap['phi_tgt_RL_l1']
        print(f"    product LR (trace_src * phi_tgt): {_fmt_sci(prod_LR)}")
        print(f"    product RL (trace_src * phi_tgt): {_fmt_sci(prod_RL)}")
        print()

        # Per-connection
        print(f"  --- Per-Connection Normalized ---")
        print(f"    raw_LR_per_conn:  {_fmt_sci(snap['raw_LR_per_conn'])}")
        print(f"    raw_RL_per_conn:  {_fmt_sci(snap['raw_RL_per_conn'])}")
        print(f"    raw_DI_per_conn:  {_fmt_di(snap['raw_DI_per_conn'])}")
        print()

        # Per-weight-mass
        print(f"  --- Per-Weight-Mass Normalized ---")
        print(f"    raw_LR_norm:      {_fmt_sci(snap['raw_LR_norm'])}")
        print(f"    raw_RL_norm:      {_fmt_sci(snap['raw_RL_norm'])}")
        print(f"    raw_DI_norm:      {_fmt_di(snap['raw_DI_norm'])}")
        print()

        # Matched mask
        print(f"  --- Matched Mask (n={mt['n_matched']}) ---")
        print(f"    raw_LR_l1_matched: {_fmt_sci(snap['raw_LR_l1_matched'])}")
        print(f"    raw_RL_l1_matched: {_fmt_sci(snap['raw_RL_l1_matched'])}")
        print(f"    raw_DI_matched:    {_fmt_di(snap['raw_DI_matched'])}")
        print()

    # ── Final Comparison ──
    if result["pair_snapshots"]:
        snap = result["pair_snapshots"][-1]  # last pair
        raw_DI = snap["raw_DI"]
        dW_DI = snap["dW_DI"]
        raw_DI_per_conn = snap["raw_DI_per_conn"]
        raw_DI_norm = snap["raw_DI_norm"]
        raw_DI_matched = snap["raw_DI_matched"]

        print("  +--------------------------------------------------+")
        print("  |  Final Comparison                               |")
        print("  +--------------------------------------------------+")
        print(f"  |  raw_DI:               {_fmt_di(raw_DI):>10}                |")
        print(f"  |  dW_DI:                {_fmt_di(dW_DI):>10}                |")
        print(f"  |  raw_DI_per_conn:      {_fmt_di(raw_DI_per_conn):>10}                |")
        print(f"  |  raw_DI_norm:          {_fmt_di(raw_DI_norm):>10}                |")
        print(f"  |  raw_DI_matched:       {_fmt_di(raw_DI_matched):>10}                |")
        print("  +--------------------------------------------------+")
        print()

        # Verdict
        raw_dW_match = abs(raw_DI - dW_DI) < 1e-6
        matched_near_zero = abs(raw_DI_matched) < 0.02
        per_conn_near_zero = abs(raw_DI_per_conn) < 0.02
        norm_near_zero = abs(raw_DI_norm) < 0.02
        raw_large = abs(raw_DI) > 0.02

        if raw_dW_match and raw_large and not matched_near_zero:
            verdict = (
                f"geometry_projection_asymmetry: raw_DI={raw_DI:+.4f} == "
                f"dW_DI={dW_DI:+.4f}. L1 normalization is DI-invariant. "
                f"Matched mask DI={raw_DI_matched:+.4f} not near zero — bias is "
                f"inherent in trace×phi projection onto directed topology, "
                f"not a connection-count or weight-mass artifact."
            )
            if per_conn_near_zero:
                verdict += (" However, per_connection_raw_DI near zero suggests "
                            "the bias is amplified by connection-count aggregation.")
        elif raw_dW_match and matched_near_zero:
            verdict = (
                f"mask_aggregation_artifact: raw_DI={raw_DI:+.4f} but "
                f"matched_raw_DI={raw_DI_matched:+.4f} near zero. "
                f"The simultaneous caveat is driven by LR/RL connection-count "
                f"and weight-distribution differences in the full mask. "
                f"Matched-mask DI suggests a clean simultaneous control."
            )
        elif raw_dW_match and per_conn_near_zero and not matched_near_zero:
            verdict = (
                f"connection_count_amplification: raw_DI_per_conn={raw_DI_per_conn:+.4f} "
                f"near zero, but total raw_DI={raw_DI:+.4f} and "
                f"matched_raw_DI={raw_DI_matched:+.4f} diverge. "
                f"DI is amplified by aggregating over unequal connection counts."
            )
        elif not raw_dW_match:
            verdict = (
                f"normalization_divergence: raw_DI={raw_DI:+.4f} != "
                f"dW_DI={dW_DI:+.4f}. L1 normalization or weight clamping "
                f"is not DI-invariant. Check clipping at weight boundaries."
            )
        elif norm_near_zero and not raw_large:
            verdict = (
                f"initial_mass_normalization: raw_DI_norm near zero. "
                f"Bias is explained by initial weight mass differences "
                f"between LR and RL subgraphs."
            )
        else:
            verdict = (
                f"diffuse_projection_bias: multiple factors contribute. "
                f"raw_DI={raw_DI:+.4f}, matched={raw_DI_matched:+.4f}, "
                f"per_conn={raw_DI_per_conn:+.4f}, norm={raw_DI_norm:+.4f}."
            )

        print(f"  VERDICT: {verdict}")
        print()
        print(f"  nan={result['flags']['nan_hit']}")
        print()

        # CSV
        row = {
            "seed": args.seed, "unit_count": args.unit_count,
            "n_LR": st["n_LR"], "n_RL": st["n_RL"],
            "fast_LR_l1": st["fast_LR_l1"], "fast_RL_l1": st["fast_RL_l1"],
            "n_matched": mt["n_matched"],
            "raw_LR_l1": snap["raw_LR_l1"], "raw_RL_l1": snap["raw_RL_l1"],
            "raw_DI": raw_DI,
            "dW_LR_l1": snap["dW_LR_l1"], "dW_RL_l1": snap["dW_RL_l1"],
            "dW_DI": dW_DI,
            "raw_DI_per_conn": raw_DI_per_conn,
            "raw_DI_norm": raw_DI_norm,
            "raw_DI_matched": raw_DI_matched,
            "trace_src_LR_l1": snap["trace_src_LR_l1"],
            "trace_src_RL_l1": snap["trace_src_RL_l1"],
            "phi_tgt_LR_l1": snap["phi_tgt_LR_l1"],
            "phi_tgt_RL_l1": snap["phi_tgt_RL_l1"],
            "verdict": verdict,
            "wall_time_s": wall_s,
            "nan_hit": result["flags"]["nan_hit"],
        }

        if args.output_csv:
            with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(row.keys()))
                w.writeheader()
                w.writerows([row])
            print(f"  CSV: {args.output_csv}")

        if args.summary_json:
            summary = {
                "experiment": "phase9D2C_event_pair_projection_diagnostic",
                "params": {"seed": args.seed, "unit_count": args.unit_count,
                           "total_steps": TOTAL_STEPS, "n_pairs": N_PAIRS},
                "structure": st,
                "matched": mt,
                "pair_snapshots": result["pair_snapshots"],
                "verdict": verdict,
                "wall_time_s": wall_s,
            }
            with open(args.summary_json, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
            print(f"  JSON: {args.summary_json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
