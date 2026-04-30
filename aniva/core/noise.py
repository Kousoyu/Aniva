"""扰动 — 持续微小噪声，防止系统陷入固定稳态.

噪声是"蝴蝶效应"和轨迹分叉的根源。
没有噪声 → 系统会走向固定稳态 → 死了。
有噪声 → 系统永远有微小偏差 → 永远有新可能。

采用高斯噪声，乘以 sqrt(dt) 保证时间一致性。
"""

import numpy as np
from aniva.core.unit import Unit


def apply_noise(
    unit: Unit,
    noise_strength: float,
    dt: float,
    rng: np.random.Generator,
) -> Unit:
    """给单元的 activation 添加微小高斯噪声。

    delta = N(0, noise_strength) * sqrt(dt)
    sqrt(dt) 确保噪声的方差与时间步长成正比，是 SDE 数值积分的标准做法。

    activation 被 clamp 在 [0, 1]——噪声不会把系统推出物理边界。

    Args:
        unit: 当前单元。
        noise_strength: 噪声强度（标准差）。
        dt: 时间步长。
        rng: NumPy 随机数生成器（保证可复现性）。

    Returns:
        更新后的 Unit（原位修改并返回）。
    """
    delta = rng.normal(0.0, noise_strength) * (dt ** 0.5)
    unit.activation = max(0.0, min(1.0, unit.activation + delta))
    return unit
