"""状态观测器 — 提取生命核的快照数据.

Observer 不做任何修改，只负责读取和记录。
"""

import numpy as np
from aniva.life_core import LifeCore


class Observer:
    """观察 LifeCore 的内部状态，提供快照接口。

    不做任何写操作，只读。
    """

    def __init__(self, core: LifeCore):
        self._core = core

    def snapshot(self) -> dict:
        """返回当前生命核的状态快照。

        Returns:
            dict: {
                "step": 当前步数,
                "activations": (unit_count,) array — 所有单元的 activation,
                "energies": (unit_count,) array — 所有单元的 energy,
                "traces": (unit_count,) array — 所有单元的 trace,
                "mean_activation": 平均 activation,
                "mean_energy": 平均 energy,
            }
        """
        activations = np.array([u.activation for u in self._core.units.values()])
        energies = np.array([u.energy for u in self._core.units.values()])
        traces = np.array([u.trace for u in self._core.units.values()])
        return {
            "step": self._core.step_count,
            "activations": activations,
            "energies": energies,
            "traces": traces,
            "mean_activation": float(np.mean(activations)),
            "mean_energy": float(np.mean(energies)),
        }
