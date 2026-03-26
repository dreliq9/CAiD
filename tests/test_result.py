import pytest
import caid


def test_ok_true_when_valid_and_shape():
    r = caid.ForgeResult(shape="something", valid=True)
    assert r.ok


def test_ok_false_when_invalid():
    r = caid.ForgeResult(shape="something", valid=False)
    assert not r.ok


def test_ok_false_when_no_shape():
    r = caid.ForgeResult(shape=None, valid=True)
    assert not r.ok


def test_unwrap_returns_shape():
    r = caid.ForgeResult(shape="myshape", valid=True)
    assert r.unwrap() == "myshape"


def test_unwrap_raises_on_failure():
    r = caid.ForgeResult(shape=None, valid=False, diagnostics={"reason": "test"})
    with pytest.raises(ValueError, match="test"):
        r.unwrap()


def test_diagnostics_default_empty():
    r = caid.ForgeResult(shape=None, valid=False)
    assert r.diagnostics == {}
