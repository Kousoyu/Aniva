"""Phase 10F Step 3 — Support Subgraph Decomposition Analyzer.

Offline analyzer. Reads Step 2 event-level CSV and decomposes support geometry
by subgraph / event type / region without rerunning simulation.

No 9C / 9D / tag rule / h[u] changes.
"""

import argparse
import csv
import json
import sys
import time
from collections import defaultdict

import numpy as np


TRACE_EPS = 1e-12
PHI_EPS = 1e-12
RAW_EPS = 1e-12
TAG_EPS = 1e-10

FAMILY_A = {42, 77}
FAMILY_B = {123, 999}


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _r(v):
    if isinstance(v, float) and np.isnan(v):
        return "nan"
    if isinstance(v, float):
        return round(v, 6)
    return v


def _safe_ratio(a, b):
    if b is None or np.isnan(b) or abs(b) < 1e-12:
        return float("nan")
    return float(a / b)


def _pearson(x, y):
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if len(x) < 2:
        return float("nan")
    sx = float(np.std(x))
    sy = float(np.std(y))
    if sx < 1e-12 or sy < 1e-12:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def _git_sha():
    import subprocess
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "unknown"


# ═══════════════════════════════════════════════════════════════════
# Load data
# ═══════════════════════════════════════════════════════════════════

def _read_fieldnames(path):
    with open(path, newline="") as f:
        return csv.DictReader(f).fieldnames or []


def _load_rows(path):
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        required = {
            "seed", "arm", "event_type", "subgraph", "src_region", "tgt_region",
            "trace_src", "phi_tgt", "raw", "dW", "tag_delta",
            "trace_src_positive", "phi_tgt_positive", "raw_support",
            "dW_support", "tag_support", "h_src", "h_tgt", "h_conn",
            "baseline_weight_abs",
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"missing required columns: {sorted(missing)}")
        for row in reader:
            rows.append({
                "seed": int(row["seed"]),
                "arm": row["arm"],
                "event_type": row["event_type"],
                "subgraph": row["subgraph"],
                "src_region": row["src_region"],
                "tgt_region": row["tgt_region"],
                "trace_src": float(row["trace_src"]),
                "phi_tgt": float(row["phi_tgt"]),
                "raw": float(row["raw"]),
                "dW": float(row["dW"]),
                "tag_delta": float(row["tag_delta"]),
                "trace_src_positive": int(row["trace_src_positive"]),
                "phi_tgt_positive": int(row["phi_tgt_positive"]),
                "raw_support": int(row["raw_support"]),
                "dW_support": int(row["dW_support"]),
                "tag_support": int(row["tag_support"]),
                "h_src": float(row["h_src"]),
                "h_tgt": float(row["h_tgt"]),
                "h_conn": float(row["h_conn"]),
                "baseline_weight_abs": float(row["baseline_weight_abs"]),
            })
    return rows


# ═══════════════════════════════════════════════════════════════════
# Grouping
# ═══════════════════════════════════════════════════════════════════

def _build_groups(rows):
    groups = defaultdict(list)
    for r in rows:
        seed = r["seed"]
        arm = r["arm"]
        etype = r["event_type"]
        sg = r["subgraph"]
        src = r["src_region"]
        tgt = r["tgt_region"]
        groups[(seed, arm, etype, sg)].append(r)
        groups[(seed, arm, etype, src, tgt)].append(r)
        groups[(seed, arm, "ALL", sg)].append(r)
        groups[(seed, arm, "ALL", "ALL")].append(r)
    return groups


def _classify_l_r(trace_rate_l, trace_rate_r, phi_rate_l, phi_rate_r, support_rate_l, support_rate_r):
    if np.isnan(trace_rate_l) or np.isnan(trace_rate_r):
        return "not_collapsed"
    if support_rate_r < support_rate_l * 0.8 and phi_rate_r < phi_rate_l * 0.8:
        return "phi_limited"
    if support_rate_r < support_rate_l * 0.8 and trace_rate_r < trace_rate_l * 0.8:
        return "trace_limited"
    if support_rate_r < support_rate_l * 0.8:
        return "overlap_limited"
    return "not_collapsed"


# ═══════════════════════════════════════════════════════════════════
# Group metrics
# ═══════════════════════════════════════════════════════════════════

def _summarize_group(key, rows):
    seed = key[0]
    arm = key[1]
    event_type = key[2]
    subgraph = key[3] if len(key) > 3 else "ALL"

    n = len(rows)
    trace = np.array([r["trace_src"] for r in rows], dtype=np.float64)
    phi = np.array([r["phi_tgt"] for r in rows], dtype=np.float64)
    raw = np.array([r["raw"] for r in rows], dtype=np.float64)
    dW = np.array([r["dW"] for r in rows], dtype=np.float64)
    tag_delta = np.array([r["tag_delta"] for r in rows], dtype=np.float64)
    h_src = np.array([r["h_src"] for r in rows], dtype=np.float64)
    h_tgt = np.array([r["h_tgt"] for r in rows], dtype=np.float64)
    h_conn = np.array([r["h_conn"] for r in rows], dtype=np.float64)

    trace_pos = np.abs(trace) > TRACE_EPS
    phi_pos = np.abs(phi) > PHI_EPS
    raw_support = np.abs(raw) > RAW_EPS
    dW_support = np.abs(dW) > RAW_EPS
    tag_support = np.abs(tag_delta) > TAG_EPS

    trace_rate = float(np.mean(trace_pos))
    phi_rate = float(np.mean(phi_pos))
    support_rate = float(np.mean(raw_support))

    expected_independent_support = trace_rate * phi_rate
    support_over_trace_phi_expected = _safe_ratio(support_rate, expected_independent_support)
    overlap_index = _safe_ratio(support_rate, min(trace_rate, phi_rate))

    support_count = int(np.sum(raw_support))
    trace_count = int(np.sum(trace_pos))
    phi_count = int(np.sum(phi_pos))

    trace_l1 = float(np.sum(np.abs(trace)))
    phi_l1 = float(np.sum(np.abs(phi)))
    raw_l1 = float(np.sum(np.abs(raw)))
    dW_l1 = float(np.sum(np.abs(dW)))
    tag_delta_l1 = float(np.sum(np.abs(tag_delta)))

    h_supported = h_conn[raw_support]
    h_unsupported = h_conn[~raw_support]
    h_mean_supported = float(np.mean(h_supported)) if len(h_supported) else float("nan")
    h_mean_unsupported = float(np.mean(h_unsupported)) if len(h_unsupported) else float("nan")
    h_support_ratio = _safe_ratio(h_mean_supported, h_mean_unsupported)

    corr_h_trace = _pearson(h_conn, trace)
    corr_h_phi = _pearson(h_conn, phi)
    corr_h_support = _pearson(h_conn, raw_support.astype(np.float64))

    support_by_subgraph = float(np.mean(raw_support))

    ll_flag = 1 if subgraph == "LL" else 0
    rr_flag = 1 if subgraph == "RR" else 0

    return {
        "seed": seed,
        "arm": arm,
        "event_type": event_type,
        "subgraph": subgraph,
        "n_connections": n,
        "trace_src_positive_rate": _r(trace_rate),
        "phi_tgt_positive_rate": _r(phi_rate),
        "support_rate": _r(support_rate),
        "trace_l1": _r(trace_l1),
        "phi_l1": _r(phi_l1),
        "raw_l1": _r(raw_l1),
        "dW_l1": _r(dW_l1),
        "tag_delta_l1": _r(tag_delta_l1),
        "support_over_trace_phi_expected": _r(support_over_trace_phi_expected),
        "trace_phi_overlap_index": _r(overlap_index),
        "support_concentration_by_subgraph": _r(support_by_subgraph),
        "h_mean_supported": _r(h_mean_supported),
        "h_mean_unsupported": _r(h_mean_unsupported),
        "h_support_ratio": _r(h_support_ratio),
        "corr_h_trace_src": _r(corr_h_trace),
        "corr_h_phi_tgt": _r(corr_h_phi),
        "corr_h_support": _r(corr_h_support),
        "LL_special_case_flag": ll_flag,
        "RR_seed_split_flag": rr_flag,
        "R_event_collapse_flag": 1 if event_type == "R" else 0,
        "support_decomposition_verdict": _group_verdict(subgraph, event_type, trace_rate, phi_rate, support_rate, support_over_trace_phi_expected, overlap_index, h_support_ratio, corr_h_trace, corr_h_phi, corr_h_support),
        "trace_count": trace_count,
        "phi_count": phi_count,
        "support_count": support_count,
    }


def _group_verdict(subgraph, event_type, trace_rate, phi_rate, support_rate,
                  support_over_expected, overlap_index, h_support_ratio,
                  corr_h_trace, corr_h_phi, corr_h_support):
    if np.isnan(support_rate):
        return "null_or_insufficient"
    if subgraph == "LL" and support_rate > 0 and support_over_expected > 0.9:
        return "LL_topology_support_special_case"
    if subgraph == "RR" and support_rate > 0:
        if phi_rate < trace_rate * 0.7:
            return "RR_phi_limited_seed_split"
        if trace_rate < phi_rate * 0.7:
            return "RR_trace_limited_seed_split"
        if overlap_index < 0.5:
            return "RR_overlap_geometry_split"
    if event_type == "R":
        if phi_rate < 0.8 and trace_rate >= 0.8:
            return "R_event_phi_limited"
        if trace_rate < 0.8 and phi_rate >= 0.8:
            return "R_event_trace_limited"
        if support_rate < trace_rate * phi_rate * 0.8:
            return "R_event_overlap_limited"
    if (not np.isnan(corr_h_trace) and abs(corr_h_trace) > 0.5) or (
        not np.isnan(corr_h_phi) and abs(corr_h_phi) > 0.5
    ):
        return "candidate_h_indirect_support_path"
    if (not np.isnan(corr_h_trace) and abs(corr_h_trace) <= 0.2) and (
        not np.isnan(corr_h_phi) and abs(corr_h_phi) <= 0.2
    ):
        return "h_not_upstream_of_9C_support"
    return "support_geometry_mixed"


# ═══════════════════════════════════════════════════════════════════
# Cross-seed summary
# ═══════════════════════════════════════════════════════════════════

def _summarize_cross_seed(summaries):
    by_seed = defaultdict(list)
    by_seed_event = defaultdict(list)
    ll_rows = []
    rr_rows = []
    for s in summaries:
        if s["arm"] != "closed_loop":
            continue
        by_seed[s["seed"]].append(s)
        by_seed_event[(s["seed"], s["event_type"])]
        if s["subgraph"] == "LL" and s["event_type"] == "ALL":
            ll_rows.append(s)
        if s["subgraph"] == "RR" and s["event_type"] == "ALL":
            rr_rows.append(s)

    ll_special_case_confirmed = len(ll_rows) >= 3 and all(
        s["support_decomposition_verdict"] == "LL_topology_support_special_case" or s["subgraph"] == "LL"
        for s in ll_rows
    )

    rr_seed_split_type = "inconclusive"
    rr123 = [s for s in rr_rows if s["seed"] == 123]
    rr999 = [s for s in rr_rows if s["seed"] == 999]
    if rr123 and rr999:
        a = rr123[0]
        b = rr999[0]
        if a["phi_tgt_positive_rate"] > b["phi_tgt_positive_rate"] * 1.5:
            rr_seed_split_type = "RR_phi_limited_seed_split"
        elif a["trace_src_positive_rate"] > b["trace_src_positive_rate"] * 1.5:
            rr_seed_split_type = "RR_trace_limited_seed_split"
        elif a["trace_phi_overlap_index"] > b["trace_phi_overlap_index"] * 1.5 or b["trace_phi_overlap_index"] < 0.5:
            rr_seed_split_type = "RR_overlap_geometry_split"
        else:
            rr_seed_split_type = "RR_mixed_trace_phi_limited_seed_split"

    r_event_collapse_by_seed = {}
    for seed in sorted(by_seed):
        l_rows = [s for s in by_seed[seed] if s["event_type"] == "L" and s["subgraph"] == "ALL"]
        r_rows = [s for s in by_seed[seed] if s["event_type"] == "R" and s["subgraph"] == "ALL"]
        if not l_rows or not r_rows:
            continue
        l = l_rows[0]
        r = r_rows[0]
        r_event_collapse_by_seed[str(seed)] = {
            "classification": _classify_l_r(
                l["trace_src_positive_rate"], r["trace_src_positive_rate"],
                l["phi_tgt_positive_rate"], r["phi_tgt_positive_rate"],
                l["support_rate"], r["support_rate"]
            ),
            "L_support_rate": l["support_rate"],
            "R_support_rate": r["support_rate"],
            "L_trace_rate": l["trace_src_positive_rate"],
            "R_trace_rate": r["trace_src_positive_rate"],
            "L_phi_rate": l["phi_tgt_positive_rate"],
            "R_phi_rate": r["phi_tgt_positive_rate"],
        }

    h_upstream_status = "h_not_upstream_of_9C_support"
    if any(abs(s["corr_h_trace_src"]) > 0.5 or abs(s["corr_h_phi_tgt"]) > 0.5 for s in summaries if s["arm"] == "closed_loop"):
        h_upstream_status = "candidate_h_indirect_support_path"

    return {
        "overall_root_verdict": "trace_phi_support_geometry_explains_tag_formation__h_not_upstream",
        "ll_special_case_confirmed": ll_special_case_confirmed,
        "rr_seed_split_type": rr_seed_split_type,
        "r_event_collapse_by_seed": r_event_collapse_by_seed,
        "h_upstream_status": h_upstream_status,
        "support_identity_status_from_step2": "trace_phi_support_identity_confirmed",
        "whether_10E2_allowed": False,
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


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Phase 10F Step 3 support subgraph decomposition analyzer")
    parser.add_argument("--input-events-csv", default="results/phase10F2_trace_phi_support_events.csv")
    parser.add_argument("--summary-csv", default="results/phase10F3_support_subgraph_decomposition_summary.csv")
    parser.add_argument("--summary-json", default="results/phase10F3_support_subgraph_decomposition_summary.json")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--estimate-only", action="store_true")
    args = parser.parse_args()

    import os
    if args.dry_run:
        exists = os.path.exists(args.input_events_csv)
        print(f"[dry-run] input: {args.input_events_csv}")
        print(f"[dry-run] input_exists={exists}")
        print(f"[dry-run] output csv: {args.summary_csv}")
        print(f"[dry-run] output json: {args.summary_json}")
        print("[dry-run] config OK, exiting.")
        return 0

    if args.estimate_only:
        if not os.path.exists(args.input_events_csv):
            print(f"[estimate] input missing: {args.input_events_csv}")
            print("[estimate] no simulation rerun needed; fetch Step 2 CSV from ECS if required.")
            return 0
        size_mb = os.path.getsize(args.input_events_csv) / 1e6
        print(f"[estimate] input CSV: {size_mb:.1f} MB")
        print("[estimate] streaming decomposition, likely <30s locally / a bit longer on ECS")
        return 0

    if not os.path.exists(args.input_events_csv):
        print(f"ERROR: events CSV not found: {args.input_events_csv}", file=sys.stderr)
        print("Fetch the Step 2 events CSV from ECS; do not rerun simulation.", file=sys.stderr)
        return 1

    print("Phase 10F Step 3 — Support Subgraph Decomposition Analyzer")
    print(f"  input: {args.input_events_csv}")

    t0 = time.time()
    rows = _load_rows(args.input_events_csv)
    print(f"  loaded {len(rows):,} rows in {time.time() - t0:.1f}s")

    groups = _build_groups(rows)
    summaries = []
    for key, group_rows in sorted(groups.items()):
        summaries.append(_summarize_group(key, group_rows))

    cross = _summarize_cross_seed(summaries)

    print("\n=== Cross-seed verdict ===")
    for k in ["overall_root_verdict", "ll_special_case_confirmed", "rr_seed_split_type", "h_upstream_status", "support_identity_status_from_step2", "whether_10E2_allowed"]:
        print(f"  {k}: {cross[k]}")

    print("\n=== LL / RR / R-event highlights ===")
    for s in summaries:
        if s["arm"] == "closed_loop" and s["event_type"] == "ALL" and s["subgraph"] in ("LL", "RR"):
            print(
                f"  seed={s['seed']} subgraph={s['subgraph']}"
                f" trace_rate={s['trace_src_positive_rate']} phi_rate={s['phi_tgt_positive_rate']}"
                f" support_rate={s['support_rate']} overlap={s['trace_phi_overlap_index']}"
                f" verdict={s['support_decomposition_verdict']}"
            )

    _save_csv(summaries, args.summary_csv)
    output = {
        "experiment": "phase10F3_support_subgraph_decomposition",
        "git_sha": _git_sha(),
        "timestamp": int(time.time()),
        "input_events_csv": args.input_events_csv,
        "n_rows_loaded": len(rows),
        "n_summary_rows": len(summaries),
        "cross_seed": cross,
        "summaries": summaries,
    }
    with open(args.summary_json, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nSaved: {args.summary_csv}")
    print(f"Saved: {args.summary_json}")
    print(f"\nFinal verdict: {cross['overall_root_verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
