"""实验 2：环境刺激响应.

对比无刺激 baseline 和点刺激条件下的轨迹差异。
验证：
- 刺激后状态分布变化
- 刺激移除后不会完全回到 baseline 轨迹
- 不同条件下出现可观测差异

只使用已有 API，不修改任何核心机制。
"""

import argparse
import csv
import sys
import numpy as np

from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.observer import Observer
from aniva.environment.environment import Stimulus, StimulusEvent, Environment


def _trajectory_distance(core_a: LifeCore, core_b: LifeCore) -> float:
    """计算两个生命核 activation 向量之间的平均绝对差。"""
    acts_a = np.array([u.activation for u in core_a.units.values()])
    acts_b = np.array([u.activation for u in core_b.units.values()])
    return float(np.mean(np.abs(acts_a - acts_b)))


def _avg_metrics(metrics_list: list[dict]) -> dict:
    """对一组 metrics dict 求平均。"""
    if not metrics_list:
        return {}
    keys = [
        "mean_activation", "mean_energy", "hard_active_ratio",
        "strong_output_ratio", "mean_abs_synaptic_input",
    ]
    result = {}
    for key in keys:
        result[key] = float(np.mean([m[key] for m in metrics_list]))
    return result


def run(
    config: AnivaConfig | None = None,
    total_steps: int = 1000,
    stim_start: int = 300,
    stim_duration: int = 100,
    stim_radius: float = 0.5,
    stim_intensity: float = 0.03,
    report_interval: int = 100,
) -> dict:
    """运行环境刺激响应对比实验。

    创建两个同 seed 的 LifeCore：
    - baseline: 全程无刺激
    - stimulus: 在 [stim_start, stim_start + stim_duration) 之间施加点刺激

    Args:
        config: 生命核配置。None 则使用默认配置。
        total_steps: 总运行步数。
        stim_start: 刺激开始步数。
        stim_duration: 刺激持续步数。
        stim_radius: 刺激影响半径。
        stim_intensity: 刺激强度（保守默认 0.03）。
        report_interval: 每隔多少步打印指标。

    Returns:
        dict: 包含 phase_summaries, trajectory_history 等完整结果。
    """
    if config is None:
        config = AnivaConfig()

    baseline_core = LifeCore(config)
    stimulus_core = LifeCore(config)
    baseline_obs = Observer(baseline_core)
    stimulus_obs = Observer(stimulus_core)

    env = Environment()
    env.add_event(StimulusEvent(
        stimulus=Stimulus(
            position=(0.0, 0.0, 0.0),
            intensity=stim_intensity,
            radius=stim_radius,
        ),
        start_step=stim_start,
        duration_steps=stim_duration,
    ))

    # 计算受影响单元比例（刺激开始时的快照）
    influences_snapshot = env.compute_influences(stimulus_core.units, stim_start)
    stimulated_unit_ratio = len(influences_snapshot) / config.unit_count

    # 按阶段累积 metrics
    phase_metrics: dict[str, dict[str, list[dict]]] = {
        "pre_stimulus": {"baseline": [], "stimulus": []},
        "during_stimulus": {"baseline": [], "stimulus": []},
        "post_stimulus": {"baseline": [], "stimulus": []},
    }
    trajectory_history: list[dict] = []

    stim_end = stim_start + stim_duration

    for step in range(total_steps):
        if step < stim_start:
            phase = "pre_stimulus"
        elif step < stim_end:
            phase = "during_stimulus"
        else:
            phase = "post_stimulus"

        # Baseline: 全程无刺激
        baseline_core.step(env_influences=None)
        b_metrics = baseline_obs.get_metrics()

        # Stimulus: 仅在 during_stimulus 阶段施加刺激
        if phase == "during_stimulus":
            influences = env.compute_influences(stimulus_core.units, step)
        else:
            influences = None
        stimulus_core.step(env_influences=influences)
        s_metrics = stimulus_obs.get_metrics()

        phase_metrics[phase]["baseline"].append(b_metrics)
        phase_metrics[phase]["stimulus"].append(s_metrics)

        traj_dist = _trajectory_distance(baseline_core, stimulus_core)
        trajectory_history.append({
            "step": step,
            "phase": phase,
            "trajectory_distance": traj_dist,
        })

        if (step + 1) % report_interval == 0:
            _print_step(step + 1, phase, b_metrics, s_metrics, traj_dist)

    # 汇总各阶段平均指标
    phase_summaries = {}
    for phase in ["pre_stimulus", "during_stimulus", "post_stimulus"]:
        b_avg = _avg_metrics(phase_metrics[phase]["baseline"])
        s_avg = _avg_metrics(phase_metrics[phase]["stimulus"])
        phase_summaries[phase] = {
            "baseline": b_avg,
            "stimulus": s_avg,
            "step_count": len(phase_metrics[phase]["baseline"]),
        }

    return {
        "config_seed": config.seed,
        "total_steps": total_steps,
        "unit_count": config.unit_count,
        "stim_start": stim_start,
        "stim_duration": stim_duration,
        "stim_radius": stim_radius,
        "stim_intensity": stim_intensity,
        "final_baseline_metrics": baseline_obs.get_metrics(),
        "final_stimulus_metrics": stimulus_obs.get_metrics(),
        "phase_summaries": phase_summaries,
        "trajectory_history": trajectory_history,
        "stimulated_unit_ratio": stimulated_unit_ratio,
    }


def _print_step(
    step: int, phase: str,
    b: dict, s: dict, traj_dist: float,
) -> None:
    """打印单步对比指标。"""
    print(
        f"step={step:5d} [{phase:>16s}] | "
        f"B-act={b['mean_activation']:.4f} S-act={s['mean_activation']:.4f} | "
        f"B-eng={b['mean_energy']:.4f} S-eng={s['mean_energy']:.4f} | "
        f"B-hard={b['hard_active_ratio']:.2%} S-hard={s['hard_active_ratio']:.2%} | "
        f"B-strong={b['strong_output_ratio']:.2%} S-strong={s['strong_output_ratio']:.2%} | "
        f"traj_dist={traj_dist:.6f}"
    )


def _save_csv(history: list[dict], path: str) -> None:
    """将 trajectory history 保存为 CSV 文件."""
    if not history:
        return
    fieldnames = list(history[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(history)


def main(argv: list[str] | None = None) -> int:
    """命令行入口。

    Args:
        argv: 命令行参数列表。None 则使用 sys.argv[1:]。

    Returns:
        0 表示成功。
    """
    parser = argparse.ArgumentParser(
        description="Aniva 实验 2：环境刺激响应对比"
    )
    parser.add_argument(
        "--steps", type=int, default=1000,
        help="总运行步数（默认 1000）"
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="随机种子（默认 42）"
    )
    parser.add_argument(
        "--unit-count", type=int, default=None,
        help="活性单元数量（默认 300）"
    )
    parser.add_argument(
        "--stim-start", type=int, default=300,
        help="刺激开始步数（默认 300）"
    )
    parser.add_argument(
        "--stim-duration", type=int, default=100,
        help="刺激持续步数（默认 100）"
    )
    parser.add_argument(
        "--stim-radius", type=float, default=0.5,
        help="刺激影响半径（默认 0.5）"
    )
    parser.add_argument(
        "--stim-intensity", type=float, default=0.03,
        help="刺激强度（默认 0.03）"
    )
    parser.add_argument(
        "--report-interval", type=int, default=100,
        help="每隔多少步打印指标（默认 100）"
    )
    parser.add_argument(
        "--output-csv", type=str, default=None,
        help="将 trajectory history 保存到指定 CSV 文件"
    )
    args = parser.parse_args(argv)

    config = AnivaConfig()
    if args.seed is not None:
        config.seed = args.seed
    if args.unit_count is not None:
        config.unit_count = args.unit_count

    result = run(
        config=config,
        total_steps=args.steps,
        stim_start=args.stim_start,
        stim_duration=args.stim_duration,
        stim_radius=args.stim_radius,
        stim_intensity=args.stim_intensity,
        report_interval=args.report_interval,
    )

    # 打印阶段汇总
    print()
    print("=" * 70)
    print("Phase Summaries (averaged over phase steps)")
    print("=" * 70)
    for phase, summary in result["phase_summaries"].items():
        if summary["step_count"] == 0:
            continue
        b = summary["baseline"]
        s = summary["stimulus"]
        print(f"\n--- {phase} ({summary['step_count']} steps) ---")
        print(f"  baseline:  act={b['mean_activation']:.4f}  "
              f"eng={b['mean_energy']:.4f}  "
              f"hard={b['hard_active_ratio']:.2%}  "
              f"strong={b['strong_output_ratio']:.2%}")
        print(f"  stimulus:  act={s['mean_activation']:.4f}  "
              f"eng={s['mean_energy']:.4f}  "
              f"hard={s['hard_active_ratio']:.2%}  "
              f"strong={s['strong_output_ratio']:.2%}")
    print(f"\nstimulated_unit_ratio: {result['stimulated_unit_ratio']:.2%}")
    print(f"({result['stimulated_unit_ratio'] * result['unit_count']:.0f} / "
          f"{result['unit_count']} units in stimulus radius)")

    if args.output_csv:
        _save_csv(result["trajectory_history"], args.output_csv)
        print(f"\nSaved {len(result['trajectory_history'])} rows "
              f"to {args.output_csv}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
