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
        """返回当前生命核的状态快照（原始数据）。

        Returns:
            dict: {
                "step": 当前步数,
                "activations": (unit_count,) array,
                "energies": (unit_count,) array,
                "traces": (unit_count,) array,
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

    def get_metrics(self) -> dict:
        """返回当前生命核的聚合指标。

        不做解释，不判断"是否活着"——只记录客观数值。

        Returns:
            dict: {
                "step": int,
                "mean_activation": float,
                "max_activation": float,
                "min_activation": float,
                "mean_energy": float,
                "min_energy": float,
                "mean_trace": float,
                "active_unit_ratio": float,  # activation > threshold 的比例
            }
        """
        activations = np.array([u.activation for u in self._core.units.values()])
        energies = np.array([u.energy for u in self._core.units.values()])
        traces = np.array([u.trace for u in self._core.units.values()])
        thresholds = np.array([u.threshold for u in self._core.units.values()])
        active_mask = activations > thresholds
        return {
            "step": self._core.step_count,
            "mean_activation": float(np.mean(activations)),
            "max_activation": float(np.max(activations)),
            "min_activation": float(np.min(activations)),
            "mean_energy": float(np.mean(energies)),
            "min_energy": float(np.min(energies)),
            "mean_trace": float(np.mean(traces)),
            "active_unit_ratio": float(np.mean(active_mask)),
        }
