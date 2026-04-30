"""LifeCore 测试."""

import pytest
import numpy as np
from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.observer import Observer


class TestLifeCoreInit:
    def test_default_init(self):
        """用默认 config 初始化 LifeCore."""
        core = LifeCore()
        assert core.unit_count == 300
        assert core.step_count == 0

    def test_custom_unit_count(self):
        """可以指定单元数量."""
        config = AnivaConfig(unit_count=100, seed=1)
        core = LifeCore(config)
        assert core.unit_count == 100

    def test_seed_determinism(self):
        """相同 seed 产生相同的初始结构."""
        config = AnivaConfig(unit_count=50, seed=123)
        core1 = LifeCore(config)
        core2 = LifeCore(config)

        # 单元属性完全相同
        for uid in range(50):
            u1 = core1.units[uid]
            u2 = core2.units[uid]
            assert u1.uid == u2.uid
            assert u1.position == u2.position
            assert u1.threshold == u2.threshold
            assert u1.time_constant == u2.time_constant
            assert u1.energy == u2.energy

        # 连接完全相同
        assert len(core1.connections) == len(core2.connections)
        for c1, c2 in zip(core1.connections, core2.connections):
            assert c1.source_id == c2.source_id
            assert c1.target_id == c2.target_id
            assert c1.weight == c2.weight

    def test_different_seed_different_structure(self):
        """不同 seed 产生不同的初始结构."""
        core1 = LifeCore(AnivaConfig(unit_count=30, seed=1))
        core2 = LifeCore(AnivaConfig(unit_count=30, seed=2))

        # 位置至少有一个不同
        positions1 = [u.position for u in core1.units.values()]
        positions2 = [u.position for u in core2.units.values()]
        assert positions1 != positions2

    def test_connection_count(self):
        """连接数量符合 config 设置."""
        config = AnivaConfig(unit_count=100, connection_density=0.05, seed=0)
        core = LifeCore(config)
        expected = int(100 * 99 * 0.05)
        assert core.connection_count == expected

    def test_no_self_connections(self):
        """不存在自连接（同一个 unit 不会连到自己）."""
        core = LifeCore(AnivaConfig(unit_count=50, seed=7))
        for conn in core.connections:
            assert conn.source_id != conn.target_id

    def test_all_units_initialized(self):
        """所有单元都有合法的初始值."""
        core = LifeCore(AnivaConfig(unit_count=200, seed=42))
        for uid, unit in core.units.items():
            assert unit.uid == uid
            assert 0.0 <= unit.activation <= 1.0
            assert 0.0 <= unit.energy <= 1.0
            assert 0.2 <= unit.threshold <= 0.4
            assert 0.8 <= unit.time_constant <= 1.2
            # 位置在空间半径内
            for coord in unit.position:
                assert -1.0 <= coord <= 1.0

    def test_exc_inh_ratio(self):
        """兴奋/抑制比例接近 config 设定."""
        config = AnivaConfig(unit_count=200, connection_density=0.05, exc_inh_ratio=0.8, seed=0)
        core = LifeCore(config)
        exc_count = sum(1 for c in core.connections if not c.is_inhibitory)
        inh_count = sum(1 for c in core.connections if c.is_inhibitory)
        actual_ratio = exc_count / (exc_count + inh_count)
        # 允许统计偏差
        assert abs(actual_ratio - 0.8) < 0.05


class TestLifeCoreStep:
    def test_step_increments_counter(self):
        """step() 会增加步数计数器."""
        core = LifeCore(AnivaConfig(unit_count=10, seed=0))
        assert core.step_count == 0
        core.step()
        assert core.step_count == 1
        core.step()
        assert core.step_count == 2

    def test_step_does_not_crash(self):
        """多次 step() 不会崩溃."""
        core = LifeCore(AnivaConfig(unit_count=10, seed=0))
        for _ in range(100):
            core.step()


class TestObserver:
    def test_snapshot_shape(self):
        """快照返回正确的数据形状."""
        config = AnivaConfig(unit_count=20, seed=0)
        core = LifeCore(config)
        obs = Observer(core)
        snap = obs.snapshot()
        assert snap["step"] == 0
        assert len(snap["activations"]) == 20
        assert len(snap["energies"]) == 20
        assert len(snap["traces"]) == 20

    def test_snapshot_after_steps(self):
        """步进后快照的 step 值正确更新."""
        core = LifeCore(AnivaConfig(unit_count=10, seed=0))
        obs = Observer(core)
        for i in range(5):
            core.step()
        snap = obs.snapshot()
        assert snap["step"] == 5
