"""Unit 测试."""

import pytest
from aniva.core.unit import Unit


class TestUnit:
    def test_default_initialization(self):
        """Unit 可以用默认值正常初始化."""
        u = Unit(uid=0)
        assert u.uid == 0
        assert u.activation == 0.0
        assert u.energy == 0.5
        assert u.threshold == 0.3
        assert u.trace == 0.0
        assert u.position == (0.0, 0.0, 0.0)
        assert u.time_constant == 1.0

    def test_custom_initialization(self):
        """Unit 可以用自定义值初始化."""
        u = Unit(
            uid=42,
            activation=0.7,
            energy=0.3,
            threshold=0.5,
            trace=0.2,
            position=(1.0, -0.5, 0.3),
            time_constant=0.9,
        )
        assert u.uid == 42
        assert u.activation == 0.7
        assert u.energy == 0.3
        assert u.threshold == 0.5
        assert u.trace == 0.2
        assert u.position == (1.0, -0.5, 0.3)
        assert u.time_constant == 0.9

    def test_activation_bounds(self):
        """activation 必须在 [0, 1] 范围内."""
        with pytest.raises(ValueError):
            Unit(uid=0, activation=-0.1)
        with pytest.raises(ValueError):
            Unit(uid=0, activation=1.1)

    def test_energy_bounds(self):
        """energy 必须在 [0, 1] 范围内."""
        with pytest.raises(ValueError):
            Unit(uid=0, energy=-0.1)
        with pytest.raises(ValueError):
            Unit(uid=0, energy=1.1)

    def test_two_units_independent(self):
        """两个 Unit 是独立的对象."""
        u1 = Unit(uid=0, activation=0.3)
        u2 = Unit(uid=1, activation=0.7)
        assert u1.activation != u2.activation
        assert u1.uid != u2.uid
