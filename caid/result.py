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
