from __future__ import annotations
from typing import Any
from build123d import Solid, Vector
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


def add_hole(
    shape: ForgeResult | Any,
    radius: float,
    depth: float | None = None,
    face_selector: str = ">Z",
) -> ForgeResult:
    """Cut a cylindrical hole through a face of a solid.

    Uses boolean cut with a cylinder positioned at the center of the selected face.
    """
    if radius <= 0:
        return _fail(f"hole radius must be > 0, got {radius}")
    try:
        s = _extract_shape(shape)
        b_ = get_backend()
        v_before = b_.get_volume(s)

        # Find the target face using selector
        faces = s.faces()
        target_face = _select_face(faces, face_selector)
        if target_face is None:
            return _fail(f"face selector '{face_selector}' matched no face")

        # Get face center and normal for hole placement
        center = target_face.center()
        normal = target_face.normal_at(center)

        # Determine hole depth: if None, use shape bounding box diagonal
        if depth is None:
            bb = s.bounding_box()
            depth = bb.diagonal * 2  # ensure through-hole

        # Build a cylinder tool along the inward normal (opposite face normal)
        cyl = Solid.make_cylinder(radius, depth)
        # Position: translate to center, oriented along -normal
        # Default cylinder is along Z, so rotate from Z to -normal
        from build123d import Axis
        neg_normal = Vector(-normal.X, -normal.Y, -normal.Z)
        z_axis = Vector(0, 0, 1)

        # Place cylinder: start above center along normal, cut downward
        start = Vector(
            center.X + normal.X * depth * 0.1,
            center.Y + normal.Y * depth * 0.1,
            center.Z + normal.Z * depth * 0.1,
        )

        # Rotate cylinder from Z-axis to -normal direction
        cross = z_axis.cross(neg_normal)
        if cross.length > 1e-10:
            angle = z_axis.get_angle(neg_normal) * 180.0 / 3.141592653589793
            ax = Axis(Vector(0, 0, 0), cross)
            cyl = cyl.rotate(ax, angle)
        elif neg_normal.Z < 0:
            # 180 degree flip
            ax = Axis(Vector(0, 0, 0), Vector(1, 0, 0))
            cyl = cyl.rotate(ax, 180.0)

        cyl = cyl.translate(start)
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


def _select_face(faces, selector: str):
    """Select a face using CQ-style selector strings (>Z, <Z, >X, etc.)."""
    if not faces:
        return None
    sel = selector.strip()
    if len(sel) < 2:
        return faces[0] if faces else None

    axis_map = {"X": Vector(1, 0, 0), "Y": Vector(0, 1, 0), "Z": Vector(0, 0, 1)}
    op = sel[0]
    axis_key = sel[1:].upper()
    axis_vec = axis_map.get(axis_key)
    if axis_vec is None:
        return faces[0] if faces else None

    def _center_val(f):
        c = f.center()
        return c.X * axis_vec.X + c.Y * axis_vec.Y + c.Z * axis_vec.Z

    if op == ">":
        return max(faces, key=_center_val)
    elif op == "<":
        return min(faces, key=_center_val)
    return faces[0] if faces else None


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
            shape = b_.translate(shape, Vector(-origin.X, -origin.Y, -origin.Z))
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
