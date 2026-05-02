"""实验 5：历史分叉 — 验证经历是否沉积进结构.

Phase 5.1: 同 seed 不同刺激序列，观测结构分叉、动力学分叉、长期沉积。

核心命题：
    历史是否开始不可逆地塑造结构？

实验矩阵（6 组）：
    A_L:  plasticity=on,  L@300, R@1000
    A_R:  plasticity=on,  R@300, L@1000
    B:    plasticity=on,  无刺激
    C:    plasticity=on,  同 A_L（可重复性对照）
    D_L:  plasticity=off, 同 A_L（plasticity 因果对照，L then R）
    D_R:  plasticity=off, 同 A_R（plasticity-off 顺序对照，R then L）
    F:    plasticity=on,  同 A_L，刺激在 5000 步后停止，观测至 20000

验证三层：
    第一层 — 结构分叉：weight L1 distance, cosine similarity
    第二层 — 动力学分叉：同一测试刺激下响应差异
    第三层 — 稳定性：刺激移除后差异是否保留

不引入：homeostatic plasticity, 连接生长/消亡, task learning, global reward.
"""

import argparse
import csv
import json
import math
import sys
import time
import numpy as np

from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.observer import Observer
from aniva.environment.environment import Stimulus, StimulusEvent, Environment


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

# 物理刺激定义（无时间 — 时间属于"经历"层）
L_STIM = Stimulus(position=(-0.5, 0.0, 0.0), intensity=0.03, radius=0.5)
R_STIM = Stimulus(position=(0.5, 0.0, 0.0), intensity=0.03, radius=0.5)
TEST_STIM = Stimulus(position=(0.0, 0.5, 0.0), intensity=0.03, radius=0.5)

GROUP_DEFS = {
    "A_L": {
        "label": "L then R",
        "events": [
            {"stimulus": L_STIM, "start_step": 300, "duration_steps": 100},
            {"stimulus": R_STIM, "start_step": 1000, "duration_steps": 100},
            {"stimulus": TEST_STIM, "start_step": 19000, "duration_steps": 50},
        ],
        "plasticity_rate": 0.0001,
        "total_steps": 20000,
    },
    "A_R": {
        "label": "R then L",
        "events": [
            {"stimulus": R_STIM, "start_step": 300, "duration_steps": 100},
            {"stimulus": L_STIM, "start_step": 1000, "duration_steps": 100},
            {"stimulus": TEST_STIM, "start_step": 19000, "duration_steps": 50},
        ],
        "plasticity_rate": 0.0001,
        "total_steps": 20000,
    },
    "B": {
        "label": "no stimulus",
        "events": [
            {"stimulus": TEST_STIM, "start_step": 19000, "duration_steps": 50},
        ],
        "plasticity_rate": 0.0001,
        "total_steps": 20000,
    },
    "C": {
        "label": "repeat A_L",
        "events": [
            {"stimulus": L_STIM, "start_step": 300, "duration_steps": 100},
            {"stimulus": R_STIM, "start_step": 1000, "duration_steps": 100},
            {"stimulus": TEST_STIM, "start_step": 19000, "duration_steps": 50},
        ],
        "plasticity_rate": 0.0001,
        "total_steps": 20000,
    },
    "D_L": {
        "label": "plasticity off (L then R)",
        "events": [
            {"stimulus": L_STIM, "start_step": 300, "duration_steps": 100},
            {"stimulus": R_STIM, "start_step": 1000, "duration_steps": 100},
            {"stimulus": TEST_STIM, "start_step": 19000, "duration_steps": 50},
        ],
        "plasticity_rate": 0.0,
        "total_steps": 20000,
    },
    "D_R": {
        "label": "plasticity off (R then L)",
        "events": [
            {"stimulus": R_STIM, "start_step": 300, "duration_steps": 100},
            {"stimulus": L_STIM, "start_step": 1000, "duration_steps": 100},
            {"stimulus": TEST_STIM, "start_step": 19000, "duration_steps": 50},
        ],
        "plasticity_rate": 0.0,
        "total_steps": 20000,
    },
    "F": {
        "label": "long observation",
        "events": [
            {"stimulus": L_STIM, "start_step": 300, "duration_steps": 100},
            {"stimulus": R_STIM, "start_step": 1000, "duration_steps": 100},
        ],
        "plasticity_rate": 0.0001,
        "total_steps": 20000,
    },
}


# ── 单组运行 ────────────────────────────────────────────────────

def _run_group(
    config: AnivaConfig,
    group_name: str,
    total_steps: int,
    snapshot_interval: int = 1000,
    plasticity_rate: float | None = None,
) -> dict:
    """运行一个实验组，记录定期快照。

    Args:
        plasticity_rate: 覆盖 GROUP_DEFS 中的 plasticity_rate。None 则使用默认。

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

    rate = plasticity_rate if plasticity_rate is not None else gdef["plasticity_rate"]
    cfg = AnivaConfig(
        seed=config.seed,
        unit_count=config.unit_count,
        plasticity_rate=rate,
        homeostasis_enabled=config.homeostasis_enabled,
        homeostatic_target_abs_weight=config.homeostatic_target_abs_weight,
        homeostatic_rate=config.homeostatic_rate,
        use_numba_plasticity=config.use_numba_plasticity,
    )

    core = LifeCore(cfg)
    obs = Observer(core)

    env = Environment()
    for es in gdef["events"]:
        env.add_event(StimulusEvent(
            stimulus=es["stimulus"],
            start_step=es["start_step"],
            duration_steps=es["duration_steps"],
        ))

    snapshots: list[dict] = []
    checkpoints: dict[str, dict] = {}
    weights_initial = np.array([c.weight for c in core.connections])
    prev_weights = weights_initial.copy()
    t_start = time.time()

    for step in range(total_steps):
        influences = env.compute_influences(core.units, step)
        core.step(env_influences=influences if influences else None)

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
        "plasticity_rate": rate,
        "homeostasis_enabled": cfg.homeostasis_enabled,
        "homeostatic_target_abs_weight": cfg.homeostatic_target_abs_weight,
        "homeostatic_rate": cfg.homeostatic_rate,
        "use_numba_plasticity": cfg.use_numba_plasticity,
        "snapshots": snapshots,
        "checkpoints": checkpoints,
        "weights_initial": weights_initial,
        "weights_final": final_weights,
        "elapsed_sec": time.time() - t_start,
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
        ("A_L_vs_D_L", "A_L", "D_L"),
        ("C_vs_A_L", "C", "A_L"),
        ("D_L_vs_D_R", "D_L", "D_R"),
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
    plasticity_rate: float | None = None,
    seeds: list[int] | None = None,
) -> dict:
    """运行历史分叉实验。

    Args:
        config: 基础配置。
        total_steps: 每组总步数。
        snapshot_interval: 快照间隔。
        groups: 要运行的组名列表，None 则运行全部 6 组。
        plasticity_rate: 覆盖所有组的 plasticity_rate。None 则使用 GROUP_DEFS 默认值。
        seeds: 多 seed 列表，None 则使用 config.seed 单 seed。

    Returns:
        dict: 单 seed 时包含各组快照、分歧曲线、判定结果。
              多 seed 时额外包含 per_seed 列表和 aggregate 汇总。
    """
    if config is None:
        config = AnivaConfig()

    if groups is None:
        groups = list(GROUP_DEFS.keys())

    if seeds is None:
        seeds = [config.seed]

    per_seed_results: list[dict] = []
    for seed in seeds:
        seed_config = AnivaConfig(
            seed=seed,
            unit_count=config.unit_count,
            homeostasis_enabled=config.homeostasis_enabled,
            homeostatic_target_abs_weight=config.homeostatic_target_abs_weight,
            homeostatic_rate=config.homeostatic_rate,
            use_numba_plasticity=config.use_numba_plasticity,
        )

        group_results: dict[str, dict] = {}
        for gname in groups:
            tag = f"[seed={seed}]" if len(seeds) > 1 else ""
            print(f"Running group {gname} ({GROUP_DEFS[gname]['label']}) {tag}...")
            result = _run_group(
                seed_config, gname, total_steps, snapshot_interval,
                plasticity_rate=plasticity_rate,
            )
            group_results[gname] = result
            final = result["snapshots"][-1]
            elapsed = result.get("elapsed_sec", 0)
            rate = final['step'] / elapsed if elapsed > 0 else 0
            print(
                f"  done: step={final['step']} "
                f"act={final['mean_activation']:.4f} "
                f"eng={final['mean_energy']:.4f} "
                f"weight_mean={final['weight_mean']:.4f} "
                f"act_entropy={final['activation_entropy']:.4f} "
                f"({elapsed:.0f}s, {rate:.0f} steps/s)"
            )

        divergence = _compute_divergence_curves(group_results)
        verdict = _make_verdict(group_results, divergence)

        per_seed_results.append({
            "seed": seed,
            "unit_count": config.unit_count,
            "total_steps": total_steps,
            "groups": group_results,
            "divergence": divergence,
            "verdict": verdict,
        })

    if len(per_seed_results) == 1:
        return per_seed_results[0]

    # 多 seed 汇总
    aggregate = _aggregate_multi_seed(per_seed_results)
    return {
        "seeds": seeds,
        "unit_count": config.unit_count,
        "total_steps": total_steps,
        "per_seed": per_seed_results,
        "aggregate": aggregate,
    }


def _aggregate_multi_seed(per_seed: list[dict]) -> dict:
    """汇总多 seed 结果。"""
    agg = {}
    # 收集关键指标
    key_metrics = [
        "delta_weight_l1",
        "D_L_vs_D_R_weight_l1",
        "repeat_weight_l1",
        "diverge_weight_l1",
    ]
    for metric in key_metrics:
        values = []
        for r in per_seed:
            v = r["verdict"].get(metric)
            if v is not None:
                values.append(v)
        if values:
            agg[f"{metric}_mean"] = float(np.mean(values))
            agg[f"{metric}_std"] = float(np.std(values))
            agg[f"{metric}_min"] = float(np.min(values))
            agg[f"{metric}_max"] = float(np.max(values))

    # 分类判定汇总
    cat_metrics = [
        "structural_bifurcation",
        "plasticity_causal",
        "plasticity_off_symmetry",
        "repeatability",
    ]
    for metric in cat_metrics:
        values = []
        for r in per_seed:
            v = r["verdict"].get(metric)
            if v is not None:
                values.append(v)
        if values:
            agg[f"{metric}_modes"] = list(set(values))
            agg[f"{metric}_by_seed"] = {
                r["seed"]: r["verdict"].get(metric) for r in per_seed
            }

    return agg


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

    # Plasticity 因果检查：D_L 权重应与 A_L 初始态更接近
    if "D_L" in group_results and "A_L" in group_results:
        dl_vs_al_init = _weight_l1(
            group_results["D_L"]["weights_final"],
            group_results["A_L"]["weights_initial"],
        )
        al_vs_al_init = _weight_l1(
            group_results["A_L"]["weights_final"],
            group_results["A_L"]["weights_initial"],
        )
        v["plasticity_causal"] = (
            "plasticity_drives_divergence"
            if dl_vs_al_init < al_vs_al_init * 0.5
            else "no_clear_plasticity_effect"
        )
        v["D_L_weight_drift"] = dl_vs_al_init
        v["A_L_weight_drift"] = al_vs_al_init

    # Plasticity-off 顺序对照：无 plasticity 时不同顺序应结构一致
    if "D_L" in group_results and "D_R" in group_results:
        dl_vs_dr = _weight_l1(
            group_results["D_L"]["weights_final"],
            group_results["D_R"]["weights_final"],
        )
        v["plasticity_off_symmetry"] = (
            "order_irrelevant_without_plasticity"
            if dl_vs_dr < 1e-4
            else "order_matters_even_without_plasticity"
        )
        v["D_L_vs_D_R_weight_l1"] = dl_vs_dr

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

    # 结构分叉检查：A_L vs A_R 的 delta（三层判定）
    if "A_L_vs_A_R" in divergence:
        d = divergence["A_L_vs_A_R"]
        delta = abs(d.get("delta_weight_l1", 0))
        if delta > 1e-4:
            v["structural_bifurcation"] = "significant"
        elif delta > 5e-5:
            v["structural_bifurcation"] = "emerging"
        else:
            v["structural_bifurcation"] = "weak"
        v["delta_weight_l1"] = d.get("delta_weight_l1", 0)

    # 因果骨架判定：可复现 + plasticity-off 对称 + plasticity 因果
    skeleton_ok = True
    skeleton_checks = []
    if "repeatability" in v:
        skeleton_checks.append(v["repeatability"] == "deterministic_history_sensitive")
    if "plasticity_off_symmetry" in v:
        skeleton_checks.append(v["plasticity_off_symmetry"] == "order_irrelevant_without_plasticity")
    if "plasticity_causal" in v:
        skeleton_checks.append(v["plasticity_causal"] == "plasticity_drives_divergence")
    v["causal_skeleton_intact"] = all(skeleton_checks) if skeleton_checks else None

    return v


# ── 输出 ─────────────────────────────────────────────────────────

def _print_results(result: dict) -> None:
    """打印实验结果摘要。"""
    # 多 seed 模式
    if "per_seed" in result:
        _print_multi_seed_results(result)
        return

    # 单 seed 模式
    print()
    print("=" * 70)
    print("History Bifurcation Experiment Results")
    print(f"seed={result['seed']}, units={result['unit_count']}, "
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


def _print_multi_seed_results(result: dict) -> None:
    """打印多 seed 实验结果摘要。"""
    print()
    print("=" * 70)
    print("History Bifurcation — Multi-Seed Results")
    print(f"seeds={result['seeds']}, units={result['unit_count']}, "
          f"steps={result['total_steps']}")
    print("=" * 70)

    # 逐 seed 判决
    print("\n--- Per-Seed Verdict Summary ---")
    key_fields = [
        "structural_bifurcation", "delta_weight_l1",
        "plasticity_causal", "D_L_vs_D_R_weight_l1",
        "plasticity_off_symmetry", "repeatability", "repeat_weight_l1",
    ]
    header = f"{'seed':>6s}"
    col_widths = {}
    for f in key_fields:
        w = max(len(f), 14)
        header += f"  {f:>{w}s}"
        col_widths[f] = w
    print(header)
    print("-" * len(header))
    for r in result["per_seed"]:
        v = r["verdict"]
        line = f"{r['seed']:>6d}"
        for f in key_fields:
            val = v.get(f)
            if val is None:
                line += f"  {'N/A':>{col_widths[f]}s}"
            elif isinstance(val, float):
                line += f"  {val:>{col_widths[f]}.6f}"
            else:
                s = str(val)[:col_widths[f]]
                line += f"  {s:>{col_widths[f]}s}"
        print(line)

    # 汇总
    agg = result["aggregate"]
    print("\n--- Aggregate ---")
    for key, val in agg.items():
        if isinstance(val, float):
            print(f"  {key}: {val:.6f}")
        elif isinstance(val, dict):
            print(f"  {key}:")
            for k2, v2 in val.items():
                print(f"    {k2}: {v2}")
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


def _make_summary(result: dict) -> dict:
    """从实验结果提取精简 summary（适合 JSON 序列化）。"""
    if "per_seed" in result:
        first_seed = result["per_seed"][0]
        first_group = next(iter(first_seed["groups"].values()))
        return {
            "mode": "multi_seed",
            "seeds": result["seeds"],
            "unit_count": result["unit_count"],
            "total_steps": result["total_steps"],
            "homeostasis_enabled": first_group.get("homeostasis_enabled", False),
            "use_numba_plasticity": first_group.get("use_numba_plasticity", False),
            "per_seed": [_make_single_summary(r) for r in result["per_seed"]],
            "aggregate": _serialize_aggregate(result["aggregate"]),
        }

    return _make_single_summary(result)


def _make_single_summary(r: dict) -> dict:
    """单 seed summary。"""
    groups_summary = {}
    for gname, gdata in r["groups"].items():
        final = gdata["snapshots"][-1]
        groups_summary[gname] = {
            "label": gdata["label"],
            "plasticity_rate": gdata["plasticity_rate"],
            "final_step": final["step"],
            "mean_activation": final["mean_activation"],
            "mean_energy": final["mean_energy"],
            "hard_active_ratio": final["hard_active_ratio"],
            "activation_entropy": final["activation_entropy"],
            "weight_mean": final["weight_mean"],
            "weight_std": final["weight_std"],
            "weight_abs_mean": final["weight_abs_mean"],
            "elapsed_sec": gdata.get("elapsed_sec", 0),
        }

    divergence_summary = {}
    for pair_name, d in r["divergence"].items():
        divergence_summary[pair_name] = {
            k: v for k, v in d.items()
            if isinstance(v, (float, int)) and not isinstance(v, bool)
        }

    # 从第一个 group 提取配置信息（所有 group 共用同一 config）
    first_group = next(iter(r["groups"].values()))
    return {
        "seed": r["seed"],
        "unit_count": r["unit_count"],
        "total_steps": r["total_steps"],
        "homeostasis_enabled": first_group.get("homeostasis_enabled", False),
        "use_numba_plasticity": first_group.get("use_numba_plasticity", False),
        "groups": groups_summary,
        "divergence": divergence_summary,
        "verdict": {k: v for k, v in r["verdict"].items() if not isinstance(v, dict)},
    }


def _serialize_aggregate(agg: dict) -> dict:
    """确保 aggregate 值可 JSON 序列化。"""
    out = {}
    for k, v in agg.items():
        if isinstance(v, float):
            out[k] = v
        elif isinstance(v, (list, set)):
            out[k] = list(v)
        elif isinstance(v, dict):
            out[k] = {str(ks): vs for ks, vs in v.items()}
        else:
            out[k] = str(v) if v is not None else None
    return out


def _save_summary_json(result: dict, path: str) -> None:
    """保存精简 summary JSON。"""
    summary = _make_summary(result)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)


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
    parser.add_argument(
        "--plasticity-rate", type=float, default=None,
        help="覆盖所有组的 plasticity_rate（默认使用 GROUP_DEFS 值）"
    )
    parser.add_argument(
        "--homeostasis-enabled", action="store_true", default=None,
        help="启用 homeostatic maintenance，防止 weight decay 导致系统静默"
    )
    parser.add_argument(
        "--seeds", type=int, nargs="+", default=None,
        help="多 seed 列表（默认单 seed）。例：--seeds 42 77 123"
    )
    parser.add_argument(
        "--summary-json", type=str, default=None,
        help="保存精简 summary JSON（仅 verduct + final metrics）"
    )
    parser.add_argument(
        "--summary-only", action="store_true", default=False,
        help="只输出 summary JSON，跳过 CSV"
    )
    parser.add_argument(
        "--use-numba-plasticity", action="store_true", default=False,
        help="启用 Numba plasticity 加速后端（Numba 不可用时自动降级为 scalar）"
    )
    args = parser.parse_args(argv)

    config = AnivaConfig(seed=args.seed, unit_count=args.unit_count)
    if args.homeostasis_enabled is not None:
        config.homeostasis_enabled = args.homeostasis_enabled
    config.use_numba_plasticity = args.use_numba_plasticity

    result = run_experiment(
        config=config,
        total_steps=args.steps,
        snapshot_interval=args.snapshot_interval,
        groups=args.groups,
        plasticity_rate=args.plasticity_rate,
        seeds=args.seeds,
    )

    _print_results(result)

    if args.summary_json:
        _save_summary_json(result, args.summary_json)
        print(f"\nSaved summary JSON to {args.summary_json}")

    if args.output_csv and not args.summary_only:
        _save_csv(result, args.output_csv)
        print(f"\nSaved snapshots to {args.output_csv}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
