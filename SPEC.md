# CAiD — build handoff

## What this is

A Python abstraction layer that sits between AI agents and CadQuery/OCCT. The goal is not to replace CadQuery but to wrap it with a stable, agent-friendly API that validates geometry, eliminates footguns, and exposes a swappable backend seam so individual operations can be migrated to direct OCCT calls without a rewrite.

This document is the complete specification. Build exactly what is described here. Do not add features not listed. Do not use CadQuery's `Workplane` chaining API in the public-facing layer — all public functions must be stateless and explicit.

---

## Repository layout

```
caid/
  __init__.py        # re-exports public API only
  result.py          # ForgeResult dataclass — build this first
  _backend.py        # BackendProtocol + CadQueryBackend
  ops.py             # boolean, extrude, sweep, fillet, chamfer
  primitives.py      # box, cylinder, sphere, cone, torus
  heal.py            # shape healing and validity checking
  compound.py        # array_on_curve, belt_wire, pulley_assembly
  assembly.py        # positioning and multi-shape management
  export.py          # STL, STEP, BREP export
  preview.py         # shape → PIL.Image in-process render

tests/
  test_result.py
  test_ops.py
  test_primitives.py
  test_heal.py
  test_compound.py
  test_assembly.py
  test_export.py
  test_preview.py
  conftest.py        # shared fixtures

pyproject.toml
SPEC.md
```

---

## Dependencies — pin these exactly

```toml
[project]
name = "caid"
requires-python = ">=3.11"

dependencies = [
  "cadquery==2.4.0",
  "trimesh==4.4.3",
  "pyrender==0.1.45",
  "Pillow==10.3.0",
  "numpy>=1.26,<2.0",
]

[project.optional-dependencies]
dev = [
  "pytest==8.2.0",
  "pytest-cov==5.0.0",
]
```

CadQuery 2.4.0 bundles its own OCP build (`cadquery-ocp`). Do not install pythonOCC-core separately — it will conflict. If you need a direct OCCT call, import from `OCP.Core.*` inside the already-installed CadQuery environment. Note: CadQuery 2.4.0 uses `OCP.*` not the older `OCC.Core.*` namespace.

---

## Build order

Build and test each module before starting the next. The order is a dependency chain.

1. `result.py`
2. `_backend.py`
3. `primitives.py`
4. `ops.py`
5. `heal.py`
6. `assembly.py`
7. `export.py`
8. `preview.py`
9. `compound.py`

---

## Module specifications

### `result.py`

The central data contract. Every public function in every other module returns a `ForgeResult`. No exceptions.

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass
class ForgeResult:
    shape: Any | None                        # cadquery Shape or None on failure
    valid: bool                              # False if geometry is degenerate or operation failed
    volume_before: float | None = None       # mm³, None if not applicable
    volume_after: float | None = None        # mm³, None if not applicable
    surface_area: float | None = None        # mm², populated on success
    diagnostics: dict = field(default_factory=dict)
    # diagnostics keys: "reason" (str), "hint" (str), "check" (str), "exception" (str)

    @property
    def ok(self) -> bool:
        return self.valid and self.shape is not None

    def unwrap(self) -> Any:
        """Return shape or raise ValueError with diagnostics."""
        if not self.ok:
            raise ValueError(f"ForgeResult failed: {self.diagnostics}")
        return self.shape
```

Rules:
- `valid=False` must be set whenever: shape is None, volume did not change when it should have, topology checks fail, or any exception is caught.
- `diagnostics["reason"]` must always be a human-readable string explaining what went wrong.
- `diagnostics["hint"]` should suggest a fix when one is known (e.g. "shapes may not be overlapping — check that boolean operands intersect").
- Never raise exceptions from public functions. Catch internally and return `ForgeResult(shape=None, valid=False, diagnostics={"reason": ..., "exception": str(e)})`.
- **Important**: Export functions return `shape=None, valid=True` on success. This means `.ok` is `False` for successful exports. Use `.valid` to check export success.

---

### `_backend.py`

Defines the backend protocol and the default CadQuery implementation. Nothing outside this module should import from `cadquery` directly except `heal.py` which needs OCP internals, and `export.py` which needs CQ importers.

```python
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
    # returns (vertices: np.ndarray shape (N,3), faces: np.ndarray shape (M,3))

class CadQueryBackend:
    """Default backend. Implements BackendProtocol via cadquery."""
    # implement each method using cq.Workplane or cq.Shape directly
    # do not expose Workplane objects in return values — always return cq.Shape
```

The backend instance is module-level state in `_backend.py`:

```python
_active_backend: BackendProtocol = CadQueryBackend()

def get_backend() -> BackendProtocol:
    return _active_backend

def set_backend(backend: BackendProtocol) -> None:
    global _active_backend
    _active_backend = backend
```

**CadQuery-specific notes**:
- `makeSphere` defaults to a hemisphere (angleDegrees1=0, angleDegrees2=90). Use `angleDegrees1=-90, angleDegrees2=90` for a full sphere.
- `fillet(radius, edges)` and `chamfer(distance, None, edges)` take edge lists as positional args.
- `rotate(startVec, endVec, angleDeg)` — pass `axis_origin` and `axis_origin + axis_dir` as the two vectors.

---

### `primitives.py`

Stateless shape constructors. All positions and orientations are explicit. No workplane state.

```python
from cadquery import Vector
from .result import ForgeResult

def box(
    length: float,
    width: float,
    height: float,
    origin: Vector = Vector(0, 0, 0),
    x_dir: Vector = Vector(1, 0, 0),
    z_dir: Vector = Vector(0, 0, 1),
) -> ForgeResult:
    """
    Create a box. Origin is the corner (not center).
    x_dir and z_dir define the local coordinate frame.
    y_dir is derived as cross(z_dir, x_dir).
    """

def cylinder(
    radius: float,
    height: float,
    origin: Vector = Vector(0, 0, 0),
    axis: Vector = Vector(0, 0, 1),
) -> ForgeResult:
    """Origin is the center of the bottom face. Axis is the extrusion direction."""

def sphere(
    radius: float,
    origin: Vector = Vector(0, 0, 0),
) -> ForgeResult:

def cone(
    radius_bottom: float,
    radius_top: float,
    height: float,
    origin: Vector = Vector(0, 0, 0),
    axis: Vector = Vector(0, 0, 1),
) -> ForgeResult:
    """radius_top=0 gives a true cone. radius_top > 0 gives a frustum."""

def torus(
    major_radius: float,
    minor_radius: float,
    origin: Vector = Vector(0, 0, 0),
    axis: Vector = Vector(0, 0, 1),
) -> ForgeResult:
```

Each function must:
- Validate that all dimension arguments are > 0.
- Return `ForgeResult(valid=False, ...)` with a clear diagnostic if validation fails.
- Populate `volume_after` and `surface_area` on success.

---

### `ops.py`

Boolean operations and geometric transforms. All validated.

```python
from cadquery import Vector
from .result import ForgeResult

def boolean_union(a: ForgeResult | Any, b: ForgeResult | Any) -> ForgeResult:
    """
    Union two shapes. Validates that volume increased.
    If volume_after <= max(volume_a, volume_b), sets valid=False with hint
    "shapes may not overlap — verify operands intersect before union".
    Accepts either ForgeResult or raw shape.
    """

def boolean_cut(base: ForgeResult | Any, tool: ForgeResult | Any) -> ForgeResult:
    """
    Subtract tool from base. Validates that volume decreased.
    If volume_after >= volume_base, sets valid=False with hint
    "tool may not intersect base — verify overlap before cut".
    """

def boolean_intersect(a: ForgeResult | Any, b: ForgeResult | Any) -> ForgeResult:
    """Intersection. Validates that result is non-empty (volume > 0)."""

def extrude(
    face: Any,
    direction: Vector,
    distance: float,
) -> ForgeResult:
    """
    Extrude a face in an explicit direction.
    direction is normalised internally — magnitude is ignored.
    distance must be > 0.
    No workplane conventions. No implicit axis.
    """

def sweep(
    profile: Any,
    path_wire: Any,
) -> ForgeResult:
    """Sweep profile along path_wire. Checks result topology after."""

def fillet(shape: Any, radius: float, edge_selector: str | None = None) -> ForgeResult:
    """
    Fillet edges. edge_selector is a CadQuery selector string e.g. ">Z".
    If None, fillets all edges.
    radius must be small enough that it does not exceed the minimum edge length.
    If fillet fails (common with large radii), returns valid=False with hint.
    """

def chamfer(shape: Any, distance: float, edge_selector: str | None = None) -> ForgeResult:
    """Same conventions as fillet."""

def translate(shape: Any, vector: Vector) -> ForgeResult:
def rotate(shape: Any, axis_origin: Vector, axis_dir: Vector, angle_deg: float) -> ForgeResult:
def mirror(shape: Any, plane_origin: Vector, plane_normal: Vector) -> ForgeResult:
def scale(shape: Any, factor: float, origin: Vector = Vector(0, 0, 0)) -> ForgeResult:
```

Volume validation tolerance: use 1e-4 relative tolerance. `abs(v_after - v_before) / max(v_before, 1e-9) < 1e-4` means the operation changed nothing meaningful.

All operations route through the backend — `mirror` and `scale` do not call shape methods directly.

---

### `heal.py`

Shape healing and validity checking. This module uses OCP internals directly.

```python
from typing import Any
from .result import ForgeResult

def check_valid(shape: Any) -> dict:
    """
    Run OCCT validity checks. Returns a dict with keys:
      "is_valid": bool
      "has_degenerate_faces": bool
      "has_small_faces": bool         # faces with area < 1e-6 mm²
      "has_bad_edges": bool
      "has_self_intersections": bool
      "n_faces": int
      "n_edges": int
      "n_vertices": int
    Uses BRepCheck_Analyzer internally.
    """

def heal(shape: Any, precision: float = 1e-3) -> ForgeResult:
    """
    Attempt to fix a shape using OCCT's ShapeFix suite.
    Runs in order:
      1. ShapeFix_Shape (general fix)
      2. ShapeFix_Solid (close open shells into solids)
      3. ShapeUpgrade_UnifySameDomain (merge coplanar faces, simplify)
    Note: ShapeFix_Face was removed from the pipeline — it operates on
    isolated face copies and does not propagate fixes back into the parent shape.
    Returns healed shape if valid after fixing, else valid=False.
    diagnostics["checks_before"] and diagnostics["checks_after"] should
    contain the output of check_valid() run before and after healing.
    """

def simplify(shape: Any, tolerance: float = 0.01) -> ForgeResult:
    """
    Merge coplanar/co-cylindrical faces using ShapeUpgrade_UnifySameDomain.
    Useful after boolean operations that leave unnecessary face boundaries.
    """
```

Import pattern for OCP internals (CadQuery 2.4.0 uses `OCP`, not `OCC.Core`):
```python
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.ShapeFix import ShapeFix_Shape, ShapeFix_Solid
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX, TopAbs_SOLID
from OCP.TopoDS import TopoDS
```

---

### `assembly.py`

Manages collections of positioned shapes. Does not use CadQuery's `Assembly` internally — builds on the primitives and ops modules directly to keep the dependency surface narrow.

```python
from __future__ import annotations
from dataclasses import dataclass, field
from cadquery import Vector
from typing import Any
from .result import ForgeResult

@dataclass
class Part:
    name: str
    shape: Any
    origin: Vector = field(default_factory=lambda: Vector(0, 0, 0))
    metadata: dict = field(default_factory=dict)

class Assembly:
    """
    An ordered collection of Parts.
    All operations return new Assembly instances (immutable pattern).
    """

    def add(self, part: Part) -> Assembly:
        """Return new Assembly with part appended."""

    def remove(self, name: str) -> Assembly:
        """Return new Assembly with named part removed."""

    def move(self, name: str, vector: Vector) -> Assembly:
        """Translate a named part. Returns new Assembly."""

    def rotate_part(self, name: str, axis_origin: Vector, axis_dir: Vector, angle_deg: float) -> Assembly:
        """Rotate a named part. Returns new Assembly."""

    def get(self, name: str) -> Part | None:
        """Return named part or None."""

    def merge_all(self) -> ForgeResult:
        """Boolean union of all parts into one shape."""

    def to_dict(self) -> list[dict]:
        """
        Serialise to a list of dicts for agent inspection.
        Each dict: {"name": str, "origin": [x,y,z], "metadata": dict}
        Shape is not serialised (not JSON-safe).
        """
```

---

### `export.py`

Thin, explicit export functions. No magic format detection.

```python
from pathlib import Path
from typing import Any
from .result import ForgeResult

def to_stl(shape: Any, path: str | Path, tolerance: float = 0.1, angular_tolerance: float = 0.1) -> ForgeResult:
    """
    Export to binary STL.
    tolerance and angular_tolerance control mesh quality (mm, radians).
    Returns ForgeResult with shape=None, valid=True on success.
    valid=False if export fails, with diagnostics["reason"].
    Checks the boolean return value of exportStl and verifies the file exists.
    """

def to_step(shape: Any, path: str | Path) -> ForgeResult:
    """Export to STEP AP214. Lossless B-rep format. Preferred for interchange."""

def to_brep(shape: Any, path: str | Path) -> ForgeResult:
    """Export to native OCCT BREP. Lossless, fastest, OCCT-only."""

def from_step(path: str | Path) -> ForgeResult:
    """Import from STEP. Returns shape in ForgeResult."""

def from_brep(path: str | Path) -> ForgeResult:
    """Import from BREP."""
```

---

### `preview.py`

In-process render to PIL Image. No subprocess. No temp files.

```python
from typing import Any
from PIL import Image
from .result import ForgeResult

def preview(
    shape: Any,
    size: tuple[int, int] = (512, 512),
    view: str = "iso",              # "iso" | "top" | "front" | "right"
    background: tuple = (40, 40, 40),
) -> Image.Image | None:
    """
    Render shape to PIL Image using trimesh + pyrender.
    Pipeline:
      1. Tessellate shape via backend.tessellate(shape, tolerance=0.05)
      2. Build trimesh.Trimesh from vertices + faces, fix normals
      3. Create pyrender.Mesh from trimesh
      4. Set camera based on view argument:
           iso:   azimuth=45°, elevation=35°
           top:   azimuth=0°, elevation=90°
           front: azimuth=0°, elevation=0°
           right: azimuth=90°, elevation=0°
      5. Auto-fit camera distance to bounding sphere
      6. Render to numpy array, convert to PIL.Image.fromarray()
    Returns None on failure (pyrender environment issues are common in
    headless/MCP contexts — never raise, always return None).
    """

def preview_multi(
    shapes: list[Any],
    colors: list[tuple] | None = None,
    size: tuple[int, int] = (512, 512),
    view: str = "iso",
    background: tuple = (40, 40, 40),
) -> Image.Image | None:
    """Render multiple shapes in one scene. colors is list of (R,G,B,A) 0-255."""
```

Note: pyrender requires an OpenGL context. In headless environments (MCP, CI) it falls back to `pyrender.OffscreenRenderer`. If even that fails, return `None` silently. The caller should handle `None` gracefully.

---

### `compound.py`

High-value compound geometry operations.

```python
from cadquery import Vector
from typing import Any
from .result import ForgeResult

def array_on_curve(
    shape: Any,
    path_wire: Any,
    count: int,
    start: float = 0.0,
    end: float = 1.0,
    align_to_curve: bool = True,
) -> ForgeResult:
    """
    Stamp `count` copies of shape along path_wire.
    start and end are normalised path positions (0.0–1.0).
    If align_to_curve=True, each copy is rotated to align its Z axis
    with the curve tangent at that point.

    Returns ForgeResult where shape is a list of shapes (not merged).
    diagnostics["failed_indices"] lists any copy indices that produced invalid geometry.
    """

def belt_wire(
    pulleys: list[tuple[Vector, float]],
    closed: bool = True,
) -> ForgeResult:
    """
    Build a closed wire representing a belt or track around a set of pulleys.
    Each pulley is (center: Vector, radius: float). Centers are assumed coplanar (XY plane).

    Returns ForgeResult with the wire as shape.
    diagnostics["n_edges"] should report the total edge count.
    """

def pulley_assembly(
    pulleys: list[tuple[Vector, float]],
    profile: Any,
) -> ForgeResult:
    """
    Build a swept solid around a pulley system.
    Calls belt_wire internally, then ops.sweep(profile, wire).
    profile should be a 2D face in the XY plane centered at the wire start point.
    """
```

---

## Testing strategy

Geometry tests cannot use equality assertions on shapes. Use these patterns instead:

```python
# Pattern 1: volume check
def test_box_volume():
    r = box(10, 20, 30)
    assert r.ok
    assert abs(r.volume_after - 6000.0) < 0.01

# Pattern 2: boolean changes volume
def test_boolean_cut_reduces_volume():
    base = box(10, 10, 10).unwrap()
    tool = box(5, 5, 5, origin=Vector(0, 0, 5)).unwrap()
    r = boolean_cut(base, tool)
    assert r.ok
    assert r.volume_after < r.volume_before

# Pattern 3: invalid operation is caught
def test_boolean_cut_no_overlap():
    base = box(10, 10, 10).unwrap()
    tool = box(5, 5, 5, origin=Vector(100, 100, 100)).unwrap()  # no overlap
    r = boolean_cut(base, tool)
    assert not r.ok
    assert "reason" in r.diagnostics

# Pattern 4: export roundtrip (use .valid not .ok for exports)
def test_step_roundtrip(tmp_path):
    r = box(10, 10, 10)
    out = tmp_path / "test.step"
    export_r = to_step(r.shape, out)
    assert export_r.valid  # NOT .ok — exports have shape=None
    import_r = from_step(out)
    assert import_r.ok
    assert abs(import_r.volume_after - r.volume_after) < 0.1

# Pattern 5: topology check
def test_heal_fixes_degenerate(degenerate_shape):
    checks = check_valid(degenerate_shape)
    assert not checks["is_valid"]
    r = heal(degenerate_shape)
    assert r.ok
    checks_after = check_valid(r.shape)
    assert checks_after["is_valid"]
```

`conftest.py` should provide fixtures for:
- A simple valid box shape
- A cylinder
- A two-pulley belt wire setup

Every test file should import only from the public `caid` API, never from submodules directly. This validates the `__init__.py` export surface.

---

## `__init__.py` — public surface

Export exactly these names and nothing else:

```python
from .result import ForgeResult
from .primitives import box, cylinder, sphere, cone, torus
from .ops import (
    boolean_union, boolean_cut, boolean_intersect,
    extrude, sweep, fillet, chamfer,
    translate, rotate, mirror, scale,
)
from .heal import check_valid, heal, simplify
from .assembly import Assembly, Part
from .export import to_stl, to_step, to_brep, from_step, from_brep
from .preview import preview, preview_multi
from .compound import array_on_curve, belt_wire, pulley_assembly
from ._backend import get_backend, set_backend

__all__ = [
    "ForgeResult",
    "box", "cylinder", "sphere", "cone", "torus",
    "boolean_union", "boolean_cut", "boolean_intersect",
    "extrude", "sweep", "fillet", "chamfer",
    "translate", "rotate", "mirror", "scale",
    "check_valid", "heal", "simplify",
    "Assembly", "Part",
    "to_stl", "to_step", "to_brep", "from_step", "from_brep",
    "preview", "preview_multi",
    "array_on_curve", "belt_wire", "pulley_assembly",
    "get_backend", "set_backend",
]
```

---

## Known environment issues

**CadQuery 2.4.0 uses OCP, not OCC.Core**: Import OCCT internals from `OCP.*` (e.g. `from OCP.BRepCheck import BRepCheck_Analyzer`), not from `OCC.Core.*`.

**CadQuery's makeSphere is a hemisphere by default**: `cq.Solid.makeSphere(r)` produces a hemisphere (angleDegrees1=0, angleDegrees2=90). The backend corrects this by passing `angleDegrees1=-90, angleDegrees2=90`.

**pyrender in headless/MCP context**: pyrender may fail to initialise an OpenGL context. Always wrap pyrender calls in try/except and return None from preview functions on failure. In MCP contexts, use the shell-based render pipeline instead.

**CadQuery import time**: First import of cadquery takes 3–8 seconds while it initialises OCCT. This is normal.

**OCCT boolean failures produce no exception**: Some degenerate booleans silently return the original shape. This is why the volume check in `ops.py` is mandatory, not optional.

**fillet on complex shapes**: OCCT's fillet algorithm is fragile on shapes with small faces or near-tangent edges produced by booleans. If `fillet()` fails, the hint should say "try heal() before fillet, or reduce radius". Do not attempt to work around this at the ops layer — surface the failure clearly.

**trimesh winding**: `tessellate()` in `CadQueryBackend` must return consistently-wound faces (outward normals). Use `trimesh.repair.fix_normals()` after creating the Trimesh object in `preview.py`.

**ShapeFix_Face does not propagate**: `ShapeFix_Face` operates on face copies and does not write fixes back into the parent shape's topology. It was removed from the heal pipeline for this reason.

**Install via conda, not pip**: CadQuery 2.4.0 must be installed via conda-forge (`conda install -c conda-forge cadquery=2.4.0`). Pip install fails on the `nlopt` dependency build.

---

## What this layer explicitly does not do

- No constraint-based or parametric modelling. All geometry is imperative.
- No NURBS surface fitting or subdivision. `heal.py` uses OCCT's own surface repair, not custom fitting.
- No direct C++ OCCT extension. All work is Python-level.
- No GUI or interactive viewer. `preview.py` returns a PIL Image — display is the caller's problem.
- No cloud or remote rendering.
