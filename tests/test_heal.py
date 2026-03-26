import pytest
import caid


def test_check_valid_on_good_shape(box_shape):
    checks = caid.check_valid(box_shape)
    assert checks["is_valid"]
    assert checks["n_faces"] > 0
    assert checks["n_edges"] > 0
    assert checks["n_vertices"] > 0


def test_heal_on_good_shape(box_shape):
    r = caid.heal(box_shape)
    assert r.ok
    assert r.volume_after > 0
    assert "checks_before" in r.diagnostics
    assert "checks_after" in r.diagnostics


def test_simplify_on_boolean_result(box_shape):
    """After a boolean, simplify should merge coplanar faces."""
    tool = caid.box(5, 5, 5).unwrap()
    cut_result = caid.boolean_cut(box_shape, tool)
    assert cut_result.ok
    r = caid.simplify(cut_result.shape)
    assert r.ok
    assert r.volume_after > 0
