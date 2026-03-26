import pytest
import caid


def test_stl_export(box_shape, tmp_path):
    out = tmp_path / "test.stl"
    r = caid.to_stl(box_shape, out)
    assert r.valid
    assert out.exists()
    assert out.stat().st_size > 0


def test_step_roundtrip(box_shape, tmp_path):
    out = tmp_path / "test.step"
    export_r = caid.to_step(box_shape, out)
    assert export_r.valid
    import_r = caid.from_step(out)
    assert import_r.ok
    assert abs(import_r.volume_after - 6000.0) < 1.0


def test_brep_roundtrip(box_shape, tmp_path):
    out = tmp_path / "test.brep"
    export_r = caid.to_brep(box_shape, out)
    assert export_r.valid
    import_r = caid.from_brep(out)
    assert import_r.ok
    assert abs(import_r.volume_after - 6000.0) < 1.0


def test_step_import_nonexistent(tmp_path):
    r = caid.from_step(tmp_path / "nope.step")
    assert not r.ok


def test_brep_import_nonexistent(tmp_path):
    r = caid.from_brep(tmp_path / "nope.brep")
    assert not r.ok
