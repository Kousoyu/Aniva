"""实验 5：历史分叉 — 验证经历是否沉积进结构.

Phase 5.1: 同 seed 不同刺激序列，观测结构分叉、动力学分叉、长期沉积。

核心命题：
    历史是否开始不可逆地塑造结构？

实验矩阵（6 组）：
    A_L:  plasticity=on,  L@300, R@1000
    A_R:  plasticity=on,  R@300, L@1000
    B:    plasticity=on,  无刺激
    C:    plasticity=on,  同 A_L（可重复性对照）
    D:    plasticity=off, 同 A_L（plasticity 因果对照）
    F:    plasticity=on,  同 A_L，刺激在 5000 步后停止，观测至 20000

验证三层：
    第一层 — 结构分叉：weight L1 distance, cosine similarity
    第二层 — 动力学分叉：同一测试刺激下响应差异
    第三层 — 稳定性：刺激移除后差异是否保留

不引入：homeostatic plasticity, 连接生长/消亡, task learning, global reward.
"""

import argparse
import csv
import math
import sys
import numpy as np

from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.observer import Observer
from aniva.environment.environment import Stimulus, Environment


# ── 辅助函数 ────────────────────────────────────────────────────

def _activation_entropy(activations: np.ndarray, bins: int = 20) -> float:
    """激活分布熵 — 衡量活跃模式的多样性。"""
    hist, _ = np.histogram(activations, bins=bins, range=(0.0, 1.0))
    hist = hist.astype(float) / max(hist.sum(), 1)
    hist = hist[hist > 0]
    if len(hist) == 0:
        return 0.0
    return float(-np.sum(hist * np.log(hist)))


def _weight_stats(weights: np.ndarray) -> dict:
    """权重向量统计。"""
    return {
        "weight_mean": float(np.mean(weights)),
        "weight_std": float(np.std(weights)),
        "weight_abs_mean": float(np.mean(np.abs(weights))),
    }


def _weight_l1(wa: np.ndarray, wb: np.ndarray) -> float:
    """权重向量 L1 距离（平均绝对差）。"""
    return float(np.mean(np.abs(wa - wb)))


def _weight_cosine(wa: np.ndarray, wb: np.ndarray) -> float:
    """权重向量余弦相似度。"""
    na = np.linalg.norm(wa)
    nb = np.linalg.norm(wb)
    if na < 1e-12 or nb < 1e-12:
        return 1.0 if na < 1e-12 and nb < 1e-12 else 0.0
    return float(np.dot(wa, wb) / (na * nb))


def _activation_l1(core_a: LifeCore, core_b: LifeCore) -> float:
    """两个 core 的 activation 向量 L1 距离。"""
    acts_a = np.array([u.activation for u in core_a.units.values()])
    acts_b = np.array([u.activation for u in core_b.units.values()])
    return float(np.mean(np.abs(acts_a - acts_b)))


def _make_snapshot(
    core: LifeCore, obs: Observer, step: int,
) -> dict:
    """提取单步快照：metrics + 权重统计 + 激活熵。"""
    metrics = obs.get_metrics()
    activations = np.array([u.activation for u in core.units.values()])
    weights = np.array([c.weight for c in core.connections])
    snap = {
        "step": step,
        "mean_activation": metrics["mean_activation"],
        "mean_energy": metrics["mean_energy"],
        "hard_active_ratio": metrics["hard_active_ratio"],
        "strong_output_ratio": metrics["strong_output_ratio"],
        "activation_entropy": _activation_entropy(activations),
    }
    snap.update(_weight_stats(weights))
    return snap


# ── 刺激配置 ────────────────────────────────────────────────────

# 训练刺激
L_STIM = Stimulus(
    position=(-0.5, 0.0, 0.0),
    intensity=0.03, radius=0.5,
    start_step=300, duration_steps=100,
)
R_STIM = Stimulus(
    position=(0.5, 0.0, 0.0),
    intensity=0.03, radius=0.5,
    start_step=1000, duration_steps=100,
)

# 测试刺激（对所有组在 step=19000 施加，探测动力学差异）
TEST_STIM = Stimulus(
    position=(0.0, 0.5, 0.0),
    intensity=0.03, radius=0.5,
    start_step=19000, duration_steps=50,
)

GROUP_DEFS = {
    "A_L": {
        "label": "L then R",
        "train_stimuli": [L_STIM, R_STIM],
        "plasticity_rate": 0.0001,
        "test_stimulus": TEST_STIM,
        "total_steps": 20000,
    },
    "A_R": {
        "label": "R then L",
        "train_stimuli": [R_STIM, L_STIM],
        "plasticity_rate": 0.0001,
        "test_stimulus": TEST_STIM,
        "total_steps": 20000,
    },
    "B": {
        "label": "no stimulus",
        "train_stimuli": [],
        "plasticity_rate": 0.0001,
        "test_stimulus": TEST_STIM,
        "total_steps": 20000,
    },
    "C": {
        "label": "repeat A_L",
        "train_stimuli": [L_STIM, R_STIM],
        "plasticity_rate": 0.0001,
        "test_stimulus": TEST_STIM,
        "total_steps": 20000,
    },
    "D": {
        "label": "plasticity off",
        "train_stimuli": [L_STIM, R_STIM],
        "plasticity_rate": 0.0,
        "test_stimulus": TEST_STIM,
        "total_steps": 20000,
    },
    "F": {
        "label": "long observation",
        "train_stimuli": [L_STIM, R_STIM],
        "plasticity_rate": 0.0001,
        "test_stimulus": None,  # F 不施加测试刺激，观察长期自发轨迹
        "total_steps": 20000,
    },
}


# ── 单组运行 ────────────────────────────────────────────────────

def _run_group(
    config: AnivaConfig,
    group_name: str,
    total_steps: int,
    snapshot_interval: int = 1000,
) -> dict:
    """运行一个实验组，记录定期快照。

    Returns:
        dict: {
            "group": str,
            "label": str,
            "plasticity_rate": float,
            "snapshots": list[dict],
            "checkpoints": dict[str, dict],
            "final_weights": np.ndarray,
        }
    """
    gdef = GROUP_DEFS[group_name]

    # 覆盖 plasticity_rate
    cfg = AnivaConfig(
        seed=config.seed,
        unit_count=config.unit_count,
        plasticity_rate=gdef["plasticity_rate"],
    )

    core = LifeCore(cfg)
    obs = Observer(core)

    env = Environment()
    for stim in gdef["train_stimuli"]:
        env.add_stimulus(stim)
    test_env = Environment()
    if gdef["test_stimulus"] is not None:
        test_env.add_stimulus(gdef["test_stimulus"])

    snapshots: list[dict] = []
    checkpoints: dict[str, dict] = {}
    weights_initial = np.array([c.weight for c in core.connections])
    prev_weights = weights_initial.copy()

    for step in range(total_steps):
        # 训练刺激
        train_infl = env.compute_influences(core.units, step)
        # 测试刺激
        test_infl = test_env.compute_influences(core.units, step)
        # 合并（测试刺激优先级更高）
        merged = {**train_infl}
        for uid, inf in test_infl.items():
            merged[uid] = merged.get(uid, 0.0) + inf

        core.step(env_influences=merged if merged else None)

        if step == 0:
            checkpoints["initial"] = {
                "step": 0,
                "weights": np.array([c.weight for c in core.connections]),
                "activations": np.array([u.activation for u in core.units.values()]),
            }

        if (step + 1) % snapshot_interval == 0 or step == total_steps - 1:
            curr_weights = np.array([c.weight for c in core.connections])
            snap = _make_snapshot(core, obs, step + 1)
            # Connection turnover: fraction changed since last snapshot
            weight_deltas = np.abs(curr_weights - prev_weights)
            snap["turnover_fraction"] = float(
                np.mean(weight_deltas > 1e-6)
            )
            snap["mean_abs_weight_change"] = float(np.mean(weight_deltas))
            snapshots.append(snap)
            prev_weights = curr_weights.copy()

    # 关键检查点
    final_weights = np.array([c.weight for c in core.connections])
    final_acts = np.array([u.activation for u in core.units.values()])
    checkpoints["final"] = {
        "step": total_steps,
        "weights": final_weights,
        "activations": final_acts,
    }

    return {
        "group": group_name,
        "label": gdef["label"],
        "plasticity_rate": gdef["plasticity_rate"],
        "snapshots": snapshots,
        "checkpoints": checkpoints,
        "weights_initial": weights_initial,
        "weights_final": final_weights,
    }


# ── 分歧曲线计算 ────────────────────────────────────────────────

def _compute_divergence_curves(
    group_results: dict[str, dict],
) -> dict[str, dict]:
    """计算组间分歧曲线。

    Returns:
        dict: {
            "pair_name": {
                "steps": list[int],
                "weight_l1": list[float],
                "activation_l1": list[float],
            }
        }
    """
    # 只对实际运行的组计算比较
    all_comparisons = [
        ("A_L_vs_A_R", "A_L", "A_R"),
        ("A_L_vs_B", "A_L", "B"),
        ("A_L_vs_D", "A_L", "D"),
        ("C_vs_A_L", "C", "A_L"),
    ]
    available = [(name, a, b) for name, a, b in all_comparisons
                 if a in group_results and b in group_results]

    curves = {}
    for pair_name, ga, gb in available:
        ra = group_results[ga]
        rb = group_results[gb]
        sa = ra["snapshots"]
        sb = rb["snapshots"]

        # 对齐步数
        steps = sorted(set(
            s["step"] for s in sa
        ).intersection(
            s["step"] for s in sb
        ))

        w_l1_curve = []
        act_l1_curve = []

        for step in steps:
            snap_a = next(s for s in sa if s["step"] == step)
            snap_b = next(s for s in sb if s["step"] == step)

            # 权重 L1（使用 checkpoint 中的完整向量）
            wa = ra["checkpoints"]["final"]["weights"]
            wb = rb["checkpoints"]["final"]["weights"]
            # 注：这里需要定期保存权重。暂时用 mean_activation 等做代理
            # activation L1 近似 = 用 mean_activation 的绝对差
            w_l1_curve.append(abs(
                snap_a.get("weight_abs_mean", 0) -
                snap_b.get("weight_abs_mean", 0)
            ))
            act_l1_curve.append(abs(
                snap_a["mean_activation"] - snap_b["mean_activation"]
            ))

        curves[pair_name] = {
            "steps": steps,
            "weight_abs_mean_diff": w_l1_curve,
            "mean_activation_diff": act_l1_curve,
        }

    # 最终权重的精确比较
    for pair_name, ga, gb in available:
        wa_final = group_results[ga]["weights_final"]
        wb_final = group_results[gb]["weights_final"]
        wa_init = group_results[ga]["weights_initial"]
        wb_init = group_results[gb]["weights_initial"]

        curves[pair_name]["final_weight_l1"] = _weight_l1(wa_final, wb_final)
        curves[pair_name]["initial_weight_l1"] = _weight_l1(wa_init, wb_init)
        curves[pair_name]["delta_weight_l1"] = (
            _weight_l1(wa_final, wb_final) - _weight_l1(wa_init, wb_init)
        )
        curves[pair_name]["final_weight_cosine"] = _weight_cosine(wa_final, wb_final)
        curves[pair_name]["initial_weight_cosine"] = _weight_cosine(wa_init, wb_init)

    return curves


# ── 主实验入口 ──────────────────────────────────────────────────

def run_experiment(
    config: AnivaConfig | None = None,
    total_steps: int = 20000,
    snapshot_interval: int = 1000,
    groups: list[str] | None = None,
) -> dict:
    """运行历史分叉实验。

    Args:
        config: 基础配置。
        total_steps: 每组总步数（会被 GROUP_DEFS 覆盖）。
        snapshot_interval: 快照间隔。
        groups: 要运行的组名列表，None 则运行全部 6 组。

    Returns:
        dict: 包含各组快照、分歧曲线、判定结果。
    """
    if config is None:
        config = AnivaConfig()

    if groups is None:
        groups = list(GROUP_DEFS.keys())

    group_results: dict[str, dict] = {}
    for gname in groups:
        print(f"Running group {gname} ({GROUP_DEFS[gname]['label']})...")
        result = _run_group(config, gname, total_steps, snapshot_interval)
        group_results[gname] = result
        final = result["snapshots"][-1]
        print(
            f"  done: step={final['step']} "
            f"act={final['mean_activation']:.4f} "
            f"eng={final['mean_energy']:.4f} "
            f"weight_mean={final['weight_mean']:.4f} "
            f"act_entropy={final['activation_entropy']:.4f}"
        )

    divergence = _compute_divergence_curves(group_results)

    # 判定
    verdict = _make_verdict(group_results, divergence)

    return {
        "config_seed": config.seed,
        "unit_count": config.unit_count,
        "total_steps": total_steps,
        "groups": group_results,
        "divergence": divergence,
        "verdict": verdict,
    }


def _make_verdict(
    group_results: dict[str, dict],
    divergence: dict[str, dict],
) -> dict:
    """根据控制组结果生成判定。"""
    v = {}

    # 可重复性检查：C vs A_L 差异应远小于 A_L vs A_R
    if "C" in group_results and "A_L" in group_results and "A_R" in group_results:
        c_vs_al = _weight_l1(
            group_results["C"]["weights_final"],
            group_results["A_L"]["weights_final"],
        )
        al_vs_ar = _weight_l1(
            group_results["A_L"]["weights_final"],
            group_results["A_R"]["weights_final"],
        )
        v["repeatability"] = (
            "deterministic_history_sensitive"
            if c_vs_al < al_vs_ar * 0.5
            else "chaotic"
            if c_vs_al > al_vs_ar * 0.8
            else "marginal"
        )
        v["repeat_weight_l1"] = c_vs_al
        v["diverge_weight_l1"] = al_vs_ar

    # Plasticity 因果检查：D 权重应与 A_L 初始态更接近
    if "D" in group_results and "A_L" in group_results:
        d_vs_al_init = _weight_l1(
            group_results["D"]["weights_final"],
            group_results["A_L"]["weights_initial"],
        )
        al_vs_al_init = _weight_l1(
            group_results["A_L"]["weights_final"],
            group_results["A_L"]["weights_initial"],
        )
        v["plasticity_causal"] = (
            "plasticity_drives_divergence"
            if d_vs_al_init < al_vs_al_init * 0.5
            else "no_clear_plasticity_effect"
        )
        v["D_weight_drift"] = d_vs_al_init
        v["A_L_weight_drift"] = al_vs_al_init

    # 长期沉积检查：F 最终状态与 B 的差异
    if "F" in group_results and "B" in group_results:
        f_vs_b = _weight_l1(
            group_results["F"]["weights_final"],
            group_results["B"]["weights_final"],
        )
        v["long_term_deposition"] = (
            "deposition_detected"
            if f_vs_b > 1e-4
            else "no_significant_deposition"
        )
        v["F_vs_B_weight_l1"] = f_vs_b

    # 结构分叉检查：A_L vs A_R 的 delta
    if "A_L_vs_A_R" in divergence:
        d = divergence["A_L_vs_A_R"]
        v["structural_bifurcation"] = (
            "significant"
            if abs(d.get("delta_weight_l1", 0)) > 1e-4
            else "negligible"
        )
        v["delta_weight_l1"] = d.get("delta_weight_l1", 0)

    return v


# ── 输出 ─────────────────────────────────────────────────────────

def _print_results(result: dict) -> None:
    """打印实验结果摘要。"""
    print()
    print("=" * 70)
    print("History Bifurcation Experiment Results")
    print(f"seed={result['config_seed']}, units={result['unit_count']}, "
          f"steps={result['total_steps']}")
    print("=" * 70)

    # 各组最终状态
    print("\n--- Final State Summary ---")
    header = (
        f"{'group':>6s}  {'act':>7s}  {'eng':>7s}  "
        f"{'hard':>6s}  {'w_mean':>7s}  {'act_ent':>8s}"
    )
    print(header)
    print("-" * len(header))
    for gname, gdata in result["groups"].items():
        final = gdata["snapshots"][-1]
        print(
            f"{gname:>6s}  {final['mean_activation']:7.4f}  "
            f"{final['mean_energy']:7.4f}  "
            f"{final['hard_active_ratio']:5.1%}  "
            f"{final['weight_mean']:7.4f}  "
            f"{final['activation_entropy']:8.4f}"
        )

    # 分歧曲线
    print("\n--- Divergence (Final Weight L1 & Cosine) ---")
    for pair_name, d in result["divergence"].items():
        if "final_weight_l1" in d:
            print(
                f"  {pair_name:>16s}:  "
                f"Δ_L1={d.get('delta_weight_l1', 0):.6f}  "
                f"final_L1={d['final_weight_l1']:.6f}  "
                f"cosine={d['final_weight_cosine']:.6f}"
            )

    # 判定
    print("\n--- Verdict ---")
    for key, val in result["verdict"].items():
        if isinstance(val, float):
            print(f"  {key}: {val:.6f}")
        else:
            print(f"  {key}: {val}")


def _save_csv(result: dict, path: str) -> None:
    """将快照保存为 CSV。"""
    rows = []
    for gname, gdata in result["groups"].items():
        for snap in gdata["snapshots"]:
            row = {"group": gname, "label": gdata["label"]}
            row.update(snap)
            rows.append(row)
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ── CLI ──────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Aniva 实验 5：历史分叉"
    )
    parser.add_argument(
        "--steps", type=int, default=20000,
        help="总运行步数（默认 20000）"
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="随机种子（默认 42）"
    )
    parser.add_argument(
        "--unit-count", type=int, default=300,
        help="活性单元数量（默认 300）"
    )
    parser.add_argument(
        "--snapshot-interval", type=int, default=1000,
        help="快照间隔（默认 1000）"
    )
    parser.add_argument(
        "--groups", type=str, nargs="+", default=None,
        help="指定运行组（默认全部 6 组）"
    )
    parser.add_argument(
        "--output-csv", type=str, default=None,
        help="保存快照到 CSV"
    )
    args = parser.parse_args(argv)

    config = AnivaConfig(seed=args.seed, unit_count=args.unit_count)

    result = run_experiment(
        config=config,
        total_steps=args.steps,
        snapshot_interval=args.snapshot_interval,
        groups=args.groups,
    )

    _print_results(result)

    if args.output_csv:
        _save_csv(result, args.output_csv)
        print(f"\nSaved snapshots to {args.output_csv}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
