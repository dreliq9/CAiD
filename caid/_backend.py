from __future__ import annotations
import math
from typing import Protocol, Any, runtime_checkable

import cadquery as cq
from cadquery import Vector
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


class CadQueryBackend:
    """Default backend. Implements BackendProtocol via cadquery."""

    def make_box(self, l: float, w: float, h: float) -> Any:
        return cq.Solid.makeBox(l, w, h)

    def make_cylinder(self, radius: float, height: float) -> Any:
        return cq.Solid.makeCylinder(radius, height)

    def make_sphere(self, radius: float) -> Any:
        return cq.Solid.makeSphere(radius, angleDegrees1=-90, angleDegrees2=90)

    def make_cone(self, r1: float, r2: float, height: float) -> Any:
        return cq.Solid.makeCone(r1, r2, height)

    def make_torus(self, r1: float, r2: float) -> Any:
        return cq.Solid.makeTorus(r1, r2)

    def boolean_union(self, a: Any, b: Any) -> Any:
        return a.fuse(b)

    def boolean_cut(self, a: Any, b: Any) -> Any:
        return a.cut(b)

    def boolean_intersect(self, a: Any, b: Any) -> Any:
        return a.intersect(b)

    def extrude(self, face: Any, direction: Vector, distance: float) -> Any:
        d = direction.normalized()
        vec = Vector(d.x * distance, d.y * distance, d.z * distance)
        outer = face.outerWire()
        inner = [w for w in face.Wires() if not w.IsSame(outer)]
        return cq.Solid.extrudeLinear(outer, inner, vec)

    def sweep(self, profile: Any, path: Any) -> Any:
        return cq.Solid.sweep(profile, [], path)

    def fillet(self, shape: Any, radius: float, edges: list | None = None) -> Any:
        if edges is None:
            edges = shape.Edges()
        return shape.fillet(radius, edges)

    def chamfer(self, shape: Any, distance: float, edges: list | None = None) -> Any:
        if edges is None:
            edges = shape.Edges()
        return shape.chamfer(distance, None, edges)

    def get_volume(self, shape: Any) -> float:
        return shape.Volume()

    def get_surface_area(self, shape: Any) -> float:
        return shape.Area()

    def translate(self, shape: Any, vector: Vector) -> Any:
        return shape.translate(vector)

    def rotate(self, shape: Any, axis_origin: Vector, axis_dir: Vector, angle_deg: float) -> Any:
        return shape.rotate(axis_origin, axis_origin + axis_dir, angle_deg)

    def mirror(self, shape: Any, plane_normal: Vector, plane_origin: Vector) -> Any:
        return shape.mirror(plane_normal, plane_origin)

    def scale(self, shape: Any, factor: float) -> Any:
        return shape.scale(factor)

    def select_edges(self, shape: Any, selector: str) -> list:
        return cq.Workplane().add(shape).edges(selector).vals()

    def tessellate(self, shape: Any, tolerance: float = 0.1) -> tuple[np.ndarray, np.ndarray]:
        verts, faces = shape.tessellate(tolerance)
        v_array = np.array([[v.x, v.y, v.z] for v in verts], dtype=np.float64)
        f_array = np.array(faces, dtype=np.int32)
        return v_array, f_array


_active_backend: BackendProtocol = CadQueryBackend()


def get_backend() -> BackendProtocol:
    return _active_backend


def set_backend(backend: BackendProtocol) -> None:
    global _active_backend
    _active_backend = backend
