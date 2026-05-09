"""Phase 7.5: Topology Sensitivity Analysis.

分析 Phase 7.4 的 11 seed 初始网络拓扑特征与
history-dependent structural divergence (delta_weight_l1) 的相关性。

不修改 LifeCore / plasticity / exp5 核心机制。
"""

import argparse
import csv
import json
import sys
import numpy as np

from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.environment.environment import Stimulus

# 与 exp5 一致的刺激定义
L_STIM = Stimulus(position=(-0.5, 0.0, 0.0), intensity=0.03, radius=0.5)
R_STIM = Stimulus(position=(0.5, 0.0, 0.0), intensity=0.03, radius=0.5)


def _pearson_r(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def compute_topology_features(core: LifeCore) -> dict:
    n = core.config.unit_count
    weights = np.array([c.weight for c in core.connections])
    abs_weights = np.abs(weights)
    n_conn = len(weights)

    features = {
        "connection_count": n_conn,
        "weight_abs_mean": float(np.mean(abs_weights)),
        "weight_std": float(np.std(weights)),
    }

    # E/I 比例
    exc_count = int(np.sum(weights > 0))
    inh_count = int(np.sum(weights < 0))
    features["excitatory_ratio"] = exc_count / n_conn if n_conn > 0 else 0.0
    features["inhibitory_ratio"] = inh_count / n_conn if n_conn > 0 else 0.0

    # 出入度分布
    in_degree = np.zeros(n, dtype=int)
    out_degree = np.zeros(n, dtype=int)
    for conn in core.connections:
        out_degree[conn.source_id] += 1
        in_degree[conn.target_id] += 1

    features["in_degree_mean"] = float(np.mean(in_degree))
    features["in_degree_std"] = float(np.std(in_degree))
    features["in_degree_max"] = int(np.max(in_degree))
    features["out_degree_mean"] = float(np.mean(out_degree))
    features["out_degree_std"] = float(np.std(out_degree))
    features["out_degree_max"] = int(np.max(out_degree))

    # 空间不对称性
    positions = core._positions
    left_mask = positions[:, 0] < 0
    right_mask = positions[:, 0] > 0
    left_count = int(np.sum(left_mask))
    right_count = int(np.sum(right_mask))
    features["left_unit_count"] = left_count
    features["right_unit_count"] = right_count
    features["spatial_x_mean"] = float(np.mean(positions[:, 0]))
    features["spatial_x_std"] = float(np.std(positions[:, 0]))
    features["spatial_y_mean"] = float(np.mean(positions[:, 1]))
    features["spatial_y_std"] = float(np.std(positions[:, 1]))
    features["spatial_z_mean"] = float(np.mean(positions[:, 2]))
    features["spatial_z_std"] = float(np.std(positions[:, 2]))

    # L/R 刺激影响单元
    l_affected = set()
    r_affected = set()
    for uid in range(n):
        pos = tuple(positions[uid])
        if L_STIM.influence_at(pos) > 0:
            l_affected.add(uid)
        if R_STIM.influence_at(pos) > 0:
            r_affected.add(uid)

    features["L_affected_count"] = len(l_affected)
    features["R_affected_count"] = len(r_affected)
    features["LR_overlap_count"] = len(l_affected & r_affected)

    # L<->R 区域间连接强度
    l_to_r_weights = []
    r_to_l_weights = []
    for conn in core.connections:
        if conn.source_id in l_affected and conn.target_id in r_affected:
            l_to_r_weights.append(abs(conn.weight))
        if conn.source_id in r_affected and conn.target_id in l_affected:
            r_to_l_weights.append(abs(conn.weight))

    features["L_to_R_abs_weight_mean"] = (
        float(np.mean(l_to_r_weights)) if l_to_r_weights else 0.0
    )
    features["R_to_L_abs_weight_mean"] = (
        float(np.mean(r_to_l_weights)) if r_to_l_weights else 0.0
    )
    features["L_to_R_connection_count"] = len(l_to_r_weights)
    features["R_to_L_connection_count"] = len(r_to_l_weights)

    # 阈值和时间常数分布
    features["threshold_mean"] = float(np.mean(core._thresholds))
    features["threshold_std"] = float(np.std(core._thresholds))
    features["time_constant_mean"] = float(np.mean(core._time_constants))
    features["time_constant_std"] = float(np.std(core._time_constants))

    return features


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Phase 7.5: Topology Sensitivity Analysis"
    )
    parser.add_argument(
        "--summary-json",
        default="results/phase7_multiseed_120k_summary.json",
    )
    parser.add_argument(
        "--output-csv",
        default="results/phase7_topology_sensitivity.csv",
    )
    parser.add_argument(
        "--correlation-csv",
        default="results/phase7_topology_correlations.csv",
    )
    args = parser.parse_args(argv)

    with open(args.summary_json, encoding="utf-8") as f:
        data = json.load(f)

    per_seed = data["per_seed"]

    rows = []
    for entry in per_seed:
        seed = entry["seed"]
        delta = entry["verdict"]["delta_weight_l1"]

        cfg = AnivaConfig(seed=seed, unit_count=entry["unit_count"])
        core = LifeCore(cfg)

        features = compute_topology_features(core)
        features["seed"] = seed
        features["delta_weight_l1"] = delta
        rows.append(features)

    fieldnames = list(rows[0].keys())
    with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {len(rows)} rows to {args.output_csv}")

    # 相关性计算
    delta_values = np.array([r["delta_weight_l1"] for r in rows])
    correlations = []

    for key in fieldnames:
        if key in ("seed", "delta_weight_l1"):
            continue
        values = np.array([r[key] for r in rows], dtype=float)
        if np.std(values) < 1e-15:
            continue
        r_val = _pearson_r(values, delta_values)
        correlations.append({"feature": key, "pearson_r": r_val})

    correlations.sort(key=lambda x: abs(x["pearson_r"]), reverse=True)

    with open(args.correlation_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["feature", "pearson_r"])
        writer.writeheader()
        writer.writerows(correlations)
    print(f"Saved {len(correlations)} correlations to {args.correlation_csv}")

    print(f"\n{'Feature':>35s}  {'r':>8s}  {'|r|':>8s}")
    print("-" * 55)
    for c in correlations:
        marker = " **" if abs(c["pearson_r"]) > 0.5 else ""
        print(f"{c['feature']:>35s}  {c['pearson_r']:8.4f}  {abs(c['pearson_r']):8.4f}{marker}")
    print("\n** |r| > 0.5 (n=11, 注意样本量很小)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
