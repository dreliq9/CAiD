import pytest
from caid.vector import Vector
import caid


def test_belt_wire_two_pulleys(two_pulley_setup):
    r = caid.belt_wire(two_pulley_setup, closed=True)
    assert r.ok
    assert r.diagnostics.get("n_edges", 0) > 0


def test_belt_wire_too_few_pulleys():
    r = caid.belt_wire([(Vector(0, 0, 0), 5.0)])
    assert not r.ok
    assert "2 pulleys" in r.diagnostics["reason"]


def test_belt_wire_three_pulleys():
    pulleys = [
        (Vector(0, 0, 0), 10.0),
        (Vector(50, 0, 0), 10.0),
        (Vector(25, 40, 0), 8.0),
    ]
    r = caid.belt_wire(pulleys, closed=True)
    assert r.ok


def test_array_on_curve_invalid_count():
    r = caid.array_on_curve(None, None, 0)
    assert not r.ok
