"""Phase 10F Step 1 — Event-Pair Support Geometry Proxy Audit.

Offline analyzer. Reads existing 10E.1B event-level CSV.
Does NOT re-run simulation and does NOT modify mechanisms.

Important limitation: the 10E.1B CSV stores phi_conn as a proxy. It does not
store true phi[tgt] or trace[src]. This analyzer only audits whether the
recorded phi_conn proxy support approximates event_pair_dW support.
Exact trace[src] × phi[tgt] identity requires a Step 2 capture pass.
"""

import argparse, csv, json, sys, time
from collections import defaultdict
import numpy as np


DEFAULT_EPS = 1e-12
REQUIRED_COLUMNS = {
    "seed", "arm", "event_type", "subgraph", "src_region", "tgt_region",
    "phi_conn", "event_pair_dW", "tag_presence", "tag_strength", "tag_delta",
    "h_conn", "h_norm_conn", "novelty_factor", "surprise_factor",
    "baseline_weight_abs",
}


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _r(v):
    if isinstance(v, float) and np.isnan(v):
        return "nan"
    if isinstance(v, float):
        return round(v, 6)
    return v


def _corr(x, y):
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if len(x) < 2:
        return float("nan")
    if float(np.std(x)) < 1e-12 or float(np.std(y)) < 1e-12:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def _safe_ratio(a, b):
    if b <= 1e-12:
        return float("nan")
    return float(a / b)


def _git_sha():
    import subprocess
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


# ═══════════════════════════════════════════════════════════════════
# Load rows
# ═══════════════════════════════════════════════════════════════════

def _read_fieldnames(path):
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames or []


def _load_rows(path):
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
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
                "phi_conn": float(row["phi_conn"]),
                "event_pair_dW": float(row["event_pair_dW"]),
                "tag_presence": int(row["tag_presence"]),
                "tag_strength": float(row["tag_strength"]),
                "tag_delta": float(row["tag_delta"]),
                "h_conn": float(row["h_conn"]),
                "h_norm_conn": float(row["h_norm_conn"]),
                "novelty_factor": float(row["novelty_factor"]),
                "surprise_factor": float(row["surprise_factor"]),
                "baseline_weight_abs": float(row["baseline_weight_abs"]),
            })
    return rows


# ═══════════════════════════════════════════════════════════════════
# Group analysis
# ═══════════════════════════════════════════════════════════════════

def _build_groups(rows):
    groups = defaultdict(list)
    for r in rows:
        seed, arm = r["seed"], r["arm"]
        etype, sg = r["event_type"], r["subgraph"]
        groups[(seed, arm, "ALL", "ALL")].append(r)
        groups[(seed, arm, etype, "ALL")].append(r)
        groups[(seed, arm, "ALL", sg)].append(r)
        groups[(seed, arm, etype, sg)].append(r)
    return groups


def _analyze_group(key, rows, eps):
    seed, arm, etype, sg = key
    n = len(rows)
    phi = np.array([r["phi_conn"] for r in rows], dtype=np.float64)
    h = np.array([r["h_conn"] for r in rows], dtype=np.float64)
    dW = np.array([r["event_pair_dW"] for r in rows], dtype=np.float64)
    tag_delta = np.array([r["tag_delta"] for r in rows], dtype=np.float64)
    tag_presence = np.array([r["tag_presence"] for r in rows], dtype=np.int8)

    dW_support = np.abs(dW) > eps
    tag_support = (tag_presence == 1) | (np.abs(tag_delta) > eps)
    phi_support = phi > eps

    dW_n = int(np.sum(dW_support))
    tag_n = int(np.sum(tag_support))
    phi_n = int(np.sum(phi_support))

    phi_match = phi_support == dW_support
    tag_match = tag_support == dW_support
    fp = phi_support & ~dW_support
    fn = ~phi_support & dW_support

    dW_supported = dW_support
    dW_unsupported = ~dW_support
    mean_phi_supported = float(np.mean(phi[dW_supported])) if dW_supported.any() else float("nan")
    mean_phi_unsupported = float(np.mean(phi[dW_unsupported])) if dW_unsupported.any() else float("nan")
    mean_h_supported = float(np.mean(h[dW_supported])) if dW_supported.any() else float("nan")
    mean_h_unsupported = float(np.mean(h[dW_unsupported])) if dW_unsupported.any() else float("nan")

    verdict = _group_verdict(float(np.mean(phi_match)), float(np.mean(tag_match)))

    return {
        "seed": seed,
        "arm": arm,
        "event_type": etype,
        "subgraph": sg,
        "n_connections": n,
        "dW_support_rate": _r(dW_n / n),
        "tag_support_rate": _r(tag_n / n),
        "phi_proxy_positive_rate": _r(phi_n / n),
        "phi_proxy_dW_match_rate": _r(float(np.mean(phi_match))),
        "phi_proxy_false_positive_rate": _r(int(np.sum(fp)) / n),
        "phi_proxy_false_negative_rate": _r(int(np.sum(fn)) / n),
        "tag_dW_match_rate": _r(float(np.mean(tag_match))),
        "dW_l1": _r(float(np.sum(np.abs(dW)))),
        "tag_delta_l1": _r(float(np.sum(np.abs(tag_delta)))),
        "mean_phi_dW_supported": _r(mean_phi_supported),
        "mean_phi_dW_unsupported": _r(mean_phi_unsupported),
        "mean_h_dW_supported": _r(mean_h_supported),
        "mean_h_dW_unsupported": _r(mean_h_unsupported),
        "h_support_ratio": _r(_safe_ratio(mean_h_supported, mean_h_unsupported)),
        "phi_support_ratio": _r(_safe_ratio(mean_phi_supported, mean_phi_unsupported)),
        "corr_h_dW_support": _r(_corr(h, dW_support.astype(np.float64))),
        "corr_phi_dW_support": _r(_corr(phi, dW_support.astype(np.float64))),
        "support_geometry_verdict": verdict,
    }


def _group_verdict(phi_match_rate, tag_match_rate):
    if tag_match_rate < 0.99:
        return "tag_dW_mismatch"
    if phi_match_rate > 0.99:
        return "proxy_phi_support_matches_dW_support"
    return "proxy_phi_support_insufficient"


# ═══════════════════════════════════════════════════════════════════
# Cross-seed summary
# ═══════════════════════════════════════════════════════════════════

def _aggregate_match(rows, eps):
    phi = np.array([r["phi_conn"] for r in rows], dtype=np.float64)
    dW = np.array([r["event_pair_dW"] for r in rows], dtype=np.float64)
    tag_delta = np.array([r["tag_delta"] for r in rows], dtype=np.float64)
    tag_presence = np.array([r["tag_presence"] for r in rows], dtype=np.int8)
    dW_support = np.abs(dW) > eps
    tag_support = (tag_presence == 1) | (np.abs(tag_delta) > eps)
    phi_support = phi > eps
    fp = phi_support & ~dW_support
    fn = ~phi_support & dW_support
    return {
        "n": len(rows),
        "phi_proxy_match_rate": float(np.mean(phi_support == dW_support)),
        "tag_dW_match_rate": float(np.mean(tag_support == dW_support)),
        "phi_proxy_positive_rate": float(np.mean(phi_support)),
        "dW_support_rate": float(np.mean(dW_support)),
        "phi_proxy_false_positive_rate": float(np.mean(fp)),
        "phi_proxy_false_negative_rate": float(np.mean(fn)),
        "phi_mean": float(np.mean(phi)),
        "phi_mass": float(np.sum(np.abs(phi))),
    }


def _cross_seed_summary(rows, summaries, fieldnames, eps):
    exact_phi_tgt_available = "phi_tgt" in fieldnames
    trace_src_available = "trace_src" in fieldnames

    all_stats = _aggregate_match(rows, eps)

    by_seed = {}
    by_event_type = {}
    closed_loop_by_seed_event = defaultdict(list)

    for seed in sorted(set(r["seed"] for r in rows)):
        seed_rows = [r for r in rows if r["seed"] == seed]
        by_seed[str(seed)] = {k: _r(v) for k, v in _aggregate_match(seed_rows, eps).items()}

    for etype in sorted(set(r["event_type"] for r in rows)):
        etype_rows = [r for r in rows if r["event_type"] == etype]
        by_event_type[etype] = {k: _r(v) for k, v in _aggregate_match(etype_rows, eps).items()}

    for r in rows:
        if r["arm"] == "closed_loop":
            closed_loop_by_seed_event[(r["seed"], r["event_type"])].append(r)

    # L vs R phi proxy coverage per seed, closed_loop only.
    l_vs_r = {}
    for seed in sorted(set(r["seed"] for r in rows)):
        l_rows = closed_loop_by_seed_event.get((seed, "L"), [])
        r_rows = closed_loop_by_seed_event.get((seed, "R"), [])
        l_stats = _aggregate_match(l_rows, eps) if l_rows else None
        r_stats = _aggregate_match(r_rows, eps) if r_rows else None
        l_vs_r[str(seed)] = {
            "L_phi_proxy_positive_rate": _r(l_stats["phi_proxy_positive_rate"]) if l_stats else "nan",
            "R_phi_proxy_positive_rate": _r(r_stats["phi_proxy_positive_rate"]) if r_stats else "nan",
            "R_minus_L_phi_proxy_positive_rate": _r(
                r_stats["phi_proxy_positive_rate"] - l_stats["phi_proxy_positive_rate"]
            ) if l_stats and r_stats else "nan",
            "L_phi_mass": _r(l_stats["phi_mass"]) if l_stats else "nan",
            "R_phi_mass": _r(r_stats["phi_mass"]) if r_stats else "nan",
            "R_over_L_phi_mass": _r(_safe_ratio(r_stats["phi_mass"], l_stats["phi_mass"]))
            if l_stats and r_stats else "nan",
        }

    # Seed family comparison: seed42/77 vs seed123/999, closed_loop aggregate.
    family_a = [r for r in rows if r["arm"] == "closed_loop" and r["seed"] in (42, 77)]
    family_b = [r for r in rows if r["arm"] == "closed_loop" and r["seed"] in (123, 999)]
    fam_a_stats = _aggregate_match(family_a, eps)
    fam_b_stats = _aggregate_match(family_b, eps)
    family_compare = {
        "seed42_77_phi_proxy_positive_rate": _r(fam_a_stats["phi_proxy_positive_rate"]),
        "seed123_999_phi_proxy_positive_rate": _r(fam_b_stats["phi_proxy_positive_rate"]),
        "seed123_999_minus_42_77_phi_proxy_positive_rate": _r(
            fam_b_stats["phi_proxy_positive_rate"] - fam_a_stats["phi_proxy_positive_rate"]),
        "seed42_77_phi_mean": _r(fam_a_stats["phi_mean"]),
        "seed123_999_phi_mean": _r(fam_b_stats["phi_mean"]),
        "seed42_77_phi_mass": _r(fam_a_stats["phi_mass"]),
        "seed123_999_phi_mass": _r(fam_b_stats["phi_mass"]),
    }

    step2_required = True
    if all_stats["phi_proxy_match_rate"] <= 0.99:
        final = "proxy_phi_support_insufficient"
    else:
        final = "proxy_phi_support_matches_dW_support"

    # Step 2 remains required unless exact fields already exist in the CSV.
    if exact_phi_tgt_available and trace_src_available:
        step2_required = False

    return {
        "all_phi_proxy_match_rate": _r(all_stats["phi_proxy_match_rate"]),
        "all_tag_dW_match_rate": _r(all_stats["tag_dW_match_rate"]),
        "all_phi_proxy_false_positive_rate": _r(all_stats["phi_proxy_false_positive_rate"]),
        "all_phi_proxy_false_negative_rate": _r(all_stats["phi_proxy_false_negative_rate"]),
        "by_seed_phi_proxy_match_rate": {
            seed: stats["phi_proxy_match_rate"] for seed, stats in by_seed.items()
        },
        "by_event_type_phi_proxy_match_rate": {
            etype: stats["phi_proxy_match_rate"] for etype, stats in by_event_type.items()
        },
        "R_event_phi_proxy_rate_vs_L": l_vs_r,
        "seed123_999_phi_proxy_distribution_vs_42_77": family_compare,
        "exact_phi_tgt_available": exact_phi_tgt_available,
        "trace_src_available": trace_src_available,
        "step2_required": step2_required,
        "final_verdict": final,
        "interpretation_guardrail": (
            "This is proxy evidence only: phi_conn is not confirmed true phi[tgt]. "
            "Exact trace[src] x phi[tgt] support requires Step 2 if trace_src/phi_tgt are absent."
        ),
    }


# ═══════════════════════════════════════════════════════════════════
# Save / main
# ═══════════════════════════════════════════════════════════════════

def _save_csv(rows, path):
    if not rows:
        return
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(
        description="Phase 10F Step 1 support geometry proxy audit")
    parser.add_argument(
        "--input-events-csv",
        default="results/phase10E1B_tag_formation_events.csv")
    parser.add_argument(
        "--summary-csv",
        default="results/phase10F_support_geometry_summary.csv")
    parser.add_argument(
        "--summary-json",
        default="results/phase10F_support_geometry_summary.json")
    parser.add_argument("--eps", type=float, default=DEFAULT_EPS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--estimate-only", action="store_true")
    args = parser.parse_args()

    import os
    if not os.path.exists(args.input_events_csv):
        print(f"ERROR: events CSV not found: {args.input_events_csv}", file=sys.stderr)
        print("Regenerate the 10E.1B events CSV before running this analyzer.", file=sys.stderr)
        return 1

    fieldnames = _read_fieldnames(args.input_events_csv)
    missing = REQUIRED_COLUMNS - set(fieldnames)
    if missing:
        print(f"ERROR: missing required columns: {sorted(missing)}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"[dry-run] input: {args.input_events_csv}")
        print(f"[dry-run] output csv: {args.summary_csv}")
        print(f"[dry-run] output json: {args.summary_json}")
        print(f"[dry-run] eps={args.eps}")
        print(f"[dry-run] exact_phi_tgt_available={'phi_tgt' in fieldnames}")
        print(f"[dry-run] trace_src_available={'trace_src' in fieldnames}")
        print("[dry-run] config OK, exiting.")
        return 0

    if args.estimate_only:
        size_mb = os.path.getsize(args.input_events_csv) / 1e6
        print(f"[estimate] input CSV: {size_mb:.1f} MB")
        print("[estimate] streaming/read-only CSV aggregation, expected <30s locally")
        return 0

    print("Phase 10F Step 1 — Support Geometry Proxy Audit")
    print(f"  input: {args.input_events_csv}")
    print(f"  eps={args.eps}")
    print(f"  exact_phi_tgt_available={'phi_tgt' in fieldnames}")
    print(f"  trace_src_available={'trace_src' in fieldnames}")

    t0 = time.time()
    print("Loading events CSV ...")
    rows = _load_rows(args.input_events_csv)
    print(f"  loaded {len(rows):,} rows in {time.time() - t0:.1f}s")

    print("Building groups ...")
    groups = _build_groups(rows)
    print(f"  {len(groups)} groups")

    summaries = []
    for key, group_rows in sorted(groups.items()):
        summaries.append(_analyze_group(key, group_rows, args.eps))

    cross = _cross_seed_summary(rows, summaries, fieldnames, args.eps)

    print("\n=== Cross-seed proxy verdict ===")
    for k in [
        "final_verdict", "all_tag_dW_match_rate", "all_phi_proxy_match_rate",
        "all_phi_proxy_false_positive_rate", "all_phi_proxy_false_negative_rate",
        "exact_phi_tgt_available", "trace_src_available", "step2_required",
    ]:
        print(f"  {k}: {cross[k]}")

    print("\n=== L vs R phi proxy coverage (closed_loop) ===")
    for seed, stats in cross["R_event_phi_proxy_rate_vs_L"].items():
        print(f"  seed={seed}"
              f"  L_rate={stats['L_phi_proxy_positive_rate']}"
              f"  R_rate={stats['R_phi_proxy_positive_rate']}"
              f"  R-L={stats['R_minus_L_phi_proxy_positive_rate']}"
              f"  R/L_phi_mass={stats['R_over_L_phi_mass']}")

    print("\n=== Seed family phi proxy comparison (closed_loop) ===")
    for k, v in cross["seed123_999_phi_proxy_distribution_vs_42_77"].items():
        print(f"  {k}: {v}")

    _save_csv(summaries, args.summary_csv)
    output = {
        "experiment": "phase10F_support_geometry_proxy_audit",
        "git_sha": _git_sha(),
        "timestamp": int(time.time()),
        "input_events_csv": args.input_events_csv,
        "eps": args.eps,
        "n_rows_loaded": len(rows),
        "n_summary_rows": len(summaries),
        "fieldnames": fieldnames,
        "cross_seed": cross,
        "summaries": summaries,
    }
    with open(args.summary_json, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nSaved: {args.summary_csv}")
    print(f"Saved: {args.summary_json}")
    print(f"\nFinal verdict: {cross['final_verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
