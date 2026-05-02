"""LifeCore step 性能基准测试。

通过配置组合推算各阶段开销，不改 LifeCore 内部代码。

用法:
    python -m aniva.experiments.benchmark_core
    python -m aniva.experiments.benchmark_core --quick  # 快速模式
"""

import argparse
import sys
import time
import numpy as np

from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.environment.environment import Stimulus, StimulusEvent, Environment


def _make_env(duration: int) -> Environment:
    """创建带持续刺激的环境。"""
    env = Environment()
    stim = Stimulus(position=(0.0, 0.0, 0.0), intensity=0.03, radius=0.5)
    env.add_event(StimulusEvent(
        stimulus=stim, start_step=0, duration_steps=duration,
    ))
    return env


def _time_run(
    unit_count: int,
    n_steps: int = 1000,
    plasticity_rate: float = 0.0001,
    homeostasis: bool = True,
    with_env: bool = False,
    warmup: int = 100,
) -> dict:
    """运行并计时，返回性能指标。"""
    cfg = AnivaConfig(
        unit_count=unit_count,
        seed=42,
        plasticity_rate=plasticity_rate,
        homeostasis_enabled=homeostasis,
    )
    core = LifeCore(cfg)
    env = _make_env(n_steps + warmup) if with_env else None

    # 预热
    for step in range(warmup):
        influences = env.compute_influences(core.units, step) if env else None
        core.step(env_influences=influences)

    # 计时
    t0 = time.perf_counter()
    for step in range(warmup, warmup + n_steps):
        influences = env.compute_influences(core.units, step) if env else None
        core.step(env_influences=influences)
    elapsed = time.perf_counter() - t0

    return {
        "unit_count": unit_count,
        "connection_count": core.connection_count,
        "n_steps": n_steps,
        "elapsed_sec": elapsed,
        "steps_per_sec": n_steps / elapsed if elapsed > 0 else 0,
        "ms_per_step": 1000 * elapsed / n_steps if n_steps > 0 else 0,
    }


def run_benchmark(quick: bool = False) -> list[dict]:
    """运行性能基准，返回结果列表。

    通过组合变化推算:
      - 全开 baseline
      - plasticity=0 → 无 plasticity cost
      - homeostasis=off → 无 homeostasis cost
      - env=off → 无环境计算
    """
    if quick:
        unit_sizes = [100, 300]
        step_counts = [500]
    else:
        unit_sizes = [100, 300, 500]
        step_counts = [1000, 5000]

    results = []

    for units in unit_sizes:
        for steps in step_counts:
            # 全开 baseline
            r_full = _time_run(units, steps, plasticity_rate=0.0001,
                              homeostasis=True, with_env=True)
            r_full["config"] = "full"
            results.append(r_full)

            # 无 plasticity
            r_nop = _time_run(units, steps, plasticity_rate=0.0,
                             homeostasis=True, with_env=True)
            r_nop["config"] = "no_plasticity"
            results.append(r_nop)

            # 无 homeostasis
            r_noh = _time_run(units, steps, plasticity_rate=0.0001,
                             homeostasis=False, with_env=True)
            r_noh["config"] = "no_homeostasis"
            results.append(r_noh)

            # 无环境
            r_noe = _time_run(units, steps, plasticity_rate=0.0001,
                             homeostasis=True, with_env=False)
            r_noe["config"] = "no_environment"
            results.append(r_noe)

    return results


def print_results(results: list[dict]) -> None:
    """打印基准结果表格和成本分解。"""
    print()
    print("=" * 72)
    print("LifeCore Step Performance Benchmark")
    print("=" * 72)

    # 按 unit_count 分组
    by_units: dict[int, dict[str, dict]] = {}
    for r in results:
        uc = r["unit_count"]
        if uc not in by_units:
            by_units[uc] = {}
        by_units[uc][r["config"]] = r

    for uc in sorted(by_units):
        configs = by_units[uc]
        full = configs.get("full")
        if not full:
            continue

        print(f"\n--- unit_count={uc}, "
              f"connections={full['connection_count']}, "
              f"steps={full['n_steps']} ---")

        # 总览
        print(f"  {'config':<20s} {'elapsed':>7s}  {'steps/s':>8s}  {'ms/step':>8s}")
        print(f"  {'-'*20} {'-'*7}  {'-'*8}  {'-'*8}")
        order = ["full", "no_plasticity", "no_homeostasis", "no_environment"]
        for cfg_name in order:
            r = configs.get(cfg_name)
            if r:
                print(f"  {cfg_name:<20s} {r['elapsed_sec']:6.2f}s  "
                      f"{r['steps_per_sec']:8.1f}  {r['ms_per_step']:7.3f}ms")

        # 近似成本分解
        print(f"\n  Approximate cost breakdown (per step):")
        full_ms = full["ms_per_step"]
        print(f"    full:               {full_ms:.3f}ms  (100.0%)")

        nop = configs.get("no_plasticity")
        if nop and full_ms > 0:
            plasticity_ms = full_ms - nop["ms_per_step"]
            plasticity_pct = 100 * plasticity_ms / full_ms
            print(f"    plasticity:         {plasticity_ms:.3f}ms  ({plasticity_pct:5.1f}%)")

        noh = configs.get("no_homeostasis")
        if noh and full_ms > 0:
            homeo_ms = full_ms - noh["ms_per_step"]
            homeo_pct = 100 * homeo_ms / full_ms
            print(f"    homeostasis:        {homeo_ms:.3f}ms  ({homeo_pct:5.1f}%)")

        noe = configs.get("no_environment")
        if noe and full_ms > 0:
            env_ms = full_ms - noe["ms_per_step"]
            env_pct = 100 * env_ms / full_ms
            print(f"    environment:        {env_ms:.3f}ms  ({env_pct:5.1f}%)")

        # 其余是 synaptic + noise + leak + energy + trace
        if nop and noh and noe and full_ms > 0:
            other_ms = full_ms - plasticity_ms - homeo_ms - env_ms
            other_pct = 100 * other_ms / full_ms
            print(f"    synaptic+etc:       {other_ms:.3f}ms  ({other_pct:5.1f}%)")

        # 单步等效连接操作数
        conn_count = full["connection_count"]
        if full["steps_per_sec"] > 0:
            conn_per_sec = conn_count * full["steps_per_sec"]
            print(f"\n    connections:        {conn_count}")
            print(f"    conn·steps/sec:     {conn_per_sec:,.0f}")

    # 缩放性总结
    print(f"\n--- Scaling ---")
    for steps in sorted(set(r["n_steps"] for r in results)):
        print(f"\n  steps={steps}:")
        for uc in sorted(by_units):
            full = by_units[uc].get("full")
            if full and full["n_steps"] == steps:
                print(f"    units={uc:4d}  conns={full['connection_count']:5d}  "
                      f"steps/s={full['steps_per_sec']:.0f}  "
                      f"ms/step={full['ms_per_step']:.2f}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Aniva LifeCore 性能基准"
    )
    parser.add_argument("--quick", action="store_true",
                       help="快速模式（仅 100/300 units，500 steps）")
    args = parser.parse_args(argv)

    print("Running LifeCore benchmark...")
    results = run_benchmark(quick=args.quick)
    print_results(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
