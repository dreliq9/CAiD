# CAiD

An agent-friendly abstraction layer over [CadQuery](https://cadquery.readthedocs.io/) and OpenCASCADE. Every geometry operation returns a `ForgeResult` with volume tracking, validation, and diagnostics — so silent OCCT failures get caught automatically.

Built for AI agents that need reliable 3D modeling without wrestling with CadQuery's Workplane chaining or OCCT's silent failure modes.

## Install

```bash
# CadQuery requires conda (OCCT dependency)
conda create -n cadforge python=3.11 -y
conda activate cadforge
conda install -c conda-forge cadquery -y

pip install caid
```

## Quick Example

```python
import caid

# Create a box, add a hole, fillet the edges
box = caid.box(40, 30, 10)
print(box.ok)          # True
print(box.volume_after) # 12000.0

with_hole = caid.add_hole(box, radius=2.7, depth=10)
filleted = caid.fillet(with_hole, radius=1.5, edge_selector=">Z")

# Export
caid.to_stl(filleted, "bracket.stl")
caid.to_step(filleted, "bracket.step")

# Check validity
report = caid.check_valid(filleted)
print(report)  # {'is_valid': True, 'n_faces': 10, ...}
```

## Key Concepts

### ForgeResult

Every operation returns a `ForgeResult` instead of a raw shape:

```python
result = caid.box(10, 20, 30)
result.ok            # True if valid=True AND shape is not None
result.shape         # The CadQuery shape (or None on failure)
result.valid         # Geometry validity flag
result.volume_before # mm³ (for operations that modify geometry)
result.volume_after  # mm³
result.surface_area  # mm²
result.diagnostics   # {"reason": ..., "hint": ...} on failure
result.unwrap()      # Returns shape or raises ValueError
```

### Stateless API

All functions are pure — no hidden state, no Workplane chaining. Pass shapes in, get ForgeResults out.

```python
a = caid.box(10, 10, 10)
b = caid.cylinder(3, 20)
cut = caid.boolean_cut(a, b)  # Accepts ForgeResult or raw shape
```

### Validated Booleans

Boolean operations check volume before and after. If a union doesn't increase volume, you get `valid=False` with a diagnostic hint.

```python
result = caid.boolean_union(a, b)
if not result.ok:
    print(result.diagnostics)  # {"reason": "volume did not increase", "hint": "shapes may not overlap"}
```

### Swappable Backend

CAiD routes all geometry through a `BackendProtocol`. The default is CadQuery, but the protocol is designed so a direct OCCT backend could be swapped in.

```python
backend = caid.get_backend()  # Current backend instance
```

## Available Functions

| Category | Functions |
|----------|-----------|
| **Primitives** | `box`, `cylinder`, `sphere`, `cone`, `torus` |
| **Booleans** | `boolean_union`, `boolean_cut`, `boolean_intersect` |
| **Modify** | `add_hole` |
| **Operations** | `extrude`, `sweep`, `fillet`, `chamfer` |
| **Transforms** | `translate`, `rotate`, `mirror`, `scale` |
| **Healing** | `check_valid`, `heal`, `simplify` |
| **Assembly** | `Assembly`, `Part` |
| **Export** | `to_stl`, `to_step`, `to_brep`, `from_step`, `from_brep` |
| **Preview** | `preview`, `preview_multi` |
| **Compound** | `array_on_curve`, `belt_wire`, `pulley_assembly` |
| **Formatting** | `format_result` |

See [SPEC.md](SPEC.md) for the complete API specification.

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## Acknowledgments

CAiD was co-developed by Adam Steen and [Claude](https://claude.ai) (Anthropic).

## License

MIT — see [LICENSE](LICENSE).
