import pytest
from build123d import Vector
import caid


def test_add_and_get(box_shape):
    asm = caid.Assembly()
    part = caid.Part("base", box_shape)
    asm2 = asm.add(part)
    assert asm2.get("base") is not None
    assert asm.get("base") is None  # original unchanged


def test_remove(box_shape):
    asm = caid.Assembly()
    asm = asm.add(caid.Part("a", box_shape))
    asm = asm.add(caid.Part("b", box_shape))
    asm2 = asm.remove("a")
    assert asm2.get("a") is None
    assert asm2.get("b") is not None


def test_move(box_shape):
    asm = caid.Assembly()
    asm = asm.add(caid.Part("a", box_shape))
    asm2 = asm.move("a", Vector(100, 0, 0))
    p = asm2.get("a")
    assert abs(p.origin.X - 100.0) < 0.01


def test_merge_all(box_shape):
    asm = caid.Assembly()
    asm = asm.add(caid.Part("a", box_shape))
    b = caid.box(10, 20, 30, origin=Vector(5, 0, 0)).unwrap()
    asm = asm.add(caid.Part("b", b))
    r = asm.merge_all()
    assert r.ok
    assert r.volume_after > 6000.0


def test_merge_empty():
    asm = caid.Assembly()
    r = asm.merge_all()
    assert not r.ok


def test_to_dict(box_shape):
    asm = caid.Assembly()
    asm = asm.add(caid.Part("base", box_shape, metadata={"color": "red"}))
    d = asm.to_dict()
    assert len(d) == 1
    assert d[0]["name"] == "base"
    assert d[0]["metadata"]["color"] == "red"
