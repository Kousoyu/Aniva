"""Phase 10E.1D — Subgraph / Phi-Driven Tag Formation Diagnostic Analyzer.

Offline analyzer. Reads existing 10E.1B events CSV.
Does NOT re-run simulation.

Core question: is tag formation driven by phi/stimulus geometry, or does
historical context (h[u]) survive when we control for phi?

Design: docs/phase10E1D_subgraph_phi_tag_formation_diagnostic_design.md
"""

import argparse, csv, json, sys, time
import numpy as np
from collections import defaultdict


TAG_EPS = 1e-10
N_BINS_DEFAULT = 5
N_SHUFFLES_DEFAULT = 100
MIN_TAGGED = 3
MIN_BIN_TAGGED = 2


# ═══════════════════════════════════════════════════════════════════
# Math helpers
# ═══════════════════════════════════════════════════════════════════

def _rank_auc(scores, labels):
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
# Matched-bin AUC (Axis 4 / 5)
# ═══════════════════════════════════════════════════════════════════

def _matched_bin_auc(predictor, labels, control, n_bins):
    """Within-bin AUC of predictor, stratified by quantile bins of control.

    Returns weighted mean AUC across bins (weight = n_connections in bin).
    Returns nan if too few bins have enough tagged examples.
    """
    control = np.asarray(control, dtype=np.float64)
    predictor = np.asarray(predictor, dtype=np.float64)
    labels = np.asarray(labels, dtype=np.int8)

    quantiles = np.linspace(0, 100, n_bins + 1)
    edges = np.percentile(control, quantiles)
    edges[-1] += 1e-9  # include max

    bin_aucs, bin_weights = [], []
    for i in range(n_bins):
        mask = (control >= edges[i]) & (control < edges[i + 1])
        if mask.sum() < 4:
            continue
        bin_labels = labels[mask]
        if bin_labels.sum() < MIN_BIN_TAGGED or (mask.sum() - bin_labels.sum()) < MIN_BIN_TAGGED:
            continue
        auc = _rank_auc(predictor[mask], bin_labels)
        if not np.isnan(auc):
            bin_aucs.append(auc)
            bin_weights.append(float(mask.sum()))

    if not bin_aucs:
        return float("nan")
    weights = np.array(bin_weights)
    return float(np.average(bin_aucs, weights=weights))


# ═══════════════════════════════════════════════════════════════════
# Core group analysis
# ═══════════════════════════════════════════════════════════════════

def _analyze_group(rows, n_bins, n_shuffles, rng):
    if not rows:
        return None

    novelty = np.array([r["novelty_factor"] for r in rows])
    h_conn = np.array([r["h_conn"] for r in rows])
    h_norm = np.array([r["h_norm_conn"] for r in rows])
    surprise = np.array([r["surprise_factor"] for r in rows])
    pos_f = np.array([r["pos_factor"] for r in rows])
    neg_f = np.array([r["neg_factor"] for r in rows])
    phi = np.array([r["phi_conn"] for r in rows])
    bw = np.array([r["baseline_weight_abs"] for r in rows])
    dW = np.array([r["event_pair_dW"] for r in rows])
    presence = np.array([r["tag_presence"] for r in rows], dtype=np.int8)
    strength = np.array([r["tag_strength"] for r in rows])

    n_conn = len(rows)
    n_tagged = int(np.sum(presence))
    tag_rate = n_tagged / n_conn if n_conn > 0 else float("nan")

    if n_tagged < MIN_TAGGED:
        return {"n_connections": n_conn, "n_tagged": n_tagged,
                "tag_rate": _r(tag_rate), "subgraph_verdict": "null_or_insufficient",
                "best_predictor": "nan"}

    tagged_mask = presence == 1
    untagged_mask = ~tagged_mask
    eps = 1e-12

    def _ratio(a, b):
        ma = float(np.mean(a[tagged_mask])) if tagged_mask.any() else float("nan")
        mb = float(np.mean(b[untagged_mask])) if untagged_mask.any() else float("nan")
        return (ma / mb if not np.isnan(mb) and mb > eps else float("nan")), ma, mb

    h_tag_ratio, mean_h_tagged, mean_h_untagged = _ratio(h_conn, h_conn)
    phi_tag_ratio, mean_phi_tagged, mean_phi_untagged = _ratio(phi, phi)
    sur_tag_ratio, mean_sur_tagged, mean_sur_untagged = _ratio(surprise, surprise)
    nv_tag_ratio, mean_nv_tagged, mean_nv_untagged = _ratio(novelty, novelty)

    # AUC for all predictors
    auc_novelty = _rank_auc(novelty, presence)
    auc_phi = _rank_auc(phi, presence)
    auc_surprise = _rank_auc(surprise, presence)
    auc_pos = _rank_auc(pos_f, presence)
    auc_neg = _rank_auc(neg_f, presence)
    auc_h_inv = _rank_auc(-h_conn, presence)
    auc_bw = _rank_auc(bw, presence)
    abs_dW = np.abs(dW)
    auc_abs_dW = _rank_auc(abs_dW, presence)

    aucs = {
        "novelty": auc_novelty, "phi": auc_phi, "surprise": auc_surprise,
        "pos": auc_pos, "neg": auc_neg, "h_inv": auc_h_inv,
        "baseline_weight": auc_bw, "abs_dW": auc_abs_dW,
    }
    best = max(aucs, key=lambda k: aucs[k] if not np.isnan(aucs[k]) else -1)

    # Axis 4: matched-phi novelty AUC
    matched_phi_novelty_auc = _matched_bin_auc(novelty, presence, phi, n_bins)

    # Axis 5: matched-h phi AUC
    matched_h_phi_auc = _matched_bin_auc(phi, presence, h_norm, n_bins)

    # Raw dW layer
    dW_l1_tagged = float(np.sum(abs_dW[tagged_mask])) if tagged_mask.any() else float("nan")
    dW_l1_untagged = float(np.sum(abs_dW[untagged_mask])) if untagged_mask.any() else float("nan")
    if tagged_mask.sum() >= 2:
        corr_abs_dW_tag_strength = float(np.corrcoef(abs_dW[tagged_mask], strength[tagged_mask])[0, 1])
    else:
        corr_abs_dW_tag_strength = float("nan")

    verdict = _subgraph_verdict(
        auc_novelty, auc_phi, auc_surprise, auc_abs_dW,
        matched_phi_novelty_auc, matched_h_phi_auc,
        h_tag_ratio, rows[0]["subgraph"], n_tagged)

    return {
        "n_connections": n_conn, "n_tagged": n_tagged, "tag_rate": _r(tag_rate),
        "h_tag_ratio": _r(h_tag_ratio), "phi_tag_ratio": _r(phi_tag_ratio),
        "surprise_tag_ratio": _r(sur_tag_ratio), "novelty_tag_ratio": _r(nv_tag_ratio),
        "mean_h_tagged": _r(mean_h_tagged), "mean_h_untagged": _r(mean_h_untagged),
        "mean_phi_tagged": _r(mean_phi_tagged), "mean_phi_untagged": _r(mean_phi_untagged),
        "auc_novelty": _r(auc_novelty), "auc_phi": _r(auc_phi),
        "auc_surprise": _r(auc_surprise), "auc_pos": _r(auc_pos),
        "auc_neg": _r(auc_neg), "auc_inverted_h": _r(auc_h_inv),
        "auc_baseline_weight": _r(auc_bw), "auc_abs_dW": _r(auc_abs_dW),
        "best_predictor": best,
        "matched_phi_novelty_auc": _r(matched_phi_novelty_auc),
        "matched_h_phi_auc": _r(matched_h_phi_auc),
        "dW_l1_tagged": _r(dW_l1_tagged), "dW_l1_untagged": _r(dW_l1_untagged),
        "corr_abs_dW_tag_strength": _r(corr_abs_dW_tag_strength),
        "subgraph_verdict": verdict,
    }


def _subgraph_verdict(auc_nv, auc_phi, auc_sur, auc_dW,
                      matched_phi_nv, matched_h_phi,
                      h_tag_ratio, subgraph, n_tagged):
    def ok(v): return isinstance(v, float) and not np.isnan(v)

    if n_tagged < MIN_TAGGED:
        return "null_or_insufficient"

    # raw dW already explains tag split
    if ok(auc_dW) and auc_dW > 0.65:
        return "raw_9C_geometry_root"

    # local historical context survives phi control
    if ok(matched_phi_nv) and matched_phi_nv > 0.55:
        return "local_historical_context_signal"

    # phi/surprise beats novelty and novelty disappears under phi control
    phi_beats = ok(auc_phi) and ok(auc_nv) and auc_phi > auc_nv
    sur_beats = ok(auc_sur) and ok(auc_nv) and auc_sur > auc_nv
    nv_gone = ok(matched_phi_nv) and matched_phi_nv < 0.52
    if (phi_beats or sur_beats) and nv_gone:
        return "stimulus_geometry_dominant"

    # phi/surprise consistently beats novelty (even without matched control)
    if phi_beats or sur_beats:
        return "phi_surprise_driven_tag_formation"

    # LL special case: h_tag_ratio > 1.0 and novelty inverted
    if subgraph == "LL" and ok(h_tag_ratio) and h_tag_ratio > 1.0 and ok(auc_nv) and auc_nv < 0.5:
        return "LL_recurrent_subgraph_special_case"

    # novelty still predictive
    if ok(auc_nv) and auc_nv > 0.5:
        return "novelty_predictive"

    return "null_or_insufficient"


# ═══════════════════════════════════════════════════════════════════
# Build groups
# ═══════════════════════════════════════════════════════════════════

def _build_groups(rows):
    groups = defaultdict(list)
    for r in rows:
        seed, arm = r["seed"], r["arm"]
        etype, sg = r["event_type"], r["subgraph"]
        # seed × arm × event_type × subgraph
        groups[(seed, arm, etype, sg)].append(r)
        # seed × arm × ALL × subgraph
        groups[(seed, arm, "ALL", sg)].append(r)
        # seed × arm × event_type × ALL
        groups[(seed, arm, etype, "ALL")].append(r)
        # seed × arm × ALL × ALL
        groups[(seed, arm, "ALL", "ALL")].append(r)
    return groups


def _key_to_dict(key):
    seed, arm, etype, sg = key
    return {"seed": seed, "arm": arm, "event_type": etype, "subgraph": sg}


# ═══════════════════════════════════════════════════════════════════
# Cross-seed verdict
# ═══════════════════════════════════════════════════════════════════

def _cross_seed_verdict(summaries):
    seeds = sorted(set(s["seed"] for s in summaries))

    # Aggregate per seed (closed_loop, ALL etype, ALL subgraph)
    agg = {s["seed"]: s for s in summaries
           if s["arm"] == "closed_loop"
           and s["event_type"] == "ALL"
           and s["subgraph"] == "ALL"}

    # LL per seed (closed_loop, ALL etype)
    ll = {s["seed"]: s for s in summaries
          if s["arm"] == "closed_loop"
          and s["event_type"] == "ALL"
          and s["subgraph"] == "LL"}

    # RR per seed (closed_loop, ALL etype)
    rr = {s["seed"]: s for s in summaries
          if s["arm"] == "closed_loop"
          and s["event_type"] == "ALL"
          and s["subgraph"] == "RR"}

    def ok(v): return isinstance(v, float) and not np.isnan(v)

    # LL: 4/4 seeds h_tag_ratio > 1.0?
    ll_inversion_count = sum(
        1 for seed in seeds
        if seed in ll
        and ok(ll[seed].get("h_tag_ratio", float("nan")))
        and ll[seed]["h_tag_ratio"] > 1.0)
    ll_systematic = ll_inversion_count == len(seeds)

    # RR seed split
    rr_novelty_pass = [seed for seed in seeds
                       if seed in rr
                       and rr[seed].get("subgraph_verdict", "") in
                       ("novelty_predictive", "local_historical_context_signal")]
    rr_inverse = [seed for seed in seeds
                  if seed in rr
                  and ok(rr[seed].get("auc_novelty", float("nan")))
                  and rr[seed]["auc_novelty"] < 0.48]
    rr_split_confirmed = len(rr_novelty_pass) >= 1 and len(rr_inverse) >= 1

    # phi/surprise beats novelty in aggregate
    n_phi_beats = sum(
        1 for seed in seeds
        if seed in agg
        and ok(agg[seed].get("auc_phi", float("nan")))
        and ok(agg[seed].get("auc_novelty", float("nan")))
        and agg[seed]["auc_phi"] > agg[seed]["auc_novelty"])
    n_sur_beats = sum(
        1 for seed in seeds
        if seed in agg
        and ok(agg[seed].get("auc_surprise", float("nan")))
        and ok(agg[seed].get("auc_novelty", float("nan")))
        and agg[seed]["auc_surprise"] > agg[seed]["auc_novelty"])

    # matched-phi: novelty survives?
    n_matched_phi_novelty_survives = sum(
        1 for seed in seeds
        if seed in agg
        and ok(agg[seed].get("matched_phi_novelty_auc", float("nan")))
        and agg[seed]["matched_phi_novelty_auc"] > 0.55)

    # matched-h: phi survives?
    n_matched_h_phi_survives = sum(
        1 for seed in seeds
        if seed in agg
        and ok(agg[seed].get("matched_h_phi_auc", float("nan")))
        and agg[seed]["matched_h_phi_auc"] > 0.55)

    # raw dW explains tag split?
    n_dW_root = sum(
        1 for seed in seeds
        if seed in agg
        and ok(agg[seed].get("auc_abs_dW", float("nan")))
        and agg[seed]["auc_abs_dW"] > 0.65)

    # Root determination
    if n_dW_root >= 3:
        root = "raw_9C_event_pair_geometry"
    elif n_matched_phi_novelty_survives >= 3:
        root = "historical_novelty"
    elif n_matched_h_phi_survives >= 3 and n_phi_beats >= 3:
        root = "phi_stimulus_geometry"
    elif ll_systematic and n_phi_beats >= 2:
        root = "phi_stimulus_geometry_with_LL_special_case"
    elif n_phi_beats >= 3 or n_sur_beats >= 3:
        root = "phi_surprise_driven"
    else:
        root = "inconclusive"

    return {
        "seeds": seeds,
        "ll_inversion_count": ll_inversion_count,
        "ll_systematic_inversion": ll_systematic,
        "rr_novelty_pass_seeds": rr_novelty_pass,
        "rr_inverse_seeds": rr_inverse,
        "rr_split_confirmed": rr_split_confirmed,
        "n_seeds_phi_beats_novelty": n_phi_beats,
        "n_seeds_surprise_beats_novelty": n_sur_beats,
        "n_seeds_matched_phi_novelty_survives": n_matched_phi_novelty_survives,
        "n_seeds_matched_h_phi_survives": n_matched_h_phi_survives,
        "n_seeds_dW_root": n_dW_root,
        "root_likely": root,
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
        description="Phase 10E.1D Subgraph / Phi-Driven Tag Formation Analyzer")
    parser.add_argument(
        "--input-events-csv",
        default="results/phase10E1B_tag_formation_events.csv")
    parser.add_argument(
        "--summary-csv",
        default="results/phase10E1D_subgraph_phi_tag_formation_summary.csv")
    parser.add_argument(
        "--summary-json",
        default="results/phase10E1D_subgraph_phi_tag_formation_summary.json")
    parser.add_argument("--n-bins", type=int, default=N_BINS_DEFAULT)
    parser.add_argument("--n-shuffles", type=int, default=N_SHUFFLES_DEFAULT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--estimate-only", action="store_true")
    args = parser.parse_args()

    import os
    if not os.path.exists(args.input_events_csv):
        print(f"ERROR: events CSV not found: {args.input_events_csv}", file=sys.stderr)
        print("Re-run exp10E1_tag_formation_historical_context_diagnostics.py "
              "--seeds 42 77 123 999 to regenerate.", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"[dry-run] input: {args.input_events_csv}")
        print(f"[dry-run] output csv: {args.summary_csv}")
        print(f"[dry-run] output json: {args.summary_json}")
        print(f"[dry-run] n_bins={args.n_bins}  n_shuffles={args.n_shuffles}")
        print("[dry-run] config OK, exiting.")
        return 0

    if args.estimate_only:
        size_mb = os.path.getsize(args.input_events_csv) / 1e6
        print(f"[estimate] input CSV: {size_mb:.1f} MB")
        print(f"[estimate] n_bins={args.n_bins}  n_shuffles={args.n_shuffles}")
        print("[estimate] ~60-180s depending on CSV size and bin count")
        return 0

    print("Phase 10E.1D Subgraph / Phi-Driven Tag Formation Analyzer")
    print(f"  input: {args.input_events_csv}")
    print(f"  n_bins={args.n_bins}  n_shuffles={args.n_shuffles}")

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

    rng = np.random.default_rng(77777)
    summaries = []
    n_groups = len(groups)
    for i, (key, rows) in enumerate(sorted(groups.items())):
        if (i + 1) % 100 == 0:
            print(f"  [{i+1}/{n_groups}] ...")
        result = _analyze_group(rows, args.n_bins, args.n_shuffles, rng)
        if result is not None:
            entry = _key_to_dict(key)
            entry.update(result)
            summaries.append(entry)

    elapsed = time.time() - t0
    print(f"Analysis done in {elapsed:.1f}s — {len(summaries)} summary rows")

    cross = _cross_seed_verdict(summaries)
    print("\n=== Cross-seed verdict ===")
    for k, v in cross.items():
        print(f"  {k}: {v}")

    print("\n=== Aggregate per seed (closed_loop, ALL etype, ALL subgraph) ===")
    for s in summaries:
        if (s["arm"] == "closed_loop"
                and s["event_type"] == "ALL"
                and s["subgraph"] == "ALL"):
            print(f"  seed={s['seed']}"
                  f"  auc_nv={s['auc_novelty']}"
                  f"  auc_phi={s['auc_phi']}"
                  f"  auc_sur={s['auc_surprise']}"
                  f"  matched_phi_nv={s['matched_phi_novelty_auc']}"
                  f"  matched_h_phi={s['matched_h_phi_auc']}"
                  f"  best={s['best_predictor']}"
                  f"  verdict={s['subgraph_verdict']}")

    print("\n=== LL subgraph (closed_loop, ALL etype) ===")
    for s in summaries:
        if (s["arm"] == "closed_loop"
                and s["event_type"] == "ALL"
                and s["subgraph"] == "LL"):
            print(f"  seed={s['seed']}"
                  f"  h_tag_ratio={s['h_tag_ratio']}"
                  f"  auc_nv={s['auc_novelty']}"
                  f"  auc_phi={s['auc_phi']}"
                  f"  matched_phi_nv={s['matched_phi_novelty_auc']}"
                  f"  verdict={s['subgraph_verdict']}")

    print("\n=== RR subgraph (closed_loop, ALL etype) ===")
    for s in summaries:
        if (s["arm"] == "closed_loop"
                and s["event_type"] == "ALL"
                and s["subgraph"] == "RR"):
            print(f"  seed={s['seed']}"
                  f"  h_tag_ratio={s['h_tag_ratio']}"
                  f"  auc_nv={s['auc_novelty']}"
                  f"  auc_phi={s['auc_phi']}"
                  f"  matched_phi_nv={s['matched_phi_novelty_auc']}"
                  f"  verdict={s['subgraph_verdict']}")

    _save_csv(summaries, args.summary_csv)
    output = {
        "experiment": "phase10E1D_subgraph_phi_tag_formation_diagnostic",
        "git_sha": _git_sha(),
        "timestamp": int(time.time()),
        "input_events_csv": args.input_events_csv,
        "n_bins": args.n_bins,
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
    print(f"\nRoot likely: {cross['root_likely']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
