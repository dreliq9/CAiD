from __future__ import annotations
import math
from typing import Any

from .vector import Vector
from ._backend import get_backend

from OCP.BRepAdaptor import BRepAdaptor_CompCurve
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform, BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
from OCP.GC import GC_MakeArcOfCircle
from OCP.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Trsf, gp_Ax2
from OCP.BRepLProp import BRepLProp_CLProps

from .result import ForgeResult
from .heal import check_valid
from . import ops


def _fail(reason: str, **extra) -> ForgeResult:
    diag = {"reason": reason}
    diag.update(extra)
    return ForgeResult(shape=None, valid=False, diagnostics=diag)


def _get_wrapped(shape: Any):
    if hasattr(shape, "wrapped"):
        return shape.wrapped
    return shape


def array_on_curve(
    shape: Any,
    path_wire: Any,
    count: int,
    start: float = 0.0,
    end: float = 1.0,
    align_to_curve: bool = True,
) -> ForgeResult:
    if count <= 0:
        return _fail(f"count must be > 0, got {count}")
    if not (0.0 <= start < end <= 1.0):
        return _fail(f"start/end must satisfy 0 <= start < end <= 1, got start={start}, end={end}")
    try:
        wire_wrapped = _get_wrapped(path_wire)
        shape_wrapped = _get_wrapped(shape)

        adaptor = BRepAdaptor_CompCurve(wire_wrapped)
        u_first = adaptor.FirstParameter()
        u_last = adaptor.LastParameter()
        u_range = u_last - u_first

        if count == 1:
            params = [u_first + (start + end) / 2.0 * u_range]
        else:
            params = [
                u_first + (start + i * (end - start) / (count - 1)) * u_range
                for i in range(count)
            ]

        results = []
        failed_indices = []

        for idx, u in enumerate(params):
            pnt = adaptor.Value(u)

            trsf = gp_Trsf()
            if align_to_curve:
                props = BRepLProp_CLProps(adaptor, 1, 1e-6)
                props.SetParameter(u)
                tangent = props.D1()
                tan_dir = gp_Dir(tangent)

                # Build local frame: Z aligned to tangent, X perpendicular
                ref = gp_Dir(0, 0, 1)
                if abs(tan_dir.Dot(ref)) > 0.99:
                    ref = gp_Dir(1, 0, 0)
                x_vec = gp_Vec(ref).Crossed(gp_Vec(tan_dir))
                x_dir = gp_Dir(x_vec)
                ax2 = gp_Ax2(pnt, tan_dir, x_dir)

                trsf.SetTransformation(ax2)
                trsf.Invert()
            else:
                trsf.SetTranslation(gp_Vec(pnt.X(), pnt.Y(), pnt.Z()))

            builder = BRepBuilderAPI_Transform(shape_wrapped, trsf, True)
            builder.Build()
            if not builder.IsDone():
                failed_indices.append(idx)
                continue

            new_shape = get_backend().wrap_shape(builder.Shape())
            checks = check_valid(new_shape)
            if not checks["is_valid"]:
                failed_indices.append(idx)
            else:
                results.append(new_shape)

        diag = {}
        if failed_indices:
            diag["failed_indices"] = failed_indices

        return ForgeResult(
            shape=results,
            valid=len(results) > 0,
            diagnostics=diag,
        )
    except Exception as e:
        return _fail("array_on_curve failed", exception=str(e))


def _compute_tangent_data(centers, radii, n):
    """Compute tangent contact points for each adjacent pulley pair.

    Returns a dict mapping pulley index to [outgoing_point, incoming_point],
    where each point is an (x, y) tuple on the pulley's circle.
    """
    tangent_points = {i: [None, None] for i in range(n)}

    for i in range(n):
        j = (i + 1) % n
        cx1, cy1 = centers[i]
        cx2, cy2 = centers[j]
        r1, r2 = radii[i], radii[j]

        dx, dy = cx2 - cx1, cy2 - cy1
        dist = math.hypot(dx, dy)
        angle_between = math.atan2(dy, dx)

        ratio = (r1 - r2) / dist if dist > 1e-9 else 0.0
        alpha = math.asin(max(-1.0, min(1.0, ratio))) if abs(ratio) <= 1.0 else 0.0
        tangent_angle = angle_between + math.pi / 2 - alpha

        cos_t, sin_t = math.cos(tangent_angle), math.sin(tangent_angle)
        tangent_points[i][0] = (cx1 + r1 * cos_t, cy1 + r1 * sin_t)  # outgoing
        tangent_points[j][1] = (cx2 + r2 * cos_t, cy2 + r2 * sin_t)  # incoming

    return tangent_points


def belt_wire(
    pulleys: list[tuple[Vector, float]],
    closed: bool = True,
) -> ForgeResult:
    if len(pulleys) < 2:
        return _fail("need at least 2 pulleys")
    try:
        centers = [(p[0].x, p[0].y) for p in pulleys]
        radii = [p[1] for p in pulleys]
        z_val = pulleys[0][0].z
        n = len(pulleys)

        # Validate no coincident pulleys
        for i in range(n):
            j = (i + 1) % n
            if not closed and j == 0:
                break
            dist = math.hypot(centers[j][0] - centers[i][0], centers[j][1] - centers[i][1])
            if dist < 1e-9:
                return _fail(f"pulleys {i} and {j} are coincident")

        if not closed:
            # Open belt: tangent lines only, no arcs
            tp = _compute_tangent_data(centers, radii, n)
            edges = []
            for i in range(n - 1):
                j = i + 1
                out = tp[i][0]
                inc = tp[j][1]
                if out and inc:
                    p1 = gp_Pnt(out[0], out[1], z_val)
                    p2 = gp_Pnt(inc[0], inc[1], z_val)
                    edges.append(BRepBuilderAPI_MakeEdge(p1, p2).Edge())
            wire_builder = BRepBuilderAPI_MakeWire()
            for e in edges:
                wire_builder.Add(e)
            if not wire_builder.IsDone():
                return _fail("failed to assemble open belt wire")
            return ForgeResult(
                shape=get_backend().wrap_shape(wire_builder.Wire()), valid=True,
                diagnostics={"n_edges": len(edges)},
            )

        # Closed belt: alternating arcs and tangent lines
        tp = _compute_tangent_data(centers, radii, n)
        all_edges = []

        for i in range(n):
            j = (i + 1) % n
            inc = tp[i][1]   # incoming point on pulley i
            out = tp[i][0]   # outgoing point on pulley i
            cx, cy = centers[i]
            r = radii[i]

            if inc is not None and out is not None:
                p_in = gp_Pnt(inc[0], inc[1], z_val)
                p_out = gp_Pnt(out[0], out[1], z_val)

                # Arc midpoint via angle bisector on the circle
                a_in = math.atan2(inc[1] - cy, inc[0] - cx)
                a_out = math.atan2(out[1] - cy, out[0] - cx)
                a_diff = a_out - a_in
                if a_diff < 0:
                    a_diff += 2 * math.pi
                a_mid = a_in + a_diff / 2.0
                p_mid = gp_Pnt(cx + r * math.cos(a_mid), cy + r * math.sin(a_mid), z_val)

                arc = GC_MakeArcOfCircle(p_in, p_mid, p_out)
                all_edges.append(BRepBuilderAPI_MakeEdge(arc.Value()).Edge())

            # Tangent line from outgoing on pulley i to incoming on pulley j
            inc_j = tp[j][1]
            if out is not None and inc_j is not None:
                p1 = gp_Pnt(out[0], out[1], z_val)
                p2 = gp_Pnt(inc_j[0], inc_j[1], z_val)
                all_edges.append(BRepBuilderAPI_MakeEdge(p1, p2).Edge())

        wire_builder = BRepBuilderAPI_MakeWire()
        for e in all_edges:
            wire_builder.Add(e)
        if not wire_builder.IsDone():
            return _fail("failed to assemble belt wire")

        return ForgeResult(
            shape=get_backend().wrap_shape(wire_builder.Wire()), valid=True,
            diagnostics={"n_edges": len(all_edges)},
        )
    except Exception as e:
        return _fail("belt_wire failed", exception=str(e))


def pulley_assembly(
    pulleys: list[tuple[Vector, float]],
    profile: Any,
) -> ForgeResult:
    wire_result = belt_wire(pulleys, closed=True)
    if not wire_result.ok:
        return wire_result

    profile_wire = profile
    if hasattr(profile, "outerWire"):
        profile_wire = profile.outerWire()

    return ops.sweep(profile_wire, wire_result.shape)
