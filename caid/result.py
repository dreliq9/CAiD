from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ForgeResult:
    shape: Any | None
    valid: bool
    volume_before: float | None = None
    volume_after: float | None = None
    surface_area: float | None = None
    diagnostics: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.valid and self.shape is not None

    def unwrap(self) -> Any:
        """Return shape or raise ValueError with diagnostics."""
        if not self.ok:
            raise ValueError(f"ForgeResult failed: {self.diagnostics}")
        return self.shape

    def __str__(self) -> str:
        tag = "OK" if self.ok else ("WARN" if self.shape is not None else "FAIL")
        parts = [tag]
        if self.volume_before is not None and self.volume_after is not None:
            parts.append(f"vol {self.volume_before:.1f} -> {self.volume_after:.1f} mm³")
        elif self.volume_after is not None:
            parts.append(f"vol={self.volume_after:.1f} mm³")
        if self.surface_area is not None:
            parts.append(f"area={self.surface_area:.1f} mm²")
        hint = self.diagnostics.get("hint") or self.diagnostics.get("reason")
        if hint and not self.ok:
            parts.append(f"({hint})")
        return " | ".join(parts)


def format_result(fr: ForgeResult, prefix: str = "") -> str:
    """Format a ForgeResult as a human-readable status line.

    Args:
        fr: The ForgeResult to format.
        prefix: Optional text to prepend (e.g. "Filleted 'box'").
    """
    tag = "OK" if fr.ok else ("WARN" if fr.shape is not None else "FAIL")
    msg = f"{tag} {prefix}".strip() if prefix else tag
    if fr.volume_after is not None:
        msg += f" | vol={fr.volume_after:.1f} mm³"
    if fr.surface_area is not None:
        msg += f" | area={fr.surface_area:.1f} mm²"
    hint = fr.diagnostics.get("hint") or fr.diagnostics.get("reason")
    if hint and not fr.ok:
        msg += f" (hint: {hint})"
    return msg
