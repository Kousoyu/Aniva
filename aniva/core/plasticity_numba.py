"""Numba-accelerated plasticity kernel — 可选后端。

通过 @njit 编译 plasticity 循环，消除 Python 解释器开销。
默认不启用，由 AnivaConfig.use_numba_plasticity 控制。

接入方式：LifeCore.step() 在开关打开且 Numba 可用时调用本模块，
Numba 原地更新 _weight_cache，然后同步回 Connection.weight。
"""

import numpy as np

try:
    from numba import njit
    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False


if NUMBA_AVAILABLE:

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
    def _apply_plasticity_numba_kernel(
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
        """Numba-compiled plasticity kernel — 原地修改 weights。"""
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


def apply_plasticity_numba(
    source_indices: np.ndarray,
    target_indices: np.ndarray,
    weight_cache: np.ndarray,
    activations: np.ndarray,
    thresholds: np.ndarray,
    energies: np.ndarray,
    plasticity_rate: float,
    threshold_softness: float,
    dt: float,
) -> None:
    """Numba-accelerated plasticity — 原地修改 weight_cache。

    与 apply_plasticity 逻辑逐位等价，但直接操作权重数组而非 Connection 对象。

    Args:
        source_indices: shape (n_connections,) dtype int64。
        target_indices: shape (n_connections,) dtype int64。
        weight_cache: shape (n_connections,) dtype float64，原地修改。
        activations: shape (n_units,) dtype float64。
        thresholds: shape (n_units,) dtype float64。
        energies: shape (n_units,) dtype float64。
        plasticity_rate: 变化速率。
        threshold_softness: 软阈值宽度。
        dt: 时间步长。

    Raises:
        RuntimeError: Numba 不可用时调用。
    """
    if not NUMBA_AVAILABLE:
        raise RuntimeError(
            "Numba plasticity requested but numba is not installed. "
            "Run: pip install numba"
        )
    _apply_plasticity_numba_kernel(
        source_indices, target_indices, weight_cache,
        activations, thresholds, energies,
        plasticity_rate, threshold_softness, dt,
    )
