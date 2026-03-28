from __future__ import annotations
from typing import Any

from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.ShapeFix import ShapeFix_Shape, ShapeFix_Solid
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX, TopAbs_SOLID
from OCP.TopoDS import TopoDS

from .result import ForgeResult
from ._backend import get_backend


def _count_topo(wrapped_shape, topo_type) -> int:
    exp = TopExp_Explorer(wrapped_shape, topo_type)
    count = 0
    while exp.More():
        count += 1
        exp.Next()
    return count


def _get_wrapped(shape: Any):
    """Get the OCP TopoDS_Shape from a backend shape."""
    if hasattr(shape, "wrapped"):
        return shape.wrapped
    return shape


def check_valid(shape: Any) -> dict:
    wrapped = _get_wrapped(shape)
    analyzer = BRepCheck_Analyzer(wrapped, True)
    is_valid = analyzer.IsValid()

    n_faces = _count_topo(wrapped, TopAbs_FACE)
    n_edges = _count_topo(wrapped, TopAbs_EDGE)
    n_verts = _count_topo(wrapped, TopAbs_VERTEX)

    has_small_faces = False
    exp = TopExp_Explorer(wrapped, TopAbs_FACE)
    while exp.More():
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(exp.Current(), props)
        if props.Mass() < 1e-6:
            has_small_faces = True
            break
        exp.Next()

    return {
        "is_valid": is_valid,
        "has_degenerate_faces": has_small_faces,
        "has_small_faces": has_small_faces,
        "has_bad_edges": not is_valid,
        "has_self_intersections": not is_valid,
        "n_faces": n_faces,
        "n_edges": n_edges,
        "n_vertices": n_verts,
    }


def heal(shape: Any, precision: float = 1e-3) -> ForgeResult:
    try:
        wrapped = _get_wrapped(shape)
        checks_before = check_valid(shape)

        # 1. ShapeFix_Shape — general fix pass
        fixer = ShapeFix_Shape(wrapped)
        fixer.SetPrecision(precision)
        fixer.Perform()
        result = fixer.Shape()

        # 2. ShapeFix_Solid — close open shells into solids (all solids)
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid
        from OCP.TopoDS import TopoDS_Compound
        from OCP.BRep import BRep_Builder as _BB

        solids = []
        exp = TopExp_Explorer(result, TopAbs_SOLID)
        while exp.More():
            solid = TopoDS.Solid_s(exp.Current())
            solid_fixer = ShapeFix_Solid(solid)
            solid_fixer.Perform()
            solids.append(solid_fixer.Shape())
            exp.Next()

        if len(solids) == 1:
            result = solids[0]
        elif len(solids) > 1:
            builder = _BB()
            compound = TopoDS_Compound()
            builder.MakeCompound(compound)
            for s in solids:
                builder.Add(compound, s)
            result = compound

        # 3. ShapeUpgrade_UnifySameDomain — merge coplanar faces
        unifier = ShapeUpgrade_UnifySameDomain(result, True, True, True)
        unifier.Build()
        result = unifier.Shape()

        b = get_backend()
        healed = b.wrap_shape(result)
        checks_after = check_valid(healed)

        return ForgeResult(
            shape=healed,
            valid=checks_after["is_valid"],
            volume_after=b.get_volume(healed),
            surface_area=b.get_surface_area(healed),
            diagnostics={
                "checks_before": checks_before,
                "checks_after": checks_after,
            },
        )
    except Exception as e:
        return ForgeResult(
            shape=None, valid=False,
            diagnostics={"reason": "heal failed", "exception": str(e)},
        )


def simplify(shape: Any, tolerance: float = 0.01) -> ForgeResult:
    try:
        wrapped = _get_wrapped(shape)
        unifier = ShapeUpgrade_UnifySameDomain(wrapped, True, True, True)
        unifier.SetLinearTolerance(tolerance)
        unifier.SetAngularTolerance(tolerance)
        unifier.Build()
        result = unifier.Shape()

        b = get_backend()
        simplified = b.wrap_shape(result)
        checks = check_valid(simplified)

        return ForgeResult(
            shape=simplified,
            valid=checks["is_valid"],
            volume_after=b.get_volume(simplified),
            surface_area=b.get_surface_area(simplified),
        )
    except Exception as e:
        return ForgeResult(
            shape=None, valid=False,
            diagnostics={"reason": "simplify failed", "exception": str(e)},
        )
