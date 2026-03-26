from __future__ import annotations
import math
from typing import Protocol, Any, runtime_checkable

from build123d import Solid, Vector, Axis, Plane, Edge, Wire, Face, Shape
import numpy as np


@runtime_checkable
class BackendProtocol(Protocol):
    def make_box(self, l: float, w: float, h: float) -> Any: ...
    def make_cylinder(self, radius: float, height: float) -> Any: ...
    def make_sphere(self, radius: float) -> Any: ...
    def make_cone(self, r1: float, r2: float, height: float) -> Any: ...
    def make_torus(self, r1: float, r2: float) -> Any: ...
    def boolean_union(self, a: Any, b: Any) -> Any: ...
    def boolean_cut(self, a: Any, b: Any) -> Any: ...
    def boolean_intersect(self, a: Any, b: Any) -> Any: ...
    def extrude(self, face: Any, direction: Vector, distance: float) -> Any: ...
    def sweep(self, profile: Any, path: Any) -> Any: ...
    def fillet(self, shape: Any, radius: float, edges: list | None = None) -> Any: ...
    def chamfer(self, shape: Any, distance: float, edges: list | None = None) -> Any: ...
    def get_volume(self, shape: Any) -> float: ...
    def get_surface_area(self, shape: Any) -> float: ...
    def translate(self, shape: Any, vector: Vector) -> Any: ...
    def rotate(self, shape: Any, axis_origin: Vector, axis_dir: Vector, angle_deg: float) -> Any: ...
    def mirror(self, shape: Any, plane_normal: Vector, plane_origin: Vector) -> Any: ...
    def scale(self, shape: Any, factor: float) -> Any: ...
    def select_edges(self, shape: Any, selector: str) -> list: ...
    def tessellate(self, shape: Any, tolerance: float = 0.1) -> tuple[np.ndarray, np.ndarray]: ...


class Build123dBackend:
    """Default backend. Implements BackendProtocol via build123d."""

    def make_box(self, l: float, w: float, h: float) -> Any:
        return Solid.make_box(l, w, h)

    def make_cylinder(self, radius: float, height: float) -> Any:
        return Solid.make_cylinder(radius, height)

    def make_sphere(self, radius: float) -> Any:
        return Solid.make_sphere(radius)

    def make_cone(self, r1: float, r2: float, height: float) -> Any:
        return Solid.make_cone(r1, r2, height)

    def make_torus(self, r1: float, r2: float) -> Any:
        return Solid.make_torus(r1, r2)

    def boolean_union(self, a: Any, b: Any) -> Any:
        return a.fuse(b)

    def boolean_cut(self, a: Any, b: Any) -> Any:
        return a.cut(b)

    def boolean_intersect(self, a: Any, b: Any) -> Any:
        return a.intersect(b)

    def extrude(self, face: Any, direction: Vector, distance: float) -> Any:
        d = direction.normalized()
        vec = Vector(d.X * distance, d.Y * distance, d.Z * distance)
        return Solid.extrude(face, vec)

    def sweep(self, profile: Any, path: Any) -> Any:
        return Solid.sweep(profile, path)

    def fillet(self, shape: Any, radius: float, edges: list | None = None) -> Any:
        if edges is None:
            edges = shape.edges()
        return shape.fillet(radius, edges)

    def chamfer(self, shape: Any, distance: float, edges: list | None = None) -> Any:
        if edges is None:
            edges = shape.edges()
        return shape.chamfer(distance, None, edges)

    def get_volume(self, shape: Any) -> float:
        return shape.volume

    def get_surface_area(self, shape: Any) -> float:
        return shape.area

    def translate(self, shape: Any, vector: Vector) -> Any:
        return shape.translate(vector)

    def rotate(self, shape: Any, axis_origin: Vector, axis_dir: Vector, angle_deg: float) -> Any:
        ax = Axis(axis_origin, axis_dir)
        return shape.rotate(ax, angle_deg)

    def mirror(self, shape: Any, plane_normal: Vector, plane_origin: Vector) -> Any:
        p = Plane(plane_origin, z_dir=plane_normal)
        return shape.mirror(p)

    def scale(self, shape: Any, factor: float) -> Any:
        return shape.scale(factor)

    def select_edges(self, shape: Any, selector: str) -> list:
        # build123d edge filtering by selector string
        # Common selectors: ">Z", "<Z", ">X", "|Z", etc.
        all_edges = shape.edges()
        return _filter_edges(all_edges, selector)

    def tessellate(self, shape: Any, tolerance: float = 0.1) -> tuple[np.ndarray, np.ndarray]:
        verts, faces = shape.tessellate(tolerance)
        v_array = np.array([[v.X, v.Y, v.Z] for v in verts], dtype=np.float64)
        f_array = np.array(faces, dtype=np.int32)
        return v_array, f_array


def _filter_edges(edges, selector: str) -> list:
    """Filter edges using CadQuery-style selector strings.

    Supports: >X, <X, >Y, <Y, >Z, <Z (max/min along axis),
              |X, |Y, |Z (parallel to axis).
    """
    if not edges:
        return []

    axis_map = {"X": Vector(1, 0, 0), "Y": Vector(0, 1, 0), "Z": Vector(0, 0, 1)}
    sel = selector.strip()

    if len(sel) < 2:
        return list(edges)

    op = sel[0]
    axis_key = sel[1:].upper()
    axis_vec = axis_map.get(axis_key)
    if axis_vec is None:
        return list(edges)

    if op in (">", "<"):
        # Sort edges by center position along axis, return those at max/min
        def _center_val(e):
            c = e.center()
            return c.X * axis_vec.X + c.Y * axis_vec.Y + c.Z * axis_vec.Z

        vals = [(e, _center_val(e)) for e in edges]
        if op == ">":
            target = max(v for _, v in vals)
        else:
            target = min(v for _, v in vals)
        tol = 1e-6
        return [e for e, v in vals if abs(v - target) < tol]

    elif op == "|":
        # Edges parallel to axis
        result = []
        for e in edges:
            tangent = e.tangent_at(0.5)
            cross = tangent.cross(axis_vec)
            if cross.length < 1e-6:
                result.append(e)
        return result

    return list(edges)


_active_backend: BackendProtocol = Build123dBackend()


def get_backend() -> BackendProtocol:
    return _active_backend


def set_backend(backend: BackendProtocol) -> None:
    global _active_backend
    _active_backend = backend
