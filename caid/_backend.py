from __future__ import annotations
import math
from typing import Protocol, Any, runtime_checkable

from .vector import Vector
import numpy as np

from OCP.BRepPrimAPI import (
    BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeSphere,
    BRepPrimAPI_MakeCone, BRepPrimAPI_MakeTorus, BRepPrimAPI_MakePrism,
)
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse, BRepAlgoAPI_Cut, BRepAlgoAPI_Common
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet, BRepFilletAPI_MakeChamfer
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipe
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.BRep import BRep_Tool
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Trsf, gp_Vec, gp_Pnt, gp_Ax1, gp_Ax2, gp_Dir


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
    def wrap_shape(self, ocp_shape: Any) -> Any: ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unwrap(shape: Any):
    """Get the raw OCP TopoDS_Shape from any shape type."""
    if hasattr(shape, "wrapped"):
        return shape.wrapped
    return shape


def _get_edges(shape) -> list:
    """Collect all edges from a shape via TopExp_Explorer."""
    wrapped = _unwrap(shape)
    edges = []
    exp = TopExp_Explorer(wrapped, TopAbs_EDGE)
    while exp.More():
        edges.append(TopoDS.Edge_s(exp.Current()))
        exp.Next()
    return edges


def _edge_center(edge) -> tuple[float, float, float]:
    """Get the midpoint of an edge."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    adaptor = BRepAdaptor_Curve(edge)
    u_mid = (adaptor.FirstParameter() + adaptor.LastParameter()) / 2.0
    pnt = adaptor.Value(u_mid)
    return (pnt.X(), pnt.Y(), pnt.Z())


def _edge_tangent_at_mid(edge) -> tuple[float, float, float]:
    """Get the tangent direction at the midpoint of an edge."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    adaptor = BRepAdaptor_Curve(edge)
    u_mid = (adaptor.FirstParameter() + adaptor.LastParameter()) / 2.0
    pnt = adaptor.Value(u_mid)
    # Use GCPnts or direct derivative
    from OCP.BRepLProp import BRepLProp_CLProps
    props = BRepLProp_CLProps(adaptor, u_mid, 1, 1e-6)
    d1 = props.D1()
    mag = math.sqrt(d1.X()**2 + d1.Y()**2 + d1.Z()**2)
    if mag < 1e-15:
        return (0, 0, 0)
    return (d1.X() / mag, d1.Y() / mag, d1.Z() / mag)


def _filter_edges(edges: list, selector: str) -> list:
    """Filter edges using CadQuery-style selector strings.

    Supports: >X, <X, >Y, <Y, >Z, <Z (max/min center along axis),
              |X, |Y, |Z (parallel to axis).
    """
    if not edges:
        return []

    axis_map = {"X": 0, "Y": 1, "Z": 2}
    sel = selector.strip()
    if len(sel) < 2:
        return list(edges)

    op = sel[0]
    axis_idx = axis_map.get(sel[1:].upper())
    if axis_idx is None:
        return list(edges)

    if op in (">", "<"):
        centers = [(_edge_center(e), e) for e in edges]
        vals = [(c[axis_idx], e) for c, e in centers]
        target = max(v for v, _ in vals) if op == ">" else min(v for v, _ in vals)
        tol = 1e-6
        return [e for v, e in vals if abs(v - target) < tol]

    elif op == "|":
        axis_vec = [0.0, 0.0, 0.0]
        axis_vec[axis_idx] = 1.0
        result = []
        for edge in edges:
            tx, ty, tz = _edge_tangent_at_mid(edge)
            # Cross product magnitude with axis — zero means parallel
            cx = ty * axis_vec[2] - tz * axis_vec[1]
            cy = tz * axis_vec[0] - tx * axis_vec[2]
            cz = tx * axis_vec[1] - ty * axis_vec[0]
            cross_mag = math.sqrt(cx*cx + cy*cy + cz*cz)
            if cross_mag < 1e-6:
                result.append(edge)
        return result

    return list(edges)


# ---------------------------------------------------------------------------
# OCP Backend — direct OpenCascade, no CadQuery
# ---------------------------------------------------------------------------

class OCPBackend:
    """Backend using direct OCP (OpenCascade) calls. No CadQuery dependency."""

    # --- Primitives ---

    def make_box(self, l: float, w: float, h: float) -> Any:
        return BRepPrimAPI_MakeBox(l, w, h).Shape()

    def make_cylinder(self, radius: float, height: float) -> Any:
        return BRepPrimAPI_MakeCylinder(radius, height).Shape()

    def make_sphere(self, radius: float) -> Any:
        return BRepPrimAPI_MakeSphere(radius).Shape()

    def make_cone(self, r1: float, r2: float, height: float) -> Any:
        return BRepPrimAPI_MakeCone(r1, r2, height).Shape()

    def make_torus(self, r1: float, r2: float) -> Any:
        return BRepPrimAPI_MakeTorus(r1, r2).Shape()

    # --- Booleans ---

    def boolean_union(self, a: Any, b: Any) -> Any:
        return BRepAlgoAPI_Fuse(_unwrap(a), _unwrap(b)).Shape()

    def boolean_cut(self, a: Any, b: Any) -> Any:
        return BRepAlgoAPI_Cut(_unwrap(a), _unwrap(b)).Shape()

    def boolean_intersect(self, a: Any, b: Any) -> Any:
        return BRepAlgoAPI_Common(_unwrap(a), _unwrap(b)).Shape()

    # --- Extrude / Sweep ---

    def extrude(self, face: Any, direction: Vector, distance: float) -> Any:
        d = direction.normalized()
        vec = gp_Vec(d.x * distance, d.y * distance, d.z * distance)
        return BRepPrimAPI_MakePrism(_unwrap(face), vec).Shape()

    def sweep(self, profile: Any, path: Any) -> Any:
        return BRepOffsetAPI_MakePipe(_unwrap(path), _unwrap(profile)).Shape()

    # --- Fillet / Chamfer ---

    def fillet(self, shape: Any, radius: float, edges: list | None = None) -> Any:
        wrapped = _unwrap(shape)
        maker = BRepFilletAPI_MakeFillet(wrapped)
        if edges is None:
            edges = _get_edges(shape)
        for edge in edges:
            maker.Add(radius, _unwrap(edge))
        return maker.Shape()

    def chamfer(self, shape: Any, distance: float, edges: list | None = None) -> Any:
        wrapped = _unwrap(shape)
        maker = BRepFilletAPI_MakeChamfer(wrapped)
        if edges is None:
            edges = _get_edges(shape)
        for edge in edges:
            maker.Add(distance, _unwrap(edge))
        return maker.Shape()

    # --- Properties ---

    def get_volume(self, shape: Any) -> float:
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(_unwrap(shape), props)
        return props.Mass()

    def get_surface_area(self, shape: Any) -> float:
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(_unwrap(shape), props)
        return props.Mass()

    # --- Transforms ---

    def translate(self, shape: Any, vector: Vector) -> Any:
        trsf = gp_Trsf()
        trsf.SetTranslation(gp_Vec(vector.x, vector.y, vector.z))
        return BRepBuilderAPI_Transform(_unwrap(shape), trsf, True).Shape()

    def rotate(self, shape: Any, axis_origin: Vector, axis_dir: Vector, angle_deg: float) -> Any:
        if axis_dir.Length < 1e-15:
            raise ValueError("rotate axis_dir must be non-zero")
        trsf = gp_Trsf()
        ax = gp_Ax1(
            gp_Pnt(axis_origin.x, axis_origin.y, axis_origin.z),
            gp_Dir(axis_dir.x, axis_dir.y, axis_dir.z),
        )
        trsf.SetRotation(ax, math.radians(angle_deg))
        return BRepBuilderAPI_Transform(_unwrap(shape), trsf, True).Shape()

    def mirror(self, shape: Any, plane_normal: Vector, plane_origin: Vector) -> Any:
        if plane_normal.Length < 1e-15:
            raise ValueError("mirror plane_normal must be non-zero")
        trsf = gp_Trsf()
        ax2 = gp_Ax2(
            gp_Pnt(plane_origin.x, plane_origin.y, plane_origin.z),
            gp_Dir(plane_normal.x, plane_normal.y, plane_normal.z),
        )
        trsf.SetMirror(ax2)
        return BRepBuilderAPI_Transform(_unwrap(shape), trsf, True).Shape()

    def scale(self, shape: Any, factor: float) -> Any:
        trsf = gp_Trsf()
        trsf.SetScale(gp_Pnt(0, 0, 0), factor)
        return BRepBuilderAPI_Transform(_unwrap(shape), trsf, True).Shape()

    # --- Edge selection ---

    def select_edges(self, shape: Any, selector: str) -> list:
        edges = _get_edges(shape)
        return _filter_edges(edges, selector)

    # --- Tessellation ---

    def tessellate(self, shape: Any, tolerance: float = 0.1) -> tuple[np.ndarray, np.ndarray]:
        wrapped = _unwrap(shape)
        BRepMesh_IncrementalMesh(wrapped, tolerance)

        all_verts = []
        all_faces = []
        vert_offset = 0

        exp = TopExp_Explorer(wrapped, TopAbs_FACE)
        while exp.More():
            face = TopoDS.Face_s(exp.Current())
            loc = TopLoc_Location()
            tri = BRep_Tool.Triangulation_s(face, loc)
            if tri is not None:
                trsf = loc.Transformation()
                for i in range(1, tri.NbNodes() + 1):
                    pnt = tri.Node(i).Transformed(trsf)
                    all_verts.append([pnt.X(), pnt.Y(), pnt.Z()])
                for i in range(1, tri.NbTriangles() + 1):
                    t = tri.Triangle(i)
                    i1, i2, i3 = t.Get()
                    all_faces.append([
                        i1 - 1 + vert_offset,
                        i2 - 1 + vert_offset,
                        i3 - 1 + vert_offset,
                    ])
                vert_offset += tri.NbNodes()
            exp.Next()

        if not all_verts:
            return np.empty((0, 3), dtype=np.float64), np.empty((0, 3), dtype=np.int32)

        return np.array(all_verts, dtype=np.float64), np.array(all_faces, dtype=np.int32)

    # --- Shape wrapping ---

    def wrap_shape(self, ocp_shape: Any) -> Any:
        """OCP backend: shapes are already raw TopoDS_Shape, return as-is."""
        return ocp_shape


# ---------------------------------------------------------------------------
# Active backend — default is now OCPBackend (no CadQuery)
# ---------------------------------------------------------------------------

_active_backend: BackendProtocol = OCPBackend()


def get_backend() -> BackendProtocol:
    return _active_backend


def set_backend(backend: BackendProtocol) -> None:
    global _active_backend
    _active_backend = backend
