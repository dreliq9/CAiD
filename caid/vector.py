"""Lightweight 3D vector for CAiD's public API.

Drop-in replacement for cadquery.Vector — no external dependencies.
Internally wraps gp_Vec/gp_Pnt when OCP is available, but works
standalone for pure math (cross, dot, normalize, angle).
"""
from __future__ import annotations
import math


class Vector:
    """Immutable 3D vector with the operations CAiD needs."""

    __slots__ = ("_x", "_y", "_z")

    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0):
        self._x = float(x)
        self._y = float(y)
        self._z = float(z)

    # --- Properties ---

    @property
    def x(self) -> float:
        return self._x

    @property
    def y(self) -> float:
        return self._y

    @property
    def z(self) -> float:
        return self._z

    @property
    def Length(self) -> float:
        return math.sqrt(self._x ** 2 + self._y ** 2 + self._z ** 2)

    # --- Vector math ---

    def cross(self, other: Vector) -> Vector:
        return Vector(
            self._y * other._z - self._z * other._y,
            self._z * other._x - self._x * other._z,
            self._x * other._y - self._y * other._x,
        )

    def dot(self, other: Vector) -> float:
        return self._x * other._x + self._y * other._y + self._z * other._z

    def normalized(self) -> Vector:
        mag = self.Length
        if mag < 1e-15:
            return Vector(0, 0, 0)
        return Vector(self._x / mag, self._y / mag, self._z / mag)

    def getAngle(self, other: Vector) -> float:
        """Angle between two vectors in radians."""
        denom = self.Length * other.Length
        if denom < 1e-15:
            return 0.0
        d = max(-1.0, min(1.0, self.dot(other) / denom))
        return math.acos(d)

    # --- Arithmetic ---

    def __add__(self, other: Vector) -> Vector:
        return Vector(self._x + other._x, self._y + other._y, self._z + other._z)

    def __sub__(self, other: Vector) -> Vector:
        return Vector(self._x - other._x, self._y - other._y, self._z - other._z)

    def __neg__(self) -> Vector:
        return Vector(-self._x, -self._y, -self._z)

    def __mul__(self, scalar: float) -> Vector:
        return Vector(self._x * scalar, self._y * scalar, self._z * scalar)

    def __rmul__(self, scalar: float) -> Vector:
        return self.__mul__(scalar)

    # --- Comparison ---

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Vector):
            return NotImplemented
        return (
            abs(self._x - other._x) < 1e-10
            and abs(self._y - other._y) < 1e-10
            and abs(self._z - other._z) < 1e-10
        )

    def __ne__(self, other: object) -> bool:
        eq = self.__eq__(other)
        if eq is NotImplemented:
            return NotImplemented
        return not eq

    def __hash__(self) -> int:
        return hash((round(self._x, 8), round(self._y, 8), round(self._z, 8)))

    # --- OCP conversion ---

    def to_pnt(self):
        """Convert to OCP gp_Pnt."""
        from OCP.gp import gp_Pnt
        return gp_Pnt(self._x, self._y, self._z)

    def to_vec(self):
        """Convert to OCP gp_Vec."""
        from OCP.gp import gp_Vec
        return gp_Vec(self._x, self._y, self._z)

    def to_dir(self):
        """Convert to OCP gp_Dir (unit vector). Raises ValueError on zero vector."""
        if self.Length < 1e-15:
            raise ValueError("Cannot convert zero vector to gp_Dir")
        from OCP.gp import gp_Dir
        return gp_Dir(self._x, self._y, self._z)

    @classmethod
    def from_pnt(cls, pnt) -> Vector:
        """Create from OCP gp_Pnt."""
        return cls(pnt.X(), pnt.Y(), pnt.Z())

    @classmethod
    def from_vec(cls, vec) -> Vector:
        """Create from OCP gp_Vec."""
        return cls(vec.X(), vec.Y(), vec.Z())

    # --- Display ---

    def __repr__(self) -> str:
        return f"Vector({self._x}, {self._y}, {self._z})"

    def to_tuple(self) -> tuple[float, float, float]:
        return (self._x, self._y, self._z)
