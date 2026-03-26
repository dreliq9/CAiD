import pytest
from build123d import Vector
import caid


def test_boolean_union_increases_volume(box_shape):
    other = caid.box(10, 20, 30, origin=Vector(5, 0, 0)).unwrap()
    r = caid.boolean_union(box_shape, other)
    assert r.ok
    assert r.volume_after > 6000.0


def test_boolean_cut_reduces_volume(box_shape):
    tool = caid.box(5, 5, 5).unwrap()
    r = caid.boolean_cut(box_shape, tool)
    assert r.ok
    assert r.volume_after < r.volume_before


def test_boolean_cut_no_overlap(box_shape):
    tool = caid.box(5, 5, 5, origin=Vector(100, 100, 100)).unwrap()
    r = caid.boolean_cut(box_shape, tool)
    assert not r.ok
    assert "reason" in r.diagnostics


def test_boolean_intersect(box_shape):
    other = caid.box(5, 5, 5).unwrap()
    r = caid.boolean_intersect(box_shape, other)
    assert r.ok
    assert abs(r.volume_after - 125.0) < 0.1


def test_boolean_intersect_no_overlap(box_shape):
    other = caid.box(5, 5, 5, origin=Vector(100, 100, 100)).unwrap()
    r = caid.boolean_intersect(box_shape, other)
    assert not r.ok


def test_boolean_accepts_forge_result():
    a = caid.box(10, 10, 10)
    b = caid.box(10, 10, 10, origin=Vector(5, 0, 0))
    r = caid.boolean_union(a, b)
    assert r.ok


def test_fillet(box_shape):
    r = caid.fillet(box_shape, 1.0)
    assert r.ok
    assert r.volume_after < r.volume_before


def test_chamfer(box_shape):
    r = caid.chamfer(box_shape, 1.0)
    assert r.ok
    assert r.volume_after < r.volume_before


def test_fillet_invalid_radius():
    r = caid.fillet(None, -1.0)
    assert not r.ok


def test_translate(box_shape):
    r = caid.translate(box_shape, Vector(100, 0, 0))
    assert r.ok
    assert abs(r.volume_after - 6000.0) < 0.01


def test_rotate(box_shape):
    r = caid.rotate(box_shape, Vector(0, 0, 0), Vector(0, 0, 1), 45)
    assert r.ok
    assert abs(r.volume_after - 6000.0) < 0.01


def test_mirror(box_shape):
    r = caid.mirror(box_shape, Vector(0, 0, 0), Vector(1, 0, 0))
    assert r.ok
    assert abs(r.volume_after - 6000.0) < 0.01


def test_scale(box_shape):
    r = caid.scale(box_shape, 2.0)
    assert r.ok
    assert abs(r.volume_after - 48000.0) < 1.0


def test_scale_invalid():
    r = caid.scale(None, -1.0)
    assert not r.ok
