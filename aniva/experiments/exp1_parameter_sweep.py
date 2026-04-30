"""实验 1 参数扫描 — 比较不同参数下的自由运行最终状态.

不做参数推荐，不解释"好坏"——只记录客观指标。
目标：帮助观察不同参数组合下系统的行为差异。
"""

import argparse
import csv
import itertools
import sys
from typing import Any

from aniva.config import AnivaConfig
from aniva.experiments.exp1_free_run import run


def sweep(
    noise_strengths: list[float],
    baseline_activities: list[float],
    synaptic_strengths: list[float],
    seeds: list[int],
    threshold_mins: list[float] | None = None,
    threshold_maxs: list[float] | None = None,
    min_energy_activation_factors: list[float] | None = None,
    leak_rates: list[float] | None = None,
    threshold_softnesses: list[float] | None = None,
    unit_count: int = 30,
    total_steps: int = 500,
) -> list[dict[str, Any]]:
    """扫描参数组合，返回每组参数的 final_metrics。

    Args:
        noise_strengths: 要测试的 noise_strength 值列表。
        baseline_activities: 要测试的 baseline_activity 值列表。
        synaptic_strengths: 要测试的 synaptic_strength 值列表。
        seeds: 要测试的随机种子列表。
        threshold_mins: threshold_min 值列表，None 则用默认值。
        threshold_maxs: threshold_max 值列表，None 则用默认值。
        min_energy_activation_factors: min_energy_activation_factor 值列表，None 则用默认值。
        leak_rates: leak_rate 值列表，None 则用默认值。
        threshold_softnesses: threshold_softness 值列表，None 则用默认值。
        unit_count: 每组使用的单元数。
        total_steps: 每组运行的总步数。

    Returns:
        list[dict]，每个 dict 包含参数和 final_metrics。
    """
    if threshold_mins is None:
        threshold_mins = [AnivaConfig.threshold_min]
    if threshold_maxs is None:
        threshold_maxs = [AnivaConfig.threshold_max]
    if min_energy_activation_factors is None:
        min_energy_activation_factors = [AnivaConfig.min_energy_activation_factor]
    if leak_rates is None:
        leak_rates = [AnivaConfig.leak_rate]
    if threshold_softnesses is None:
        threshold_softnesses = [AnivaConfig.threshold_softness]

    results: list[dict[str, Any]] = []
    for ns, ba, ss, seed, tmin, tmax, eaf, lr, ts in itertools.product(
        noise_strengths, baseline_activities, synaptic_strengths,
        seeds, threshold_mins, threshold_maxs,
        min_energy_activation_factors, leak_rates,
        threshold_softnesses,
    ):
        if tmin > tmax:
            continue
        config = AnivaConfig(
            unit_count=unit_count,
            seed=seed,
            dt=1.0,
            noise_strength=ns,
            baseline_activity=ba,
            synaptic_strength=ss,
            threshold_min=tmin,
            threshold_max=tmax,
            min_energy_activation_factor=eaf,
            leak_rate=lr,
            threshold_softness=ts,
        )
        result = run(config=config, total_steps=total_steps, report_interval=total_steps + 1)
        fm = result["final_metrics"]
        results.append({
            "noise_strength": ns,
            "baseline_activity": ba,
            "synaptic_strength": ss,
            "seed": seed,
            "threshold_min": tmin,
            "threshold_max": tmax,
            "min_energy_activation_factor": eaf,
            "leak_rate": lr,
            "threshold_softness": ts,
            "mean_activation": fm["mean_activation"],
            "max_activation": fm["max_activation"],
            "mean_energy": fm["mean_energy"],
            "min_energy": fm["min_energy"],
            "mean_trace": fm["mean_trace"],
            "active_unit_ratio": fm["active_unit_ratio"],
            "mean_threshold": fm["mean_threshold"],
            "mean_activation_to_threshold_ratio": fm["mean_activation_to_threshold_ratio"],
            "hard_active_ratio": fm["hard_active_ratio"],
            "soft_output_ratio": fm["soft_output_ratio"],
            "strong_output_ratio": fm["strong_output_ratio"],
            "source_active_ratio": fm["source_active_ratio"],
            "mean_effective_output": fm["mean_effective_output"],
            "max_effective_output": fm["max_effective_output"],
            "mean_abs_synaptic_input": fm["mean_abs_synaptic_input"],
            "max_abs_synaptic_input": fm["max_abs_synaptic_input"],
            "synaptic_target_ratio": fm["synaptic_target_ratio"],
        })
    return results


def _save_csv(results: list[dict], path: str) -> None:
    if not results:
        return
    fieldnames = list(results[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Aniva 参数扫描：比较不同参数下的自由运行最终状态"
    )
    parser.add_argument(
        "--steps", type=int, default=500,
        help="每组运行步数（默认 500）"
    )
    parser.add_argument(
        "--unit-count", type=int, default=30,
        help="每组单元数（默认 30）"
    )
    parser.add_argument(
        "--noise", type=float, nargs="+", default=[0.005, 0.01, 0.02],
        help="noise_strength 值列表"
    )
    parser.add_argument(
        "--baseline", type=float, nargs="+", default=[0.02, 0.05, 0.1],
        help="baseline_activity 值列表"
    )
    parser.add_argument(
        "--synaptic", type=float, nargs="+", default=[0.02, 0.05, 0.1],
        help="synaptic_strength 值列表"
    )
    parser.add_argument(
        "--seeds", type=int, nargs="+", default=[1, 2],
        help="随机种子列表"
    )
    parser.add_argument(
        "--threshold-min", type=float, nargs="+", default=None,
        help="threshold_min 值列表（默认 0.2）"
    )
    parser.add_argument(
        "--threshold-max", type=float, nargs="+", default=None,
        help="threshold_max 值列表（默认 0.4）"
    )
    parser.add_argument(
        "--energy-factor", type=float, nargs="+", default=None,
        help="min_energy_activation_factor 值列表（默认 0.25）"
    )
    parser.add_argument(
        "--leak-rate", type=float, nargs="+", default=None,
        help="leak_rate 值列表（默认 0.02）"
    )
    parser.add_argument(
        "--threshold-softness", type=float, nargs="+", default=None,
        help="threshold_softness 值列表（默认 0.05）"
    )
    parser.add_argument(
        "--output-csv", type=str, default=None,
        help="保存结果到 CSV 文件"
    )
    args = parser.parse_args(argv)

    results = sweep(
        noise_strengths=args.noise,
        baseline_activities=args.baseline,
        synaptic_strengths=args.synaptic,
        seeds=args.seeds,
        threshold_mins=args.threshold_min,
        threshold_maxs=args.threshold_max,
        min_energy_activation_factors=args.energy_factor,
        leak_rates=args.leak_rate,
        threshold_softnesses=args.threshold_softness,
        unit_count=args.unit_count,
        total_steps=args.steps,
    )

    # 打印摘要
    if results:
        fieldnames = list(results[0].keys())
        print("\t".join(fieldnames))
        for row in results:
            print("\t".join(str(row[k]) for k in fieldnames))

    if args.output_csv:
        _save_csv(results, args.output_csv)
        print(f"Saved {len(results)} rows to {args.output_csv}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
