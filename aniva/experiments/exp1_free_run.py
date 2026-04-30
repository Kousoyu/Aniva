"""实验 1：零输入自由运行观测.

启动系统，不给任何命令，记录有限步数内的状态指标。
只输出数值，不判断"是否活着"、不描述"是否有生命感"。

目标：观察当前机制在零输入下的客观行为。
"""

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
            "final_metrics": dict,   # 最后一步的指标
            "history": list[dict],   # 每一步的指标（可复现性用）
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
        f"active: {m['active_unit_ratio']:.2%}"
    )
