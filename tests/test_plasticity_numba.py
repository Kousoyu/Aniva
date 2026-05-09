"""Numba plasticity 集成测试 — 验证 Numba 路径与 scalar 路径等价且安全。

Numba 不可用时通过 pytest.importorskip 跳过。
"""

import numpy as np
import pytest

pytest.importorskip("numba")

from aniva.config import AnivaConfig
from aniva.core.connection import Connection
from aniva.core.plasticity import apply_plasticity
from aniva.core.plasticity_numba import apply_plasticity_numba, NUMBA_AVAILABLE
from aniva.life_core import LifeCore


class TestNumbaScalarEquivalence:
    """Numba kernel 与 scalar apply_plasticity 逐位等价。"""

    def test_single_step_allclose(self):
        """单步 plasticity 后权重 allclose。"""
        cfg = AnivaConfig(unit_count=50, seed=42, plasticity_rate=0.01)
        core = LifeCore(cfg)
        # Warmup 让状态不全是零
        for _ in range(30):
            core.step()

        # 保存初始权重
        init_weights = np.array([c.weight for c in core.connections], dtype=np.float64)

        # === Scalar ===
        for conn in core.connections:
            conn.weight = init_weights[conn.cid]
        apply_plasticity(
            core.connections,
            core._activations.copy(), core._thresholds.copy(), core._energies.copy(),
            0.01, 0.02, 0.5,
        )
        scalar_weights = np.array([c.weight for c in core.connections], dtype=np.float64)

        # === Numba ===
        numba_weights = init_weights.copy()
        apply_plasticity_numba(
            core._source_indices, core._target_indices, numba_weights,
            core._activations, core._thresholds, core._energies,
            0.01, 0.02, 0.5,
        )

        # 恢复
        for conn in core.connections:
            conn.weight = init_weights[conn.cid]

        assert np.allclose(scalar_weights, numba_weights, rtol=1e-12, atol=1e-12), (
            f"max_diff={np.abs(scalar_weights - numba_weights).max():.2e}"
        )

    def test_multi_step_tracks(self):
        """多步 plasticity 后 scalar 和 Numba 路径保持同步。"""
        cfg = AnivaConfig(unit_count=30, seed=77, plasticity_rate=0.01, dt=0.5)
        core = LifeCore(cfg)
        for _ in range(20):
            core.step()

        # Fork: scalar 副本 vs Numba 副本
        acts_fixed = core._activations.copy()
        thrs_fixed = core._thresholds.copy()
        engs_fixed = core._energies.copy()

        w_scalar = np.array([c.weight for c in core.connections], dtype=np.float64)
        w_numba = w_scalar.copy()

        for _ in range(10):
            # Scalar: 模拟步进（只跑 plasticity）
            for i, conn in enumerate(core.connections):
                conn.weight = w_scalar[i]
            apply_plasticity(
                core.connections,
                acts_fixed, thrs_fixed, engs_fixed,
                0.01, 0.02, 0.5,
            )
            w_scalar = np.array([c.weight for c in core.connections], dtype=np.float64)

            # Numba
            apply_plasticity_numba(
                core._source_indices, core._target_indices, w_numba,
                acts_fixed, thrs_fixed, engs_fixed,
                0.01, 0.02, 0.5,
            )

        assert np.allclose(w_scalar, w_numba, rtol=1e-12, atol=1e-12), (
            f"After 10 steps: max_diff={np.abs(w_scalar - w_numba).max():.2e}"
        )


class TestNumbaLifeCoreIntegration:
    """Numba 路径接入 LifeCore 的集成测试。"""

    def test_numba_flag_enabled_runs(self):
        """use_numba_plasticity=True 时 LifeCore 正常运行。"""
        cfg = AnivaConfig(
            unit_count=50, seed=42,
            plasticity_rate=0.01,
            use_numba_plasticity=True,
        )
        core = LifeCore(cfg)
        for _ in range(50):
            core.step()
        # 不应崩溃
        assert core.step_count == 50

    def test_numba_disabled_uses_scalar_path(self):
        """use_numba_plasticity=False（默认）走 scalar 路径。"""
        cfg = AnivaConfig(unit_count=50, seed=42, plasticity_rate=0.01)
        assert cfg.use_numba_plasticity is False
        core = LifeCore(cfg)
        for _ in range(50):
            core.step()
        assert core.step_count == 50

    def test_scalar_numba_same_result_after_steps(self):
        """同一 seed，Numba 开关不同 → 权重应 allclose。"""
        cfg_scalar = AnivaConfig(
            unit_count=30, seed=99,
            plasticity_rate=0.01,
            homeostasis_enabled=False,
            use_numba_plasticity=False,
        )
        cfg_numba = AnivaConfig(
            unit_count=30, seed=99,
            plasticity_rate=0.01,
            homeostasis_enabled=False,
            use_numba_plasticity=True,
        )

        core_s = LifeCore(cfg_scalar)
        core_n = LifeCore(cfg_numba)

        for _ in range(30):
            core_s.step()
            core_n.step()

        w_s = np.array([c.weight for c in core_s.connections], dtype=np.float64)
        w_n = np.array([c.weight for c in core_n.connections], dtype=np.float64)

        assert np.allclose(w_s, w_n, rtol=1e-12, atol=1e-12), (
            f"max_diff={np.abs(w_s - w_n).max():.2e}"
        )

    def test_weight_bounds_with_numba(self):
        """Numba 路径不破坏权重边界 [-1, 1]。"""
        cfg = AnivaConfig(
            unit_count=50, seed=42,
            plasticity_rate=0.05,
            use_numba_plasticity=True,
        )
        core = LifeCore(cfg)
        for _ in range(100):
            core.step()
        for conn in core.connections:
            assert -1.0 <= conn.weight <= 1.0

    def test_numba_does_not_flip_weight_sign(self):
        """Numba 路径不翻转权重符号（与 scalar 行为一致）。"""
        cfg = AnivaConfig(
            unit_count=50, seed=42,
            plasticity_rate=0.05,
            use_numba_plasticity=True,
        )
        core = LifeCore(cfg)
        signs_before = [1 if c.weight >= 0 else -1 for c in core.connections]
        for _ in range(50):
            core.step()
        signs_after = [1 if c.weight >= 0 else -1 for c in core.connections]
        assert signs_before == signs_after

    def test_numba_homeostasis_compatible(self):
        """Numba 路径 + homeostasis 同时启用不冲突。"""
        cfg = AnivaConfig(
            unit_count=50, seed=42,
            plasticity_rate=0.01,
            homeostasis_enabled=True,
            homeostatic_target_abs_weight=0.30,
            homeostatic_rate=1.0,
            use_numba_plasticity=True,
        )
        core = LifeCore(cfg)
        for _ in range(100):
            core.step()
        abs_mean = sum(abs(c.weight) for c in core.connections) / len(core.connections)
        # Homeostasis 应保持 weight_abs_mean ≥ 0.25
        assert abs_mean >= 0.25

    def test_numba_determinism(self):
        """Numba 路径应完全确定性（同 seed 同结果）。"""
        def run():
            cfg = AnivaConfig(
                unit_count=30, seed=99,
                plasticity_rate=0.01,
                use_numba_plasticity=True,
            )
            core = LifeCore(cfg)
            for _ in range(50):
                core.step()
            return [c.weight for c in core.connections]

        assert run() == pytest.approx(run())


class TestNumbaFallback:
    """Numba 不可用时的优雅降级。"""

    def test_graceful_when_numba_missing(self, monkeypatch):
        """模拟 Numba 不可用时 LifeCore 走 scalar 路径且不崩溃。"""
        # 如果 Numba 本身就不可用，跳过（测试的是降级逻辑）
        if not NUMBA_AVAILABLE:
            pytest.skip("Numba not available — no fallback to test")

        # mock 掉 NUMBA_AVAILABLE
        import aniva.life_core as lc
        monkeypatch.setattr(lc, "NUMBA_AVAILABLE", False)
        monkeypatch.setattr(lc, "apply_plasticity_numba", None)

        cfg = AnivaConfig(
            unit_count=30, seed=42,
            plasticity_rate=0.01,
            use_numba_plasticity=True,  # 请求 Numba 但不可用
        )
        core = LifeCore(cfg)
        # 不应崩溃，应走 scalar fallback
        for _ in range(20):
            core.step()
        assert core.step_count == 20
