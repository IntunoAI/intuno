"""Unit tests for topology validation.

Uses MagicMock objects to avoid importing the full ORM model chain
which triggers circular imports in isolation.
"""

import sys
from types import ModuleType
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

# Stub out the heavy dependency chain before importing TopologyValidator
_base_mod = ModuleType("src.models.base")
_base_mod.BaseModel = type("BaseModel", (), {})
sys.modules.setdefault("src.models.base", _base_mod)

from src.exceptions import BadRequestException  # noqa: E402
from src.network.utils.topology import TopologyValidator  # noqa: E402


def _make_participant(pid=None, name="Agent"):
    p = MagicMock()
    p.id = pid or uuid4()
    p.name = name
    return p


def _make_network(topology="mesh"):
    n = MagicMock()
    n.topology_type = topology
    return n


class TestMeshTopology:
    def test_allows_any_communication(self):
        v = TopologyValidator()
        a, b = _make_participant(name="A"), _make_participant(name="B")
        network = _make_network("mesh")
        # Should not raise
        v.validate(network, a, b, [a, b])

    def test_get_reachable_returns_all_others(self):
        v = TopologyValidator()
        a, b, c = (
            _make_participant(name="A"),
            _make_participant(name="B"),
            _make_participant(name="C"),
        )
        network = _make_network("mesh")
        reachable = v.get_reachable(network, a, [a, b, c])
        assert set(p.id for p in reachable) == {b.id, c.id}


class TestStarTopology:
    def test_hub_can_send_to_anyone(self):
        v = TopologyValidator()
        hub = _make_participant(name="Hub")
        spoke = _make_participant(name="Spoke")
        network = _make_network("star")
        # Hub is first participant — should not raise
        v.validate(network, hub, spoke, [hub, spoke])

    def test_spoke_cannot_initiate(self):
        v = TopologyValidator()
        hub = _make_participant(name="Hub")
        spoke = _make_participant(name="Spoke")
        network = _make_network("star")
        with pytest.raises(BadRequestException, match="hub"):
            v.validate(network, spoke, hub, [hub, spoke])

    def test_get_reachable_for_hub(self):
        v = TopologyValidator()
        hub = _make_participant(name="Hub")
        s1 = _make_participant(name="S1")
        s2 = _make_participant(name="S2")
        network = _make_network("star")
        reachable = v.get_reachable(network, hub, [hub, s1, s2])
        assert set(p.id for p in reachable) == {s1.id, s2.id}

    def test_get_reachable_for_spoke(self):
        v = TopologyValidator()
        hub = _make_participant(name="Hub")
        spoke = _make_participant(name="Spoke")
        network = _make_network("star")
        reachable = v.get_reachable(network, spoke, [hub, spoke])
        assert len(reachable) == 1
        assert reachable[0].id == hub.id


class TestRingTopology:
    def test_allows_next_in_ring(self):
        v = TopologyValidator()
        a = _make_participant(name="A")
        b = _make_participant(name="B")
        c = _make_participant(name="C")
        network = _make_network("ring")
        # A -> B (next in order)
        v.validate(network, a, b, [a, b, c])
        # B -> C (next in order)
        v.validate(network, b, c, [a, b, c])
        # C -> A (wraps around)
        v.validate(network, c, a, [a, b, c])

    def test_rejects_skip_in_ring(self):
        v = TopologyValidator()
        a = _make_participant(name="A")
        b = _make_participant(name="B")
        c = _make_participant(name="C")
        network = _make_network("ring")
        # A -> C (skipping B)
        with pytest.raises(BadRequestException, match="Ring topology"):
            v.validate(network, a, c, [a, b, c])

    def test_get_reachable_returns_next_only(self):
        v = TopologyValidator()
        a = _make_participant(name="A")
        b = _make_participant(name="B")
        c = _make_participant(name="C")
        network = _make_network("ring")
        reachable = v.get_reachable(network, a, [a, b, c])
        assert len(reachable) == 1
        assert reachable[0].id == b.id


class TestCustomTopology:
    def test_allows_any_communication(self):
        v = TopologyValidator()
        a, b = _make_participant(name="A"), _make_participant(name="B")
        network = _make_network("custom")
        # Should not raise
        v.validate(network, a, b, [a, b])
