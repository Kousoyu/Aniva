"""Connection 测试."""

import pytest
from aniva.core.connection import Connection


class TestConnection:
    def test_default_excitatory(self):
        """默认连接是兴奋性的."""
        c = Connection(cid=0, source_id=1, target_id=2)
        assert c.cid == 0
        assert c.source_id == 1
        assert c.target_id == 2
        assert c.weight == 0.1
        assert not c.is_inhibitory

    def test_inhibitory_connection(self):
        """可以创建抑制性连接."""
        c = Connection(cid=0, source_id=1, target_id=2, weight=-0.5, is_inhibitory=True)
        assert c.weight == -0.5
        assert c.is_inhibitory

    def test_weight_bounds(self):
        """weight 必须在 [-1, 1] 范围内."""
        with pytest.raises(ValueError):
            Connection(cid=0, source_id=1, target_id=2, weight=1.5)
        with pytest.raises(ValueError):
            Connection(cid=0, source_id=1, target_id=2, weight=-1.5)

    def test_inhibitory_flag_consistency_positive(self):
        """is_inhibitory=True 但 weight>0 是矛盾的."""
        with pytest.raises(ValueError):
            Connection(cid=0, source_id=1, target_id=2, weight=0.5, is_inhibitory=True)

    def test_inhibitory_flag_consistency_negative(self):
        """is_inhibitory=False 但 weight<0 是矛盾的."""
        with pytest.raises(ValueError):
            Connection(cid=0, source_id=1, target_id=2, weight=-0.5, is_inhibitory=False)

    def test_multiple_connections(self):
        """可以创建多个独立的连接."""
        c1 = Connection(cid=0, source_id=1, target_id=2, weight=0.3)
        c2 = Connection(cid=1, source_id=2, target_id=1, weight=-0.1, is_inhibitory=True)
        assert c1.cid != c2.cid
        assert c1.weight > 0
        assert c2.weight < 0
