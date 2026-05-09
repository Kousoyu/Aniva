"""Numba plasticity prototype — benchmark-only，不接入主路径。

目标：回答一个问题 — 如果 plasticity loop 用 Numba 编译，理论加速比有多大？

用法：
    python -m aniva.experiments.benchmark_plasticity_numba
    python -m aniva.experiments.benchmark_plasticity_numba --quick

要求：
    pip install numba  (本脚本不自动安装，不修改项目依赖)
"""

import argparse
import sys
import time
import numpy as np

from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.core.plasticity import apply_plasticity


# === Numba kernel ===
# 放在 try 块外以便 Numba 编译失败时有清晰报错
try:
    from numba import njit
    _HAS_NUMBA = True
except ImportError:
    _HAS_NUMBA = False


if _HAS_NUMBA:

    @njit
    def _output_strength_numba(
        activation: float, threshold: float, softness: float
    ) -> float:
        x = (activation - threshold) / softness
        if x < -60.0:
            x = -60.0
        elif x > 60.0:
            x = 60.0
        gate = 1.0 / (1.0 + np.exp(-x))
        return activation * gate

    @njit
    def apply_plasticity_numba(
        source_ids: np.ndarray,
        target_ids: np.ndarray,
        weights: np.ndarray,
        activations: np.ndarray,
        thresholds: np.ndarray,
        energies: np.ndarray,
        plasticity_rate: float,
        threshold_softness: float,
        dt: float,
    ) -> None:
        """Numba 编译的 plasticity kernel。

        原地修改 weights 数组。逻辑与 apply_plasticity 逐位等价。
        """
        decay_rate = plasticity_rate * 0.5
        n = len(source_ids)

        for i in range(n):
            sid = source_ids[i]
            tid = target_ids[i]

            src_str = _output_strength_numba(
                activations[sid], thresholds[sid], threshold_softness
            )
            tgt_str = _output_strength_numba(
                activations[tid], thresholds[tid], threshold_softness
            )
            coactivity = src_str * tgt_str

            e_src = energies[sid]
            e_tgt = energies[tid]
            energy_gate = e_src if e_src < e_tgt else e_tgt

            delta = plasticity_rate * coactivity * dt * energy_gate
            w = weights[i]
            if w >= 0.0:
                w += delta
            else:
                w -= delta

            w *= 1.0 - decay_rate * dt

            if w < -1.0:
                w = -1.0
            elif w > 1.0:
                w = 1.0

            weights[i] = w


def _extract_connection_arrays(core: LifeCore) -> dict:
    """从 LifeCore 提取 connection 数据为纯数组（Numba 输入）。"""
    n = len(core.connections)
    source_ids = np.empty(n, dtype=np.int64)
    target_ids = np.empty(n, dtype=np.int64)
    weights = np.empty(n, dtype=np.float64)
    for i, conn in enumerate(core.connections):
        source_ids[i] = conn.source_id
        target_ids[i] = conn.target_id
        weights[i] = conn.weight
    return {
        "source_ids": source_ids,
        "target_ids": target_ids,
        "weights": weights,
    }


def _check_equivalence(
    conn_arrays: dict,
    activations: np.ndarray,
    thresholds: np.ndarray,
    energies: np.ndarray,
    plasticity_rate: float,
    threshold_softness: float,
    dt: float,
    core: LifeCore,
) -> bool:
    """验证 Numba kernel 与 scalar reference 数值等价。"""
    # 重置连接权重到相同初始状态
    initial_weights = np.array([c.weight for c in core.connections], dtype=np.float64)

    # === Scalar ===
    for conn in core.connections:
        conn.weight = initial_weights[conn.cid]

    apply_plasticity(
        core.connections,
        activations.copy(), thresholds.copy(), energies.copy(),
        plasticity_rate, threshold_softness, dt,
    )
    weights_scalar = np.array([c.weight for c in core.connections], dtype=np.float64)

    # === Numba ===
    weights_numba = initial_weights.copy()
    apply_plasticity_numba(
        conn_arrays["source_ids"],
        conn_arrays["target_ids"],
        weights_numba,
        activations, thresholds, energies,
        plasticity_rate, threshold_softness, dt,
    )

    # 恢复连接权重（不留下副作用）
    for conn in core.connections:
        conn.weight = initial_weights[conn.cid]

    # 比较
    close = np.allclose(weights_scalar, weights_numba, rtol=1e-12, atol=1e-12)
    if not close:
        diff = np.abs(weights_scalar - weights_numba)
        print(f"  MISMATCH: max_diff={diff.max():.2e}, "
              f"mean_diff={diff.mean():.2e}, "
              f"n_differ={np.sum(diff > 1e-12)}/{len(diff)}")
    return close


def _benchmark_kernel(
    name: str,
    fn,
    n_warmup: int,
    n_iters: int,
    *args,
) -> dict:
    """运行单次 benchmark，返回耗时和吞吐。"""
    # Warmup
    for _ in range(n_warmup):
        fn(*args)

    t0 = time.perf_counter()
    for _ in range(n_iters):
        fn(*args)
    elapsed = time.perf_counter() - t0

    return {
        "name": name,
        "n_iters": n_iters,
        "elapsed_sec": elapsed,
        "ms_per_call": 1000 * elapsed / n_iters,
    }


def run_benchmark(quick: bool = False) -> dict:
    """运行 Numba plasticity benchmark。

    Returns:
        dict 包含：equivalence、scalar_time、numba_time、speedup。
    """
    if not _HAS_NUMBA:
        return {"error": "Numba not installed. Run: pip install numba"}

    n_units = 100 if quick else 300
    n_iters = 200 if quick else 500
    n_warmup = 10 if quick else 20

    cfg = AnivaConfig(
        unit_count=n_units, seed=42,
        plasticity_rate=0.0001,
        homeostasis_enabled=False,
    )
    core = LifeCore(cfg)

    # Warmup core
    for _ in range(50):
        core.step()

    # 提取输入数组
    acts = core._activations.copy()
    thrs = core._thresholds.copy()
    engs = core._energies.copy()
    conn_arrays = _extract_connection_arrays(core)

    plasticity_rate = 0.0001
    threshold_softness = 0.02
    dt = 0.5

    result = {
        "unit_count": n_units,
        "connection_count": core.connection_count,
        "n_iters": n_iters,
        "has_numba": True,
    }

    # 1. 等价性验证
    equivalent = _check_equivalence(
        conn_arrays, acts, thrs, engs,
        plasticity_rate, threshold_softness, dt,
        core,
    )
    result["scalar_numba_equivalent"] = equivalent
    if not equivalent:
        result["error"] = "Equivalence check failed — Numba output != scalar output"
        return result

    # 预热 Numba JIT
    weights_warm = conn_arrays["weights"].copy()
    apply_plasticity_numba(
        conn_arrays["source_ids"], conn_arrays["target_ids"],
        weights_warm, acts, thrs, engs,
        plasticity_rate, threshold_softness, dt,
    )

    # 统一初始状态：scalar 和 numba 从相同 weights 出发
    for i, conn in enumerate(core.connections):
        conn.weight = conn_arrays["weights"][i]
    weights_buf = conn_arrays["weights"].copy()

    # 2. Scalar benchmark
    def run_scalar():
        apply_plasticity(
            core.connections,
            acts, thrs, engs,
            plasticity_rate, threshold_softness, dt,
        )

    scalar_r = _benchmark_kernel("scalar", run_scalar, n_warmup, n_iters)

    # 3. Numba benchmark — 注意重新从初始状态出发
    weights_buf[:] = conn_arrays["weights"]

    def run_numba():
        apply_plasticity_numba(
            conn_arrays["source_ids"], conn_arrays["target_ids"],
            weights_buf, acts, thrs, engs,
            plasticity_rate, threshold_softness, dt,
        )

    numba_r = _benchmark_kernel("numba", run_numba, n_warmup, n_iters)

    result["scalar_ms_per_call"] = scalar_r["ms_per_call"]
    result["numba_ms_per_call"] = numba_r["ms_per_call"]
    result["speedup"] = scalar_r["ms_per_call"] / numba_r["ms_per_call"] if numba_r["ms_per_call"] > 0 else 0

    return result


def print_results(result: dict) -> None:
    """打印 benchmark 结果。"""
    print()
    print("=" * 62)
    print("Numba Plasticity Benchmark")
    print("=" * 62)

    if "error" in result:
        print(f"\n  {result['error']}")
        return

    print(f"\n  units: {result['unit_count']}, "
          f"connections: {result['connection_count']}, "
          f"iterations: {result['n_iters']}")

    eq = "PASS" if result.get("scalar_numba_equivalent") else "FAIL"
    print(f"  scalar vs numba equivalence: {eq}")

    if not result.get("scalar_numba_equivalent"):
        print("\n  Equivalence check failed — skipping performance comparison.")
        return

    su = result["speedup"]
    print(f"\n  scalar:  {result['scalar_ms_per_call']:.4f} ms/call")
    print(f"  numba:   {result['numba_ms_per_call']:.4f} ms/call")
    print(f"  speedup: {su:.1f}x")

    # 定性判断
    if su >= 10:
        label = "EXCELLENT — Numba 接入主路径价值很高"
    elif su >= 5:
        label = "GOOD — 达到 5x 门槛，值得接入"
    elif su >= 2:
        label = "MODERATE — 有一定提升但未达 5x 门槛"
    else:
        label = "NEGLIGIBLE — 不值得引入 Numba 依赖"
    print(f"  verdict: {label}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Aniva plasticity Numba prototype benchmark"
    )
    parser.add_argument("--quick", action="store_true",
                        help="快速模式（100 units，200 iters）")
    args = parser.parse_args(argv)

    result = run_benchmark(quick=args.quick)
    print_results(result)

    if "error" in result:
        return 0  # 优雅退出，不算失败
    return 0 if result.get("scalar_numba_equivalent") else 1


if __name__ == "__main__":
    sys.exit(main())
