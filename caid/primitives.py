from __future__ import annotations
import math
from .vector import Vector
from .result import ForgeResult
from ._backend import get_backend


def _fail(reason: str, **extra) -> ForgeResult:
    diag = {"reason": reason}
    diag.update(extra)
    return ForgeResult(shape=None, valid=False, diagnostics=diag)


def _positive_check(**kwargs) -> str | None:
    for name, val in kwargs.items():
        if val <= 0:
            return f"{name} must be > 0, got {val}"
    return None


def _vectors_parallel(a: Vector, b: Vector) -> bool:
    if a.Length < 1e-10 or b.Length < 1e-10:
        return False
    return a.cross(b).Length < 1e-10


def _reorient(shape, origin: Vector, axis: Vector, default_axis: Vector = Vector(0, 0, 1)):
    """Rotate shape from default_axis to axis, then translate to origin."""
    b = get_backend()
    if not _vectors_parallel(axis, default_axis):
        angle = default_axis.getAngle(axis) * 180.0 / math.pi
        cross = default_axis.cross(axis)
        if cross.Length > 1e-10:
            shape = b.rotate(shape, Vector(0, 0, 0), cross, angle)
    elif default_axis.dot(axis) < 0:
        # Anti-parallel: 180-degree flip around a perpendicular axis
        perp = Vector(1, 0, 0) if abs(default_axis.x) < 0.9 else Vector(0, 1, 0)
        shape = b.rotate(shape, Vector(0, 0, 0), perp, 180.0)
    if origin != Vector(0, 0, 0):
        shape = b.translate(shape, origin)
    return shape


def _success(shape) -> ForgeResult:
    b = get_backend()
    return ForgeResult(
        shape=shape, valid=True,
        volume_after=b.get_volume(shape),
        surface_area=b.get_surface_area(shape),
    )


def box(
    length: float,
    width: float,
    height: float,
    origin: Vector = Vector(0, 0, 0),
    x_dir: Vector = Vector(1, 0, 0),
    z_dir: Vector = Vector(0, 0, 1),
) -> ForgeResult:
    """Create a box. Origin is the corner (not center).
    x_dir and z_dir define the local coordinate frame.
    y_dir is derived as cross(z_dir, x_dir).
    """
    err = _positive_check(length=length, width=width, height=height)
    if err:
        return _fail(err)
    try:
        b = get_backend()
        shape = b.make_box(length, width, height)
        # Reorient if non-default coordinate frame
        default_x = Vector(1, 0, 0)
        default_z = Vector(0, 0, 1)
        needs_reorient = not _vectors_parallel(x_dir, default_x) or not _vectors_parallel(z_dir, default_z)
        if needs_reorient:
            # Build rotation from default frame to (x_dir, z_dir) frame
            # Default box is aligned with global XYZ; rotate to requested frame
            z_norm = z_dir.normalized()
            x_norm = x_dir.normalized()
            y_norm = z_norm.cross(x_norm)
            # Rotation matrix columns = new basis vectors
            # Apply via sequential rotations: align Z first, then twist around Z for X
            shape = _reorient(shape, Vector(0, 0, 0), z_norm, default_z)
            # After Z alignment, figure out where X landed and twist to match x_dir
            if not _vectors_parallel(z_norm, default_z):
                angle_z = default_z.getAngle(z_norm) * 180.0 / math.pi
                cross = default_z.cross(z_norm)
                if cross.Length > 1e-10:
                    # X axis rotated by same rotation — compute where it ended up
                    cos_a = math.cos(math.radians(angle_z))
                    sin_a = math.sin(math.radians(angle_z))
                    cn = cross.normalized()
                    # Rodrigues' rotation of default_x around cross by angle_z
                    dot = cn.x * default_x.x + cn.y * default_x.y + cn.z * default_x.z
                    cx = cn.cross(default_x)
                    rotated_x = Vector(
                        default_x.x * cos_a + cx.x * sin_a + cn.x * dot * (1 - cos_a),
                        default_x.y * cos_a + cx.y * sin_a + cn.y * dot * (1 - cos_a),
                        default_x.z * cos_a + cx.z * sin_a + cn.z * dot * (1 - cos_a),
                    )
                    # Now twist around z_norm to align rotated_x with x_norm
                    twist = rotated_x.getAngle(x_norm)
                    twist_cross = rotated_x.cross(x_norm)
                    if twist_cross.Length > 1e-10:
                        twist_sign = 1.0 if twist_cross.dot(z_norm) > 0 else -1.0
                        shape = b.rotate(shape, Vector(0, 0, 0), z_norm, twist_sign * twist * 180.0 / math.pi)
        if origin != Vector(0, 0, 0):
            shape = b.translate(shape, origin)
        return _success(shape)
    except Exception as e:
        return _fail("box creation failed", exception=str(e))


def cylinder(
    radius: float,
    height: float,
    origin: Vector = Vector(0, 0, 0),
    axis: Vector = Vector(0, 0, 1),
) -> ForgeResult:
    """Origin is the center of the bottom face. Axis is the extrusion direction."""
    err = _positive_check(radius=radius, height=height)
    if err:
        return _fail(err)
    try:
        shape = get_backend().make_cylinder(radius, height)
        shape = _reorient(shape, origin, axis)
        return _success(shape)
    except Exception as e:
        return _fail("cylinder creation failed", exception=str(e))


def sphere(
    radius: float,
    origin: Vector = Vector(0, 0, 0),
) -> ForgeResult:
    err = _positive_check(radius=radius)
    if err:
        return _fail(err)
    try:
        shape = get_backend().make_sphere(radius)
        if origin != Vector(0, 0, 0):
            shape = get_backend().translate(shape, origin)
        return _success(shape)
    except Exception as e:
        return _fail("sphere creation failed", exception=str(e))


def cone(
    radius_bottom: float,
    radius_top: float,
    height: float,
    origin: Vector = Vector(0, 0, 0),
    axis: Vector = Vector(0, 0, 1),
) -> ForgeResult:
    """radius_top=0 gives a true cone. radius_top > 0 gives a frustum."""
    err = _positive_check(radius_bottom=radius_bottom, height=height)
    if err:
        return _fail(err)
    if radius_top < 0:
        return _fail(f"radius_top must be >= 0, got {radius_top}")
    try:
        shape = get_backend().make_cone(radius_bottom, radius_top, height)
        shape = _reorient(shape, origin, axis)
        return _success(shape)
    except Exception as e:
        return _fail("cone creation failed", exception=str(e))


def torus(
    major_radius: float,
    minor_radius: float,
    origin: Vector = Vector(0, 0, 0),
    axis: Vector = Vector(0, 0, 1),
) -> ForgeResult:
    err = _positive_check(major_radius=major_radius, minor_radius=minor_radius)
    if err:
        return _fail(err)
    if minor_radius >= major_radius:
        return _fail(
            f"minor_radius ({minor_radius}) must be < major_radius ({major_radius})",
            hint="a self-intersecting torus is not a valid solid",
        )
    try:
        shape = get_backend().make_torus(major_radius, minor_radius)
        shape = _reorient(shape, origin, axis)
        return _success(shape)
    except Exception as e:
        return _fail("torus creation failed", exception=str(e))
