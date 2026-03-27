# CAiD Roadmap: CadQuery → OCP Migration

> **Status: COMPLETED** — Migration finished 2026-03-26. CAiD now talks directly to OCCT via OCP. CadQuery has been fully removed as a dependency. This document is preserved as historical reference for the migration that was done.

---

CAiD's long-term direction is to replace CadQuery internals with direct OCP (OpenCascade) calls, making CAiD itself the high-level API layer. CadQuery becomes unnecessary — CAiD talks to the kernel directly while keeping its validation, ForgeResult pattern, and BackendProtocol abstraction.

## Architecture

```
Current:    MCP tools  →  CAiD (validation)  →  CadQuery (API)  →  OCP (kernel)
Target:     MCP tools  →  CAiD (validation + API)  →  OCP (kernel)
```

The migration path is already built into the codebase: `_backend.py` defines a `BackendProtocol` with 20 methods. The current `CadQueryBackend` implements all 20. The plan is to write an `OCPBackend` that implements the same protocol, test it against the CadQuery backend for identical output, then swap the default.

Each tier below is independently shippable. Merge one, verify in caid-mcp, then start the next.

---

## Tier 1 — Transforms + Primitives

**Effort:** Small. All are near-direct OCP API calls.
**Risk:** Low. Easy to verify — create shape, compare volume/bounding box.
**Why first:** Highest call frequency in caid-mcp, simplest OCP equivalents.

### Transforms (4 methods)

| Method | CadQuery call | OCP replacement |
|--------|--------------|-----------------|
| `translate(shape, vector)` | `shape.translate(vector)` | `gp_Trsf.SetTranslation(gp_Vec)` + `BRepBuilderAPI_Transform` |
| `rotate(shape, origin, axis, angle)` | `shape.rotate(origin, end, angle)` | `gp_Trsf.SetRotation(gp_Ax1, radians)` + `BRepBuilderAPI_Transform` |
| `scale(shape, factor)` | `shape.scale(factor)` | `gp_Trsf.SetScale(gp_Pnt, factor)` + `BRepBuilderAPI_Transform` |
| `mirror(shape, normal, origin)` | `shape.mirror(normal, origin)` | `gp_Trsf.SetMirror(gp_Ax2)` + `BRepBuilderAPI_Transform` |

### Primitives (5 methods)

| Method | CadQuery call | OCP replacement |
|--------|--------------|-----------------|
| `make_box(l, w, h)` | `cq.Solid.makeBox(l, w, h)` | `BRepPrimAPI_MakeBox(l, w, h).Shape()` |
| `make_cylinder(r, h)` | `cq.Solid.makeCylinder(r, h)` | `BRepPrimAPI_MakeCylinder(r, h).Shape()` |
| `make_sphere(r)` | `cq.Solid.makeSphere(r, -90, 90)` | `BRepPrimAPI_MakeSphere(r).Shape()` |
| `make_cone(r1, r2, h)` | `cq.Solid.makeCone(r1, r2, h)` | `BRepPrimAPI_MakeCone(r1, r2, h).Shape()` |
| `make_torus(R, r)` | `cq.Solid.makeTorus(R, r)` | `BRepPrimAPI_MakeTorus(R, r).Shape()` |

### Validation to preserve
- `primitives.py` has a `_reorient()` helper that repositions shapes to arbitrary origins/axes using Rodrigues' rotation. This math stays — it just applies via `gp_Trsf` instead of CadQuery's `translate`/`rotate`.
- Positive-value checks on dimensions remain unchanged.
- `ForgeResult` wrapping unchanged.

### Testing strategy
For each method: create shape with both backends, compare `Volume()`, `BoundingBox()`, and `check_valid()`. Volumes must match within 1e-6. Bounding boxes within tolerance.

---

## Tier 2 — Booleans + Import/Export

**Effort:** Small-medium. Booleans are direct swaps. Export needs mesh generation.
**Risk:** Medium. Booleans are where OCCT segfaults live — subprocess isolation (already in caid-mcp) mitigates this.
**Why second:** Second-highest usage. Export/import completes the "build → validate → export" loop.

### Booleans (3 methods)

| Method | CadQuery call | OCP replacement |
|--------|--------------|-----------------|
| `boolean_union(a, b)` | `a.fuse(b)` | `BRepAlgoAPI_Fuse(a, b).Shape()` |
| `boolean_cut(a, b)` | `a.cut(b)` | `BRepAlgoAPI_Cut(a, b).Shape()` |
| `boolean_intersect(a, b)` | `a.intersect(b)` | `BRepAlgoAPI_Common(a, b).Shape()` |

### Volume/Area (2 methods)

| Method | CadQuery call | OCP replacement |
|--------|--------------|-----------------|
| `get_volume(shape)` | `shape.Volume()` | `GProp_GProps` via `BRepGProp.VolumeProperties_s()` |
| `get_surface_area(shape)` | `shape.Area()` | `GProp_GProps` via `BRepGProp.SurfaceProperties_s()` |

### Import/Export

| Method | CadQuery call | OCP replacement |
|--------|--------------|-----------------|
| `to_stl()` | `shape.exportStl()` | `BRepMesh_IncrementalMesh` + `StlAPI_Writer` |
| `to_step()` | `shape.exportStep()` | `STEPControl_Writer` |
| `to_brep()` | `shape.exportBrep()` | `BRepTools.Write_s()` (already used in caid-mcp) |
| `from_step()` | `cq.importers.importStep()` | `STEPControl_Reader` |
| `from_brep()` | `cq.Shape.importBrep()` | `BRepTools.Read_s()` + `BRep_Builder` |

### Validation to preserve
- Boolean volume validation (union must increase, cut must decrease, intersect must be non-zero).
- Export file-exists checks.
- `ForgeResult` diagnostics with hints.

---

## Tier 3 — Modifications

**Effort:** Medium. The OCP fillet/chamfer APIs are straightforward, but edge selection is the hard part.
**Risk:** Medium. Edge selector replacement is the most complex single task.

### Fillet + Chamfer (2 methods)

| Method | CadQuery call | OCP replacement |
|--------|--------------|-----------------|
| `fillet(shape, r, edges)` | `shape.fillet(r, edges)` | `BRepFilletAPI_MakeFillet` — add edges, `Build()` |
| `chamfer(shape, d, edges)` | `shape.chamfer(d, None, edges)` | `BRepFilletAPI_MakeChamfer` — add edges, `Build()` |

These are easy **if edges are already selected**. The hard part is `select_edges()`.

### Edge Selector (1 method — the big one)

| Method | CadQuery call | OCP replacement |
|--------|--------------|-----------------|
| `select_edges(shape, selector)` | `cq.Workplane().add(shape).edges(selector).vals()` | Custom `TopExp_Explorer` + geometric filtering |

CadQuery selector strings to support:

| Selector | Meaning | OCP approach |
|----------|---------|--------------|
| `">Z"` | Edges at max Z | `TopExp_Explorer(EDGE)` → filter by bounding box Z |
| `"<Z"` | Edges at min Z | Same, min Z |
| `">X"`, `">Y"`, etc. | Axis extremes | Same pattern for each axis |
| `"\|Z"` | Edges parallel to Z | Check edge tangent direction vs axis |
| `"\|X"`, `"\|Y"` | Edges parallel to axis | Same |
| `"not \|Z"` | Edges not parallel to Z | Negate the parallel filter |

**Implementation plan:** Build a `parse_selector(selector_str) → filter_fn` that returns a callable. The callable takes a list of edges and returns the filtered subset. This replaces CadQuery's selector engine with ~80-100 lines of OCP topology traversal.

### Extrude + Sweep (2 methods)

| Method | CadQuery call | OCP replacement |
|--------|--------------|-----------------|
| `extrude(face, dir, dist)` | `cq.Solid.extrudeLinear(outer, inner, vec)` | `BRepPrimAPI_MakePrism(face, gp_Vec)` |
| `sweep(profile, path)` | `cq.Solid.sweep(profile, [], path)` | `BRepOffsetAPI_MakePipe(wire, profile)` |

Extrude is straightforward with `MakePrism`. Sweep has edge cases around profile orientation and self-intersection that CadQuery handles — will need testing.

### Tessellate (1 method)

| Method | CadQuery call | OCP replacement |
|--------|--------------|-----------------|
| `tessellate(shape, tol)` | `shape.tessellate(tol)` | `BRepMesh_IncrementalMesh` + `TopExp_Explorer(FACE)` + `BRep_Tool.Triangulation_s()` to extract verts/faces per face, then merge |

---

## Tier 4 — Drop CadQuery

**Effort:** Small (cleanup pass).
**Precondition:** All 20 BackendProtocol methods implemented in OCPBackend and passing tests.

1. Set `OCPBackend` as the default in `_backend.py`
2. Remove `CadQueryBackend` class (or keep as optional legacy backend)
3. Remove `import cadquery` from all modules
4. Remove `cadquery` from `pyproject.toml` dependencies
5. Replace `cadquery.Vector` usage with `gp_Vec` / `gp_Pnt` (or a lightweight `Vector` class in CAiD)
6. Update README, SPEC.md
7. Bump major version

### Vector migration note
`cadquery.Vector` is used throughout CAiD's public API (primitives, transforms). Options:
- **A)** Define a simple `caid.Vector` dataclass that wraps `gp_Vec` — keeps the API stable
- **B)** Accept `tuple[float, float, float]` everywhere — simpler, no class needed
- **C)** Accept both via union type — most flexible

Recommend **(A)** for API stability. The `caid.Vector` class can convert to/from `gp_Vec` and `gp_Pnt` internally.

---

## Already Done (No Migration Needed)

These modules already use pure OCP:

| Module | Functions |
|--------|-----------|
| `heal.py` | `check_valid()`, `heal()`, `simplify()` |
| `compound.py` | `belt_wire()`, `array_on_curve()` |
| `assembly.py` | `Assembly` class (pure Python data management) |

---

## Testing Strategy

Each tier gets a test suite that runs the same operations through both backends and compares results:

```python
@pytest.mark.parametrize("backend", [CadQueryBackend(), OCPBackend()])
def test_box_volume(backend):
    set_backend(backend)
    fr = box(10, 20, 30)
    assert abs(fr.volume_after - 6000.0) < 1e-3
```

Additionally, run the full caid-mcp tool suite against the new backend before merging each tier. The MCP server is the real integration test.

---

## Milestones

| Milestone | What ships | CadQuery calls remaining |
|-----------|-----------|-------------------------|
| Today | CadQueryBackend (all 20 methods) | 20 |
| Tier 1 | OCPBackend: transforms + primitives | 11 |
| Tier 2 | OCPBackend: booleans + import/export | 3 |
| Tier 3 | OCPBackend: fillet, chamfer, selectors, extrude, sweep, tessellate | 0 |
| Tier 4 | CadQuery removed from dependencies | 0 (dependency gone) |
