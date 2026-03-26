import math
import pytest
from cadquery import Vector
import caid


def test_box_volume():
    r = caid.box(10, 20, 30)
    assert r.ok
    assert abs(r.volume_after - 6000.0) < 0.01


def test_box_surface_area():
    r = caid.box(10, 20, 30)
    assert r.ok
    assert abs(r.surface_area - 2200.0) < 0.01


def test_box_with_origin():
    r = caid.box(10, 10, 10, origin=Vector(5, 5, 5))
    assert r.ok
    assert abs(r.volume_after - 1000.0) < 0.01


def test_box_zero_dimension():
    r = caid.box(0, 10, 10)
    assert not r.ok
    assert "length" in r.diagnostics["reason"]


def test_box_negative_dimension():
    r = caid.box(-5, 10, 10)
    assert not r.ok


def test_cylinder_volume():
    r = caid.cylinder(5, 20)
    assert r.ok
    expected = math.pi * 25 * 20
    assert abs(r.volume_after - expected) < 0.1


def test_sphere_volume():
    r = caid.sphere(10)
    assert r.ok
    expected = (4 / 3) * math.pi * (10**3)
    assert abs(r.volume_after - expected) / expected < 0.01


def test_cone_volume():
    r = caid.cone(10, 0, 20)
    assert r.ok
    expected = (1 / 3) * math.pi * 100 * 20
    assert abs(r.volume_after - expected) < 1.0


def test_cone_frustum():
    r = caid.cone(10, 5, 20)
    assert r.ok
    assert r.volume_after > 0


def test_torus_volume():
    r = caid.torus(20, 5)
    assert r.ok
    expected = 2 * math.pi**2 * 20 * 25
    assert abs(r.volume_after - expected) < 1.0


def test_torus_invalid_radii():
    r = caid.torus(5, 10)
    assert not r.ok
    assert "minor_radius" in r.diagnostics["reason"]


def test_cylinder_custom_axis():
    r = caid.cylinder(5, 20, axis=Vector(1, 0, 0))
    assert r.ok
    expected = math.pi * 25 * 20
    assert abs(r.volume_after - expected) < 0.1
