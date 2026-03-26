from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from cadquery import Vector

from .result import ForgeResult
from ._backend import get_backend
from . import ops


@dataclass
class Part:
    name: str
    shape: Any
    origin: Vector = field(default_factory=lambda: Vector(0, 0, 0))
    metadata: dict = field(default_factory=dict)


class Assembly:
    """An ordered collection of Parts. All operations return new instances."""

    def __init__(self, parts: list[Part] | None = None):
        self._parts: list[Part] = list(parts) if parts else []

    def add(self, part: Part) -> Assembly:
        return Assembly(self._parts + [part])

    def remove(self, name: str) -> Assembly:
        return Assembly([p for p in self._parts if p.name != name])

    def move(self, name: str, vector: Vector) -> Assembly:
        new_parts = []
        b = get_backend()
        for p in self._parts:
            if p.name == name:
                new_shape = b.translate(p.shape, vector)
                new_origin = Vector(
                    p.origin.x + vector.x,
                    p.origin.y + vector.y,
                    p.origin.z + vector.z,
                )
                new_parts.append(Part(p.name, new_shape, new_origin, dict(p.metadata)))
            else:
                new_parts.append(p)
        return Assembly(new_parts)

    def rotate_part(self, name: str, axis_origin: Vector, axis_dir: Vector, angle_deg: float) -> Assembly:
        new_parts = []
        b = get_backend()
        for p in self._parts:
            if p.name == name:
                new_shape = b.rotate(p.shape, axis_origin, axis_dir, angle_deg)
                new_parts.append(Part(p.name, new_shape, p.origin, dict(p.metadata)))
            else:
                new_parts.append(p)
        return Assembly(new_parts)

    def get(self, name: str) -> Part | None:
        for p in self._parts:
            if p.name == name:
                return p
        return None

    def merge_all(self) -> ForgeResult:
        if not self._parts:
            return ForgeResult(
                shape=None, valid=False,
                diagnostics={"reason": "assembly is empty"},
            )
        if len(self._parts) == 1:
            b = get_backend()
            s = self._parts[0].shape
            return ForgeResult(
                shape=s, valid=True,
                volume_after=b.get_volume(s),
                surface_area=b.get_surface_area(s),
            )
        result = self._parts[0].shape
        for p in self._parts[1:]:
            r = ops.boolean_union(result, p.shape)
            if not r.ok:
                return r
            result = r.shape
        b = get_backend()
        return ForgeResult(
            shape=result, valid=True,
            volume_after=b.get_volume(result),
            surface_area=b.get_surface_area(result),
        )

    def to_dict(self) -> list[dict]:
        return [
            {
                "name": p.name,
                "origin": [p.origin.x, p.origin.y, p.origin.z],
                "metadata": p.metadata,
            }
            for p in self._parts
        ]
