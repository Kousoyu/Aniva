"""状态观测器 — 提取生命核的快照数据.

Observer 不做任何修改，只负责读取和记录。
"""

import numpy as np
from aniva.life_core import LifeCore
from aniva.core.dynamics import compute_synaptic_input


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
            dict: 包含 activation/energy/trace/突触诊断等聚合指标。
        """
        activations = np.array([u.activation for u in self._core.units.values()])
        energies = np.array([u.energy for u in self._core.units.values()])
        traces = np.array([u.trace for u in self._core.units.values()])
        thresholds = np.array([u.threshold for u in self._core.units.values()])
        active_mask = activations > thresholds
        mean_act = float(np.mean(activations))
        mean_thresh = float(np.mean(thresholds))

        # 突触诊断：当前状态下网络的传导情况（使用软阈值）
        softness = self._core.config.threshold_softness
        x = (activations - thresholds) / softness
        x = np.clip(x, -60.0, 60.0)
        gate = 1.0 / (1.0 + np.exp(-x))
        effective_outputs = activations * gate
        soft_output_mask = effective_outputs > 1e-8
        strong_output_mask = effective_outputs > 0.01
        syn_inputs = compute_synaptic_input(self._core.connections, self._core.units, self._core.config.threshold_softness)
        syn_values = np.array(list(syn_inputs.values())) if syn_inputs else np.array([])
        abs_syn = np.abs(syn_values) if len(syn_values) > 0 else syn_values

        hard_active = float(np.mean(active_mask))
        soft_out = float(np.mean(soft_output_mask))
        strong_out = float(np.mean(strong_output_mask))

        return {
            "step": self._core.step_count,
            "mean_activation": mean_act,
            "max_activation": float(np.max(activations)),
            "min_activation": float(np.min(activations)),
            "mean_energy": float(np.mean(energies)),
            "min_energy": float(np.min(energies)),
            "mean_trace": float(np.mean(traces)),
            # 强激活：activation > threshold
            "active_unit_ratio": hard_active,
            "hard_active_ratio": hard_active,
            "mean_threshold": mean_thresh,
            "min_threshold": float(np.min(thresholds)),
            "max_threshold": float(np.max(thresholds)),
            "mean_activation_to_threshold_ratio": (
                mean_act / mean_thresh if mean_thresh > 0 else 0.0
            ),
            # 突触输出分层
            "soft_output_ratio": soft_out,
            "strong_output_ratio": strong_out,
            "mean_effective_output": float(np.mean(effective_outputs)),
            "max_effective_output": float(np.max(effective_outputs)),
            "mean_abs_synaptic_input": float(np.mean(abs_syn)) if len(abs_syn) > 0 else 0.0,
            "max_abs_synaptic_input": float(np.max(abs_syn)) if len(abs_syn) > 0 else 0.0,
            "synaptic_target_ratio": float(len(syn_inputs) / len(self._core.units)) if self._core.units else 0.0,
            # 兼容旧字段
            "source_active_ratio": soft_out,
        }
