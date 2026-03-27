from __future__ import annotations
from pathlib import Path
from typing import Any

from OCP.STEPControl import STEPControl_Writer, STEPControl_Reader, STEPControl_AsIs
from OCP.StlAPI import StlAPI_Writer
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepTools import BRepTools
from OCP.BRep import BRep_Builder
from OCP.TopoDS import TopoDS_Shape
from OCP.IFSelect import IFSelect_RetDone

from .result import ForgeResult
from ._backend import get_backend


def _fail(reason: str, **extra) -> ForgeResult:
    diag = {"reason": reason}
    diag.update(extra)
    return ForgeResult(shape=None, valid=False, diagnostics=diag)


def _get_wrapped(shape: Any):
    if hasattr(shape, "wrapped"):
        return shape.wrapped
    return shape


def to_stl(shape: Any, path: str | Path, tolerance: float = 0.1, angular_tolerance: float = 0.1) -> ForgeResult:
    try:
        p = str(Path(path))
        wrapped = _get_wrapped(shape)
        mesh = BRepMesh_IncrementalMesh(wrapped, tolerance, False, angular_tolerance)
        mesh.Perform()
        writer = StlAPI_Writer()
        ok = writer.Write(wrapped, p)
        if not ok:
            return _fail("STL export returned failure")
        return ForgeResult(shape=None, valid=True)
    except Exception as e:
        return _fail("STL export failed", exception=str(e))


def to_step(shape: Any, path: str | Path) -> ForgeResult:
    try:
        p = str(Path(path))
        wrapped = _get_wrapped(shape)
        writer = STEPControl_Writer()
        writer.Transfer(wrapped, STEPControl_AsIs)
        status = writer.Write(p)
        if status != IFSelect_RetDone:
            return _fail("STEP export failed", status=str(status))
        if not Path(p).exists():
            return _fail("STEP export produced no file")
        return ForgeResult(shape=None, valid=True)
    except Exception as e:
        return _fail("STEP export failed", exception=str(e))


def to_brep(shape: Any, path: str | Path) -> ForgeResult:
    try:
        p = str(Path(path))
        wrapped = _get_wrapped(shape)
        BRepTools.Write_s(wrapped, p)
        if not Path(p).exists():
            return _fail("BREP export produced no file")
        return ForgeResult(shape=None, valid=True)
    except Exception as e:
        return _fail("BREP export failed", exception=str(e))


def from_step(path: str | Path) -> ForgeResult:
    try:
        p = str(Path(path))
        reader = STEPControl_Reader()
        status = reader.ReadFile(p)
        if status != IFSelect_RetDone:
            return _fail("STEP import failed to read file", status=str(status))
        reader.TransferRoots()
        ocp_shape = reader.OneShape()

        b = get_backend()
        shape = b.wrap_shape(ocp_shape)
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
        builder = BRep_Builder()
        ocp_shape = TopoDS_Shape()
        ok = BRepTools.Read_s(ocp_shape, p, builder)
        if not ok:
            return _fail("BREP import failed to read file")

        b = get_backend()
        shape = b.wrap_shape(ocp_shape)
        return ForgeResult(
            shape=shape, valid=True,
            volume_after=b.get_volume(shape),
            surface_area=b.get_surface_area(shape),
        )
    except Exception as e:
        return _fail("BREP import failed", exception=str(e))
