from __future__ import annotations
import math
from typing import Any
from .vector import Vector
from .result import ForgeResult
from ._backend import get_backend


def _fail(reason: str, **extra) -> ForgeResult:
    diag = {"reason": reason}
    diag.update(extra)
    return ForgeResult(shape=None, valid=False, diagnostics=diag)


def _extract_shape(x: ForgeResult | Any) -> Any:
    if isinstance(x, ForgeResult):
        return x.unwrap()
    return x


_REL_TOL = 1e-4


# ---------------------------------------------------------------------------
# Face selection helpers (replace CadQuery selector engine)
# ---------------------------------------------------------------------------

def _get_wrapped(shape: Any):
    if hasattr(shape, "wrapped"):
        return shape.wrapped
    return shape


def _select_face(shape, selector: str):
    """Select a face from a shape using CQ-style selector strings.

    Supports: >X, <X, >Y, <Y, >Z, <Z (face at max/min center along axis).
    """
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    wrapped = _get_wrapped(shape)
    sel = selector.strip()
    if len(sel) < 2:
        return None

    axis_map = {"X": 0, "Y": 1, "Z": 2}
    op = sel[0]
    axis_idx = axis_map.get(sel[1:].upper())
    if axis_idx is None or op not in (">", "<"):
        return None

    # Collect all faces with their center coordinate along axis
    faces = []
    exp = TopExp_Explorer(wrapped, TopAbs_FACE)
    while exp.More():
        face = exp.Current()
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        center = props.CentreOfMass()
        coord = [center.X(), center.Y(), center.Z()][axis_idx]
        faces.append((face, coord))
        exp.Next()

    if not faces:
        return None

    if op == ">":
        target = max(v for _, v in faces)
    else:
        target = min(v for _, v in faces)

    # Return first face at the target coordinate
    tol = 1e-6
    for face, v in faces:
        if abs(v - target) < tol:
            return face
    return None


def _face_center_and_normal(ocp_face):
    """Get the center point and outward normal of an OCP face."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.TopoDS import TopoDS

    # Downcast to TopoDS_Face
    face = TopoDS.Face_s(ocp_face)

    # Center via mass properties
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    center = props.CentreOfMass()

    # Normal at center via surface adaptor
    adaptor = BRepAdaptor_Surface(face)
    u_mid = (adaptor.FirstUParameter() + adaptor.LastUParameter()) / 2.0
    v_mid = (adaptor.FirstVParameter() + adaptor.LastVParameter()) / 2.0

    from OCP.BRepLProp import BRepLProp_SLProps
    slprops = BRepLProp_SLProps(adaptor, u_mid, v_mid, 1, 1e-6)
    if slprops.IsNormalDefined():
        n = slprops.Normal()
        return (
            Vector(center.X(), center.Y(), center.Z()),
            Vector(n.X(), n.Y(), n.Z()),
        )

    # Fallback: guess normal from selector axis
    return Vector(center.X(), center.Y(), center.Z()), Vector(0, 0, 1)


def add_hole(
    shape: ForgeResult | Any,
    radius: float,
    depth: float | None = None,
    face_selector: str = ">Z",
) -> ForgeResult:
    """Cut a cylindrical hole through a face of a solid.

    Args:
        shape: The solid to drill into.
        radius: Hole radius in mm.
        depth: Hole depth in mm. If None, cuts all the way through.
        face_selector: Face selector string (e.g. ">Z", "<Y"). Default ">Z" (top face).
    """
    if radius <= 0:
        return _fail(f"hole radius must be > 0, got {radius}")
    try:
        s = _extract_shape(shape)
        b_ = get_backend()
        v_before = b_.get_volume(s)

        # Find target face
        ocp_face = _select_face(s, face_selector)
        if ocp_face is None:
            return _fail(f"face selector '{face_selector}' matched no face")

        center, normal = _face_center_and_normal(ocp_face)

        # Default depth: use bounding box diagonal to ensure through-hole
        if depth is None:
            from OCP.Bnd import Bnd_Box
            from OCP.BRepBndLib import BRepBndLib
            bbox = Bnd_Box()
            BRepBndLib.Add_s(_get_wrapped(s), bbox)
            xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
            diag = math.sqrt((xmax-xmin)**2 + (ymax-ymin)**2 + (zmax-zmin)**2)
            depth = diag * 2

        # Build cylinder tool along -normal (drilling inward from face)
        cyl = b_.make_cylinder(radius, depth)

        # Rotate cylinder from Z-axis to -normal direction
        neg_normal = Vector(-normal.x, -normal.y, -normal.z)
        z_axis = Vector(0, 0, 1)
        cross = z_axis.cross(neg_normal)
        if cross.Length > 1e-10:
            angle = z_axis.getAngle(neg_normal) * 180.0 / math.pi
            cyl = b_.rotate(cyl, Vector(0, 0, 0), cross, angle)
        elif neg_normal.z < 0:
            # 180 degree flip needed
            cyl = b_.rotate(cyl, Vector(0, 0, 0), Vector(1, 0, 0), 180.0)

        # Position: start slightly above the face along normal
        nudge = 0.1  # mm
        start = Vector(
            center.x + normal.x * nudge,
            center.y + normal.y * nudge,
            center.z + normal.z * nudge,
        )
        cyl = b_.translate(cyl, start)

        result = b_.boolean_cut(s, cyl)
        vr = b_.get_volume(result)

        if vr >= v_before * (1 - _REL_TOL):
            return ForgeResult(
                shape=result, valid=False,
                volume_before=v_before, volume_after=vr,
                surface_area=b_.get_surface_area(result),
                diagnostics={
                    "reason": "hole did not reduce volume",
                    "hint": "hole may not intersect face — check face_selector and radius",
                },
            )
        return ForgeResult(
            shape=result, valid=True,
            volume_before=v_before, volume_after=vr,
            surface_area=b_.get_surface_area(result),
        )
    except Exception as e:
        return _fail("add_hole failed", exception=str(e))


def boolean_union(a: ForgeResult | Any, b: ForgeResult | Any) -> ForgeResult:
    try:
        sa = _extract_shape(a)
        sb = _extract_shape(b)
    except ValueError as e:
        return _fail("invalid input shape", exception=str(e))
    try:
        b_ = get_backend()
        va = b_.get_volume(sa)
        vb = b_.get_volume(sb)
        result = b_.boolean_union(sa, sb)
        vr = b_.get_volume(result)
        if vr <= max(va, vb) * (1 + _REL_TOL):
            return ForgeResult(
                shape=result, valid=False,
                volume_before=va + vb, volume_after=vr,
                surface_area=b_.get_surface_area(result),
                diagnostics={
                    "reason": "union did not increase volume",
                    "hint": "shapes may not overlap — verify operands intersect before union",
                },
            )
        return ForgeResult(
            shape=result, valid=True,
            volume_before=va + vb, volume_after=vr,
            surface_area=b_.get_surface_area(result),
        )
    except Exception as e:
        return _fail("boolean union failed", exception=str(e))


def boolean_cut(base: ForgeResult | Any, tool: ForgeResult | Any) -> ForgeResult:
    try:
        sb = _extract_shape(base)
        st = _extract_shape(tool)
    except ValueError as e:
        return _fail("invalid input shape", exception=str(e))
    try:
        b_ = get_backend()
        vbase = b_.get_volume(sb)
        result = b_.boolean_cut(sb, st)
        vr = b_.get_volume(result)
        if vr >= vbase * (1 - _REL_TOL):
            return ForgeResult(
                shape=result, valid=False,
                volume_before=vbase, volume_after=vr,
                surface_area=b_.get_surface_area(result),
                diagnostics={
                    "reason": "cut did not reduce volume",
                    "hint": "tool may not intersect base — verify overlap before cut",
                },
            )
        return ForgeResult(
            shape=result, valid=True,
            volume_before=vbase, volume_after=vr,
            surface_area=b_.get_surface_area(result),
        )
    except Exception as e:
        return _fail("boolean cut failed", exception=str(e))


def boolean_intersect(a: ForgeResult | Any, b: ForgeResult | Any) -> ForgeResult:
    try:
        sa = _extract_shape(a)
        sb = _extract_shape(b)
    except ValueError as e:
        return _fail("invalid input shape", exception=str(e))
    try:
        b_ = get_backend()
        va = b_.get_volume(sa)
        result = b_.boolean_intersect(sa, sb)
        vr = b_.get_volume(result)
        if vr < 1e-9:
            return ForgeResult(
                shape=result, valid=False,
                volume_before=va, volume_after=vr,
                diagnostics={
                    "reason": "intersection produced empty result",
                    "hint": "shapes may not overlap",
                },
            )
        return ForgeResult(
            shape=result, valid=True,
            volume_before=va, volume_after=vr,
            surface_area=b_.get_surface_area(result),
        )
    except Exception as e:
        return _fail("boolean intersect failed", exception=str(e))


def extrude(face: Any, direction: Vector, distance: float) -> ForgeResult:
    if distance <= 0:
        return _fail(f"distance must be > 0, got {distance}")
    try:
        b_ = get_backend()
        result = b_.extrude(face, direction, distance)
        vr = b_.get_volume(result)
        if vr < 1e-9:
            return _fail("extrude produced zero-volume shape")
        return ForgeResult(
            shape=result, valid=True,
            volume_after=vr, surface_area=b_.get_surface_area(result),
        )
    except Exception as e:
        return _fail("extrude failed", exception=str(e))


def sweep(profile: Any, path_wire: Any) -> ForgeResult:
    try:
        b_ = get_backend()
        result = b_.sweep(profile, path_wire)
        vr = b_.get_volume(result)
        if vr < 1e-9:
            return _fail("sweep produced zero-volume shape")
        return ForgeResult(
            shape=result, valid=True,
            volume_after=vr, surface_area=b_.get_surface_area(result),
        )
    except Exception as e:
        return _fail("sweep failed", exception=str(e))


def fillet(shape: ForgeResult | Any, radius: float, edge_selector: str | None = None) -> ForgeResult:
    if radius <= 0:
        return _fail(f"fillet radius must be > 0, got {radius}")
    try:
        shape = _extract_shape(shape)
        b_ = get_backend()
        v_before = b_.get_volume(shape)
        edges = None
        if edge_selector is not None:
            edges = b_.select_edges(shape, edge_selector)
            if not edges:
                return _fail(f"edge selector '{edge_selector}' matched no edges")
        result = b_.fillet(shape, radius, edges)
        vr = b_.get_volume(result)
        return ForgeResult(
            shape=result, valid=True,
            volume_before=v_before, volume_after=vr,
            surface_area=b_.get_surface_area(result),
        )
    except Exception as e:
        return ForgeResult(
            shape=None, valid=False,
            diagnostics={
                "reason": "fillet failed",
                "hint": "try heal() before fillet, or reduce radius",
                "exception": str(e),
            },
        )


def chamfer(shape: ForgeResult | Any, distance: float, edge_selector: str | None = None) -> ForgeResult:
    if distance <= 0:
        return _fail(f"chamfer distance must be > 0, got {distance}")
    try:
        shape = _extract_shape(shape)
        b_ = get_backend()
        v_before = b_.get_volume(shape)
        edges = None
        if edge_selector is not None:
            edges = b_.select_edges(shape, edge_selector)
            if not edges:
                return _fail(f"edge selector '{edge_selector}' matched no edges")
        result = b_.chamfer(shape, distance, edges)
        vr = b_.get_volume(result)
        return ForgeResult(
            shape=result, valid=True,
            volume_before=v_before, volume_after=vr,
            surface_area=b_.get_surface_area(result),
        )
    except Exception as e:
        return ForgeResult(
            shape=None, valid=False,
            diagnostics={
                "reason": "chamfer failed",
                "hint": "try heal() before chamfer, or reduce distance",
                "exception": str(e),
            },
        )


def translate(shape: ForgeResult | Any, vector: Vector) -> ForgeResult:
    try:
        shape = _extract_shape(shape)
        b_ = get_backend()
        result = b_.translate(shape, vector)
        return ForgeResult(
            shape=result, valid=True,
            volume_after=b_.get_volume(result),
            surface_area=b_.get_surface_area(result),
        )
    except Exception as e:
        return _fail("translate failed", exception=str(e))


def rotate(shape: ForgeResult | Any, axis_origin: Vector, axis_dir: Vector, angle_deg: float) -> ForgeResult:
    try:
        shape = _extract_shape(shape)
        b_ = get_backend()
        result = b_.rotate(shape, axis_origin, axis_dir, angle_deg)
        return ForgeResult(
            shape=result, valid=True,
            volume_after=b_.get_volume(result),
            surface_area=b_.get_surface_area(result),
        )
    except Exception as e:
        return _fail("rotate failed", exception=str(e))


def mirror(shape: ForgeResult | Any, plane_origin: Vector, plane_normal: Vector) -> ForgeResult:
    try:
        shape = _extract_shape(shape)
        b_ = get_backend()
        result = b_.mirror(shape, plane_normal, plane_origin)
        return ForgeResult(
            shape=result, valid=True,
            volume_after=b_.get_volume(result),
            surface_area=b_.get_surface_area(result),
        )
    except Exception as e:
        return _fail("mirror failed", exception=str(e))


def scale(shape: ForgeResult | Any, factor: float, origin: Vector = Vector(0, 0, 0)) -> ForgeResult:
    if factor <= 0:
        return _fail(f"scale factor must be > 0, got {factor}")
    try:
        shape = _extract_shape(shape)
        b_ = get_backend()
        if origin != Vector(0, 0, 0):
            shape = b_.translate(shape, Vector(-origin.x, -origin.y, -origin.z))
        result = b_.scale(shape, factor)
        if origin != Vector(0, 0, 0):
            result = b_.translate(result, origin)
        return ForgeResult(
            shape=result, valid=True,
            volume_after=b_.get_volume(result),
            surface_area=b_.get_surface_area(result),
        )
    except Exception as e:
        return _fail("scale failed", exception=str(e))
