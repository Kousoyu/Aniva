"""Phase 10E.1C — Event-Type / Topology Diagnostic Analyzer.

Offline analyzer. Reads existing 10E.1B events CSV.
Does NOT re-run simulation.

Core question: where does the global novelty_factor signal break down?
  - Event-type split (L vs R)
  - Subgraph split (LL, LR, RL, RR, ...)
  - Within-subgraph matched diagnostic (high-h vs low-h)
  - Seed topology dependence (h_tag_ratio direction per subgraph)
  - Surprise vs novelty stability

Design: docs/phase10E1C_event_type_topology_diagnostic_design.md
"""

import argparse, csv, json, sys, time
import numpy as np
from collections import defaultdict


TAG_EPS = 1e-10
N_SHUFFLES_DEFAULT = 100


# ═══════════════════════════════════════════════════════════════════
# Math helpers (no sklearn)
# ═══════════════════════════════════════════════════════════════════

def _rank_auc(scores, labels):
    """P(score_pos > score_neg). O(n log n) via rank-sum."""
    labels = np.asarray(labels, dtype=np.int8)
    n_pos = int(np.sum(labels == 1))
    n_neg = int(np.sum(labels == 0))
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    ranks = np.argsort(np.argsort(scores)) + 1
    rank_sum_pos = float(np.sum(ranks[labels == 1]))
    return (rank_sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def _percentile_rank(observed, distribution):
    dist = np.array([v for v in distribution if not np.isnan(v)])
    if len(dist) == 0:
        return float("nan")
    return float(np.mean(dist < observed))


def _r(v):
    if isinstance(v, float) and np.isnan(v):
        return "nan"
    if isinstance(v, float):
        return round(v, 6)
    return v


# ═══════════════════════════════════════════════════════════════════
# Load events CSV
# ═══════════════════════════════════════════════════════════════════

def _load_events(path):
    rows = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            rows.append({
                "seed": int(row["seed"]),
                "arm": row["arm"],
                "event_type": row["event_type"],
                "src_region": row["src_region"],
                "tgt_region": row["tgt_region"],
                "subgraph": row["subgraph"],
                "h_conn": float(row["h_conn"]),
                "h_norm_conn": float(row["h_norm_conn"]),
                "novelty_factor": float(row["novelty_factor"]),
                "surprise_factor": float(row["surprise_factor"]),
                "pos_factor": float(row["pos_factor"]),
                "neg_factor": float(row["neg_factor"]),
                "phi_conn": float(row["phi_conn"]),
                "tag_presence": int(row["tag_presence"]),
                "tag_strength": float(row["tag_strength"]),
                "tag_delta": float(row["tag_delta"]),
                "event_pair_dW": float(row["event_pair_dW"]),
                "baseline_weight_abs": float(row["baseline_weight_abs"]),
            })
    return rows


# ═══════════════════════════════════════════════════════════════════
# Core group analysis
# ═══════════════════════════════════════════════════════════════════

def _analyze_group(rows, n_shuffles, rng):
    """Compute diagnostics for one group of rows."""
    if not rows:
        return None

    novelty = np.array([r["novelty_factor"] for r in rows])
    h_conn = np.array([r["h_conn"] for r in rows])
    surprise = np.array([r["surprise_factor"] for r in rows])
    pos_f = np.array([r["pos_factor"] for r in rows])
    neg_f = np.array([r["neg_factor"] for r in rows])
    phi = np.array([r["phi_conn"] for r in rows])
    presence = np.array([r["tag_presence"] for r in rows], dtype=np.int8)
    strength = np.array([r["tag_strength"] for r in rows])
    dW = np.array([r["event_pair_dW"] for r in rows])

    n_conn = len(rows)
    n_tagged = int(np.sum(presence))
    if n_conn == 0:
        return None
    tag_rate = n_tagged / n_conn

    tagged_mask = presence == 1
    untagged_mask = ~tagged_mask

    mean_h_tagged = float(np.mean(h_conn[tagged_mask])) if tagged_mask.any() else float("nan")
    mean_h_untagged = float(np.mean(h_conn[untagged_mask])) if untagged_mask.any() else float("nan")
    mean_nv_tagged = float(np.mean(novelty[tagged_mask])) if tagged_mask.any() else float("nan")
    mean_nv_untagged = float(np.mean(novelty[untagged_mask])) if untagged_mask.any() else float("nan")
    mean_phi_tagged = float(np.mean(phi[tagged_mask])) if tagged_mask.any() else float("nan")
    mean_phi_untagged = float(np.mean(phi[untagged_mask])) if untagged_mask.any() else float("nan")

    eps = 1e-12
    h_tag_ratio = (mean_h_tagged / mean_h_untagged
                   if not np.isnan(mean_h_untagged) and mean_h_untagged > eps
                   else float("nan"))
    novelty_tag_ratio = (mean_nv_tagged / mean_nv_untagged
                         if not np.isnan(mean_nv_untagged) and mean_nv_untagged > eps
                         else float("nan"))

    auc_h = _rank_auc(-h_conn, presence)
    auc_novelty = _rank_auc(novelty, presence)
    auc_surprise = _rank_auc(surprise, presence)
    auc_pos = _rank_auc(pos_f, presence)
    auc_neg = _rank_auc(neg_f, presence)

    phi_mass = float(np.sum(np.abs(phi)))
    phi_mass_per_conn = phi_mass / n_conn
    tag_delta_mass = float(np.sum(np.abs([r["tag_delta"] for r in rows])))
    dW_l1 = float(np.sum(np.abs(dW)))

    # Shuffle null
    shuffle_nv, shuffle_sur = [], []
    for _ in range(n_shuffles):
        h_shuf = rng.permutation(h_conn)
        h_max = float(np.max(h_shuf)) + 1e-9
        nv_shuf = 1.0 - h_shuf / h_max
        sur_shuf = np.abs(phi - h_shuf / h_max)
        shuffle_nv.append(_rank_auc(nv_shuf, presence))
        shuffle_sur.append(_rank_auc(sur_shuf, presence))
    pct_nv = _percentile_rank(auc_novelty, shuffle_nv)
    pct_sur = _percentile_rank(auc_surprise, shuffle_sur)

    # Within-subgraph matched diagnostic (Axis 6)
    # Split connections by median h within this group, compare tag_rate
    h_median = float(np.median(h_conn))
    high_h_mask = h_conn >= h_median
    low_h_mask = ~high_h_mask
    high_h_tag_rate = (float(np.mean(presence[high_h_mask]))
                       if high_h_mask.any() else float("nan"))
    low_h_tag_rate = (float(np.mean(presence[low_h_mask]))
                      if low_h_mask.any() else float("nan"))
    within_auc_novelty = float("nan")
    if high_h_mask.sum() >= 2 and low_h_mask.sum() >= 2:
        within_auc_novelty = _rank_auc(novelty, presence)

    # Best predictor
    aucs = {"h_inv": auc_h, "novelty": auc_novelty, "surprise": auc_surprise,
            "pos": auc_pos, "neg": auc_neg}
    best = max(aucs, key=lambda k: aucs[k] if not np.isnan(aucs[k]) else -1)

    # Group verdict
    verdict = _group_verdict(auc_novelty, pct_nv, auc_surprise, pct_sur, n_tagged)

    return {
        "n_connections": n_conn,
        "n_tagged": n_tagged,
        "tag_rate": _r(tag_rate),
        "mean_h_tagged": _r(mean_h_tagged),
        "mean_h_untagged": _r(mean_h_untagged),
        "h_tag_ratio": _r(h_tag_ratio),
        "novelty_tag_ratio": _r(novelty_tag_ratio),
        "mean_phi_tagged": _r(mean_phi_tagged),
        "mean_phi_untagged": _r(mean_phi_untagged),
        "auc_h_inverted": _r(auc_h),
        "auc_novelty": _r(auc_novelty),
        "auc_surprise": _r(auc_surprise),
        "auc_pos": _r(auc_pos),
        "auc_neg": _r(auc_neg),
        "phi_mass": _r(phi_mass),
        "phi_mass_per_conn": _r(phi_mass_per_conn),
        "tag_delta_mass": _r(tag_delta_mass),
        "event_pair_dW_l1": _r(dW_l1),
        "shuffle_percentile_novelty": _r(pct_nv),
        "shuffle_percentile_surprise": _r(pct_sur),
        "high_h_tag_rate": _r(high_h_tag_rate),
        "low_h_tag_rate": _r(low_h_tag_rate),
        "within_auc_novelty": _r(within_auc_novelty),
        "best_predictor": best,
        "group_verdict": verdict,
    }


def _group_verdict(auc_nv, pct_nv, auc_sur, pct_sur, n_tagged):
    def ok(v): return not (isinstance(v, float) and np.isnan(v))
    if n_tagged == 0:
        return "no_tags"
    if ok(auc_nv) and auc_nv > 0.5 and ok(pct_nv) and pct_nv > 0.90:
        return "novelty_pass"
    if ok(auc_nv) and auc_nv > 0.5 and ok(pct_nv) and pct_nv > 0.75:
        return "novelty_weak"
    if ok(auc_nv) and auc_nv < 0.48:
        if ok(auc_sur) and auc_sur > 0.5 and ok(pct_sur) and pct_sur > 0.90:
            return "novelty_inverse_surprise_pass"
        return "novelty_inverse"
    if ok(auc_sur) and auc_sur > 0.5 and ok(pct_sur) and pct_sur > 0.90:
        return "surprise_pass"
    return "null"


# ═══════════════════════════════════════════════════════════════════
# Build all groups
# ═══════════════════════════════════════════════════════════════════

def _build_groups(rows):
    """Return dict of group_key → list of rows for all analysis axes."""
    groups = defaultdict(list)
    for r in rows:
        seed = r["seed"]
        arm = r["arm"]
        etype = r["event_type"]
        sg = r["subgraph"]
        src = r["src_region"]
        tgt = r["tgt_region"]

        # Axis 1: seed × arm × event_type (+ ALL)
        groups[(seed, arm, "ALL", "ALL", "ALL", "ALL")].append(r)
        groups[(seed, arm, etype, "ALL", "ALL", "ALL")].append(r)

        # Axis 2: seed × arm × event_type × subgraph
        groups[(seed, arm, "ALL", sg, src, tgt)].append(r)
        groups[(seed, arm, etype, sg, src, tgt)].append(r)

    return groups


def _key_to_dict(key):
    seed, arm, etype, sg, src, tgt = key
    return {
        "seed": seed, "arm": arm, "event_type": etype,
        "subgraph": sg, "src_region": src, "tgt_region": tgt,
    }


# ═══════════════════════════════════════════════════════════════════
# Cross-seed diagnostics
# ═══════════════════════════════════════════════════════════════════

def _cross_seed_verdict(summaries):
    """Apply 10E.1C decision rules across seeds."""
    seeds = sorted(set(s["seed"] for s in summaries))

    # Aggregate (ALL event_type, ALL subgraph, closed_loop)
    agg = {s["seed"]: s for s in summaries
           if s["arm"] == "closed_loop"
           and s["event_type"] == "ALL"
           and s["subgraph"] == "ALL"}

    # L/R per seed (closed_loop)
    by_etype = defaultdict(dict)
    for s in summaries:
        if s["arm"] == "closed_loop" and s["subgraph"] == "ALL":
            by_etype[s["seed"]][s["event_type"]] = s

    # Per-subgraph per seed (closed_loop, ALL event_type)
    by_sg = defaultdict(lambda: defaultdict(list))
    for s in summaries:
        if s["arm"] == "closed_loop" and s["event_type"] == "ALL" and s["subgraph"] != "ALL":
            by_sg[s["seed"]][s["subgraph"]].append(s)

    n_seeds = len(seeds)

    # Count L/R pass
    n_L_pass = sum(1 for seed in seeds
                   if by_etype[seed].get("L", {}).get("group_verdict", "null")
                   in ("novelty_pass", "novelty_weak"))
    n_R_pass = sum(1 for seed in seeds
                   if by_etype[seed].get("R", {}).get("group_verdict", "null")
                   in ("novelty_pass", "novelty_weak"))
    n_R_null = sum(1 for seed in seeds
                   if by_etype[seed].get("R", {}).get("group_verdict", "null")
                   not in ("novelty_pass", "novelty_weak"))

    # Count seeds with severe inverse in aggregate
    n_severe_inverse = sum(1 for seed in seeds
                           if seed in agg
                           and isinstance(agg[seed]["auc_novelty"], float)
                           and agg[seed]["auc_novelty"] < 0.48)

    # Count seeds where surprise is better than novelty in aggregate
    n_surprise_better = sum(1 for seed in seeds
                            if seed in agg
                            and agg[seed].get("best_predictor") in ("surprise", "neg"))

    # Check if seed123/999 invert globally (all subgraphs) or only some
    inversion_seeds = [seed for seed in seeds
                       if seed in agg
                       and isinstance(agg[seed]["auc_novelty"], float)
                       and agg[seed]["auc_novelty"] < 0.48]
    global_inversion = {}
    for seed in inversion_seeds:
        sg_verdicts = []
        for sg_rows in by_sg[seed].values():
            for row in sg_rows:
                sg_verdicts.append(row.get("group_verdict", "null"))
        n_inv = sum(1 for v in sg_verdicts if "inverse" in v)
        n_total = len(sg_verdicts)
        global_inversion[seed] = (n_inv / n_total if n_total > 0 else float("nan"))

    # Check within-subgraph novelty (Axis 6 gate)
    # For each seed, count subgraphs where novelty holds within matched split
    n_seeds_local_signal = 0
    for seed in seeds:
        sg_pass = 0
        sg_total = 0
        for sg_rows in by_sg[seed].values():
            for row in sg_rows:
                if row.get("n_tagged", 0) >= 2:
                    sg_total += 1
                    if row.get("group_verdict", "null") in ("novelty_pass", "novelty_weak"):
                        sg_pass += 1
        if sg_total > 0 and sg_pass / sg_total >= 0.5:
            n_seeds_local_signal += 1

    # Final cross-seed verdict
    if n_R_null >= 3 and n_L_pass >= 3:
        cross_verdict = "event_type_asymmetry_confirmed"
    elif n_severe_inverse >= 2 and all(
            global_inversion.get(s, 0) > 0.6 for s in inversion_seeds):
        cross_verdict = "seed_topology_dependent_history"
    elif n_seeds_local_signal >= 3:
        cross_verdict = "local_historical_context_signal"
    elif n_surprise_better >= 3:
        cross_verdict = "surprise_better_than_novelty"
    else:
        cross_verdict = "null_for_current_h_descriptor"

    return {
        "n_seeds": n_seeds,
        "n_L_pass": n_L_pass,
        "n_R_pass": n_R_pass,
        "n_R_null": n_R_null,
        "n_severe_inverse": n_severe_inverse,
        "n_surprise_better": n_surprise_better,
        "n_seeds_local_signal": n_seeds_local_signal,
        "inversion_global_fraction": {str(k): _r(v) for k, v in global_inversion.items()},
        "cross_seed_verdict": cross_verdict,
    }


# ═══════════════════════════════════════════════════════════════════
# Save helpers
# ═══════════════════════════════════════════════════════════════════

def _save_csv(rows, path):
    if not rows:
        return
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _git_sha():
    import subprocess
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Phase 10E.1C Event-Type / Topology Diagnostic Analyzer")
    parser.add_argument(
        "--input-events-csv",
        default="results/phase10E1B_tag_formation_events.csv")
    parser.add_argument(
        "--summary-csv",
        default="results/phase10E1C_event_type_topology_summary.csv")
    parser.add_argument(
        "--summary-json",
        default="results/phase10E1C_event_type_topology_summary.json")
    parser.add_argument("--n-shuffles", type=int, default=N_SHUFFLES_DEFAULT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--estimate-only", action="store_true")
    args = parser.parse_args()

    import os
    if not os.path.exists(args.input_events_csv):
        print(f"ERROR: events CSV not found: {args.input_events_csv}", file=sys.stderr)
        print("Re-run exp10E1_tag_formation_historical_context_diagnostics.py "
              "with --seeds 42 77 123 999 to regenerate.", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"[dry-run] input: {args.input_events_csv}")
        print(f"[dry-run] output csv: {args.summary_csv}")
        print(f"[dry-run] output json: {args.summary_json}")
        print(f"[dry-run] n_shuffles: {args.n_shuffles}")
        print("[dry-run] config OK, exiting.")
        return 0

    if args.estimate_only:
        size_mb = os.path.getsize(args.input_events_csv) / 1e6
        print(f"[estimate] input CSV: {size_mb:.1f} MB")
        print(f"[estimate] n_shuffles={args.n_shuffles}")
        print("[estimate] ~30-120s depending on CSV size and shuffle count")
        return 0

    print("Phase 10E.1C Event-Type / Topology Diagnostic Analyzer")
    print(f"  input: {args.input_events_csv}")
    print(f"  n_shuffles: {args.n_shuffles}")

    t0 = time.time()
    print("Loading events CSV ...")
    all_rows = _load_events(args.input_events_csv)
    print(f"  loaded {len(all_rows):,} rows in {time.time()-t0:.1f}s")

    seeds = sorted(set(r["seed"] for r in all_rows))
    arms = sorted(set(r["arm"] for r in all_rows))
    print(f"  seeds={seeds}  arms={arms}")

    print("Building groups ...")
    groups = _build_groups(all_rows)
    print(f"  {len(groups)} groups")

    rng = np.random.default_rng(99999)
    summaries = []
    n_groups = len(groups)
    for i, (key, rows) in enumerate(sorted(groups.items())):
        if (i + 1) % 50 == 0:
            print(f"  [{i+1}/{n_groups}] ...")
        result = _analyze_group(rows, args.n_shuffles, rng)
        if result is not None:
            entry = _key_to_dict(key)
            entry.update(result)
            summaries.append(entry)

    elapsed = time.time() - t0
    print(f"Analysis done in {elapsed:.1f}s — {len(summaries)} summary rows")

    # Cross-seed verdict
    cross = _cross_seed_verdict(summaries)
    print("\n=== Cross-seed verdict ===")
    for k, v in cross.items():
        print(f"  {k}: {v}")

    # Print key per-seed L/R breakdown
    print("\n=== Per-seed L/R (closed_loop) ===")
    for s in summaries:
        if (s["arm"] == "closed_loop"
                and s["subgraph"] == "ALL"
                and s["event_type"] in ("L", "R", "ALL")):
            print(f"  seed={s['seed']} etype={s['event_type']}"
                  f"  auc_nv={s['auc_novelty']}"
                  f"  shuf_nv={s['shuffle_percentile_novelty']}"
                  f"  h_tag_ratio={s['h_tag_ratio']}"
                  f"  verdict={s['group_verdict']}")

    # Print subgraph breakdown for inversion seeds
    print("\n=== Subgraph breakdown (closed_loop, ALL event_type) ===")
    for s in summaries:
        if (s["arm"] == "closed_loop"
                and s["event_type"] == "ALL"
                and s["subgraph"] != "ALL"
                and s["n_tagged"] >= 2):
            print(f"  seed={s['seed']} sg={s['subgraph']}"
                  f"  auc_nv={s['auc_novelty']}"
                  f"  h_tag_ratio={s['h_tag_ratio']}"
                  f"  n_tagged={s['n_tagged']}/{s['n_connections']}"
                  f"  verdict={s['group_verdict']}")

    # Save
    _save_csv(summaries, args.summary_csv)
    output = {
        "experiment": "phase10E1C_event_type_topology_diagnostic",
        "git_sha": _git_sha(),
        "timestamp": int(time.time()),
        "input_events_csv": args.input_events_csv,
        "n_shuffles": args.n_shuffles,
        "n_rows_loaded": len(all_rows),
        "n_summary_rows": len(summaries),
        "cross_seed": cross,
        "summaries": summaries,
    }
    with open(args.summary_json, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nSaved: {args.summary_csv}")
    print(f"Saved: {args.summary_json}")
    print(f"\nFinal cross-seed verdict: {cross['cross_seed_verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
