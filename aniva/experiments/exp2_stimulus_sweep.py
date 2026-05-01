"""实验 2 扩展：刺激参数扫描.

批量运行 exp2_stimulus.run()，观察不同点刺激参数下的轨迹分叉和后效。

Phase 4.2: intensity × seed 扫描。
工具支持 intensity / radius / stim_start / seed 多维度扫描，
默认只扫 intensity × seed，后续可扩展。
"""

import argparse
import csv
import sys
from collections.abc import Sequence

from aniva.config import AnivaConfig
from aniva.experiments import exp2_stimulus


def _classify_response(
    during_max_traj_dist: float,
    post_final_traj_dist: float,
    s_final_hard: float,
    s_final_energy: float,
) -> str:
    """根据刺激响应指标分类。

    阈值说明：
        - during_max_traj_dist < 0.01  → none（几乎无响应）
        - s_final_hard > 0.8 或 s_final_energy < 0.15 → takeover（接管/能量崩）
        - 其余有明显分叉 → touch（轻触）

    这只是实验标签，不是生命判断。
    """
    if during_max_traj_dist < 0.01:
        return "none"
    if s_final_hard > 0.8 or s_final_energy < 0.15:
        return "takeover"
    return "touch"


def _extract_row(
    result: dict,
    seed: int,
    intensity: float,
    radius: float,
    stim_start: int,
    stim_duration: int,
) -> dict:
    """从单次 exp2_stimulus.run() 结果中提取汇总字段。"""
    history = result["trajectory_history"]

    during_dists = [
        h["trajectory_distance"]
        for h in history
        if h["phase"] == "during_stimulus"
    ]
    post_dists = [
        h["trajectory_distance"]
        for h in history
        if h["phase"] == "post_stimulus"
    ]

    during_max = max(during_dists) if during_dists else 0.0
    during_mean = sum(during_dists) / len(during_dists) if during_dists else 0.0
    post_final = post_dists[-1] if post_dists else 0.0
    post_mean = sum(post_dists) / len(post_dists) if post_dists else 0.0

    b_final = result["final_baseline_metrics"]
    s_final = result["final_stimulus_metrics"]

    b_hard = b_final["hard_active_ratio"]
    s_hard = s_final["hard_active_ratio"]
    s_energy = s_final["mean_energy"]

    response_class = _classify_response(during_max, post_final, s_hard, s_energy)

    return {
        "seed": seed,
        "stim_intensity": intensity,
        "stim_radius": radius,
        "stim_start": stim_start,
        "stim_duration": stim_duration,
        "stimulated_unit_ratio": result["stimulated_unit_ratio"],
        "during_max_trajectory_distance": during_max,
        "during_mean_trajectory_distance": during_mean,
        "post_final_trajectory_distance": post_final,
        "post_mean_trajectory_distance": post_mean,
        "baseline_final_mean_activation": b_final["mean_activation"],
        "stimulus_final_mean_activation": s_final["mean_activation"],
        "baseline_final_mean_energy": b_final["mean_energy"],
        "stimulus_final_mean_energy": s_energy,
        "baseline_final_hard_active_ratio": b_hard,
        "stimulus_final_hard_active_ratio": s_hard,
        "baseline_final_strong_output_ratio": b_final["strong_output_ratio"],
        "stimulus_final_strong_output_ratio": s_final["strong_output_ratio"],
        "response_class": response_class,
    }


def sweep(
    config: AnivaConfig | None = None,
    total_steps: int = 1000,
    intensities: Sequence[float] = (0.01, 0.03, 0.05),
    radii: Sequence[float] = (0.5,),
    stim_starts: Sequence[int] = (300,),
    stim_durations: Sequence[int] = (100,),
    seeds: Sequence[int] = (1, 2, 3, 42, 77),
) -> list[dict]:
    """批量运行刺激响应实验，扫描多个参数组合。

    Args:
        config: 基础配置（seed 和 unit_count 会被逐次覆盖）。
        total_steps: 每组实验总步数。
        intensities: 扫描的刺激强度列表。
        radii: 扫描的刺激半径列表。
        stim_starts: 扫描的刺激开始步数列表。
        stim_durations: 扫描的刺激持续步数列表。
        seeds: 扫描的随机种子列表。

    Returns:
        list[dict]: 每行包含一组参数组合的汇总指标和 response_class。
    """
    base_config = config or AnivaConfig()
    unit_count = base_config.unit_count
    rows: list[dict] = []

    # 抑制 run() 输出：设置 report_interval 大于 total_steps
    silent = total_steps + 1

    for intensity in intensities:
        for radius in radii:
            for stim_start in stim_starts:
                for stim_duration in stim_durations:
                    for seed in seeds:
                        cfg = AnivaConfig(seed=seed, unit_count=unit_count)
                        result = exp2_stimulus.run(
                            config=cfg,
                            total_steps=total_steps,
                            stim_start=stim_start,
                            stim_duration=stim_duration,
                            stim_radius=radius,
                            stim_intensity=intensity,
                            report_interval=silent,
                        )
                        row = _extract_row(
                            result,
                            seed=seed,
                            intensity=intensity,
                            radius=radius,
                            stim_start=stim_start,
                            stim_duration=stim_duration,
                        )
                        rows.append(row)

    return rows


def _print_summary(rows: list[dict]) -> None:
    """打印扫描结果汇总表。"""
    if not rows:
        print("No results.")
        return

    # 列宽
    header = (
        f"{'seed':>5s}  {'int':>5s}  {'r':>4s}  {'start':>5s}  {'dur':>4s}  "
        f"{'stim%':>6s}  "
        f"{'dur_max':>8s}  {'dur_avg':>8s}  "
        f"{'post_f':>8s}  {'post_avg':>8s}  "
        f"{'B_act':>6s}  {'S_act':>6s}  "
        f"{'B_eng':>6s}  {'S_eng':>6s}  "
        f"{'B_hard':>6s}  {'S_hard':>6s}  "
        f"{'class':>8s}"
    )
    print(header)
    print("-" * len(header))

    for r in rows:
        print(
            f"{r['seed']:5d}  {r['stim_intensity']:5.2f}  {r['stim_radius']:4.1f}  "
            f"{r['stim_start']:5d}  {r['stim_duration']:4d}  "
            f"{r['stimulated_unit_ratio']:5.1%}  "
            f"{r['during_max_trajectory_distance']:8.5f}  "
            f"{r['during_mean_trajectory_distance']:8.5f}  "
            f"{r['post_final_trajectory_distance']:8.5f}  "
            f"{r['post_mean_trajectory_distance']:8.5f}  "
            f"{r['baseline_final_mean_activation']:6.4f}  "
            f"{r['stimulus_final_mean_activation']:6.4f}  "
            f"{r['baseline_final_mean_energy']:6.4f}  "
            f"{r['stimulus_final_mean_energy']:6.4f}  "
            f"{r['baseline_final_hard_active_ratio']:5.1%}  "
            f"{r['stimulus_final_hard_active_ratio']:5.1%}  "
            f"{r['response_class']:>8s}"
        )

    # 统计各类别数量
    classes = {"none": 0, "touch": 0, "takeover": 0}
    for r in rows:
        cls = r["response_class"]
        if cls in classes:
            classes[cls] += 1
    print(f"\nSummary: {classes['none']} none, {classes['touch']} touch, "
          f"{classes['takeover']} takeover  (out of {len(rows)} runs)")


def _save_csv(rows: list[dict], path: str) -> None:
    """将扫描结果保存为 CSV。"""
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    """命令行入口。

    Args:
        argv: 命令行参数列表。None 则使用 sys.argv[1:]。

    Returns:
        0 表示成功。
    """
    parser = argparse.ArgumentParser(
        description="Aniva 实验 2 扩展：刺激参数扫描"
    )
    parser.add_argument(
        "--intensity", type=float, nargs="+",
        default=[0.01, 0.03, 0.05],
        help="刺激强度列表（默认 0.01 0.03 0.05）"
    )
    parser.add_argument(
        "--radius", type=float, nargs="+",
        default=[0.5],
        help="刺激半径列表（默认 0.5）"
    )
    parser.add_argument(
        "--stim-start", type=int, nargs="+",
        default=[300],
        help="刺激开始步数列表（默认 300）"
    )
    parser.add_argument(
        "--stim-duration", type=int, nargs="+",
        default=[100],
        help="刺激持续步数列表（默认 100）"
    )
    parser.add_argument(
        "--seeds", type=int, nargs="+",
        default=[1, 2, 3, 42, 77],
        help="随机种子列表（默认 1 2 3 42 77）"
    )
    parser.add_argument(
        "--unit-count", type=int, default=300,
        help="活性单元数量（默认 300）"
    )
    parser.add_argument(
        "--steps", type=int, default=1000,
        help="总运行步数（默认 1000）"
    )
    parser.add_argument(
        "--output-csv", type=str, default=None,
        help="将扫描结果保存到指定 CSV 文件"
    )
    args = parser.parse_args(argv)

    base_config = AnivaConfig(unit_count=args.unit_count)

    rows = sweep(
        config=base_config,
        total_steps=args.steps,
        intensities=tuple(args.intensity),
        radii=tuple(args.radius),
        stim_starts=tuple(args.stim_start),
        stim_durations=tuple(args.stim_duration),
        seeds=tuple(args.seeds),
    )

    _print_summary(rows)

    if args.output_csv:
        _save_csv(rows, args.output_csv)
        print(f"\nSaved {len(rows)} rows to {args.output_csv}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
