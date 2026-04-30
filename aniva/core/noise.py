"""扰动 — 持续微小噪声，防止系统陷入固定稳态.

TODO（第二步实现）:
- apply_noise: 给单元的 activation 添加微小随机扰动。
- 当前仅定义接口签名，不实现任何逻辑。
"""

import numpy as np
from aniva.core.unit import Unit


def apply_noise(
    unit: Unit,
    noise_strength: float,
    rng: np.random.Generator,
) -> Unit:
    """给单元的 activation 添加微小高斯噪声。

    噪声是"蝴蝶效应"和轨迹分叉的根源。
    没有噪声 → 系统会走向固定稳态 → 死了。
    有噪声 → 系统永远有微小偏差 → 永远有新可能。

    Args:
        unit: 当前单元。
        noise_strength: 噪声强度（标准差）。
        rng: NumPy 随机数生成器。

    Returns:
        更新后的 Unit。
    """
    raise NotImplementedError("Noise not yet implemented")
