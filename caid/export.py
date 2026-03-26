from __future__ import annotations
from pathlib import Path
from typing import Any

from build123d import export_stl, export_step, export_brep, import_step, import_brep

from .result import ForgeResult
from ._backend import get_backend


def _fail(reason: str, **extra) -> ForgeResult:
    diag = {"reason": reason}
    diag.update(extra)
    return ForgeResult(shape=None, valid=False, diagnostics=diag)


def to_stl(shape: Any, path: str | Path, tolerance: float = 0.1, angular_tolerance: float = 0.1) -> ForgeResult:
    try:
        p = str(Path(path))
        ok = export_stl(shape, p, tolerance=tolerance, angular_tolerance=angular_tolerance)
        if not ok:
            return _fail("STL export returned failure")
        return ForgeResult(shape=None, valid=True)
    except Exception as e:
        return _fail("STL export failed", exception=str(e))


def to_step(shape: Any, path: str | Path) -> ForgeResult:
    try:
        p = str(Path(path))
        export_step(shape, p)
        if not Path(p).exists():
            return _fail("STEP export produced no file")
        return ForgeResult(shape=None, valid=True)
    except Exception as e:
        return _fail("STEP export failed", exception=str(e))


def to_brep(shape: Any, path: str | Path) -> ForgeResult:
    try:
        p = str(Path(path))
        export_brep(shape, p)
        if not Path(p).exists():
            return _fail("BREP export produced no file")
        return ForgeResult(shape=None, valid=True)
    except Exception as e:
        return _fail("BREP export failed", exception=str(e))


def from_step(path: str | Path) -> ForgeResult:
    try:
        p = str(Path(path))
        compound = import_step(p)
        # import_step returns a Compound; get the first solid
        solids = compound.solids()
        if solids:
            shape = solids[0] if len(solids) == 1 else compound
        else:
            shape = compound
        b = get_backend()
        return ForgeResult(
            shape=shape, valid=True,
            volume_after=b.get_volume(shape),
            surface_area=b.get_surface_area(shape),
        )
    except Exception as e:
        return _fail("STEP import failed", exception=str(e))


def from_brep(path: str | Path) -> ForgeResult:
    try:
        p = str(Path(path))
        shape = import_brep(p)
        b = get_backend()
        return ForgeResult(
            shape=shape, valid=True,
            volume_after=b.get_volume(shape),
            surface_area=b.get_surface_area(shape),
        )
    except Exception as e:
        return _fail("BREP import failed", exception=str(e))
