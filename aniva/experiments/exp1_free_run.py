"""实验 1：零输入自由运行观测.

启动系统，不给任何命令，记录有限步数内的状态指标。
只输出数值，不判断"是否活着"、不描述"是否有生命感"。

目标：观察当前机制在零输入下的客观行为。
"""

import argparse
import csv
import sys

from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.observer import Observer


def run(
    config: AnivaConfig | None = None,
    total_steps: int = 1000,
    report_interval: int = 100,
) -> dict:
    """运行自由观测实验。

    Args:
        config: 生命核配置。None 则使用默认配置。
        total_steps: 总运行步数。
        report_interval: 每隔多少步打印一次指标。

    Returns:
        dict: {
            "config_seed": int,
            "total_steps": int,
            "final_metrics": dict,
            "history": list[dict],
        }
    """
    if config is None:
        config = AnivaConfig()
    core = LifeCore(config)
    obs = Observer(core)
    history: list[dict] = []

    for step in range(total_steps):
        core.step()
        metrics = obs.get_metrics()
        history.append(metrics)
        if (step + 1) % report_interval == 0:
            _print_metrics(metrics)

    final_metrics = obs.get_metrics()
    return {
        "config_seed": config.seed,
        "total_steps": total_steps,
        "final_metrics": final_metrics,
        "history": history,
    }


def _print_metrics(m: dict) -> None:
    """打印指标到 stdout——只输出数值，不做评价."""
    print(
        f"step={m['step']:5d} | "
        f"act: mean={m['mean_activation']:.4f} max={m['max_activation']:.4f} "
        f"min={m['min_activation']:.4f} | "
        f"energy: mean={m['mean_energy']:.4f} min={m['min_energy']:.4f} | "
        f"trace: mean={m['mean_trace']:.4f} | "
        f"active: {m['active_unit_ratio']:.2%} | "
        f"syn: src_active={m['source_active_ratio']:.2%} "
        f"in_mean={m['mean_abs_synaptic_input']:.6f} "
        f"in_max={m['max_abs_synaptic_input']:.4f}"
    )


def _save_csv(history: list[dict], path: str) -> None:
    """将 metrics history 保存为 CSV 文件."""
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
        description="Aniva 实验 1：零输入自由运行观测"
    )
    parser.add_argument(
        "--steps", type=int, default=1000,
        help="总运行步数（默认 1000）"
    )
    parser.add_argument(
        "--report-interval", type=int, default=100,
        help="每隔多少步打印指标（默认 100）"
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
        "--output-csv", type=str, default=None,
        help="将 metrics history 保存到指定 CSV 文件"
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
        report_interval=args.report_interval,
    )

    if args.output_csv:
        _save_csv(result["history"], args.output_csv)
        print(f"Saved {len(result['history'])} rows to {args.output_csv}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
