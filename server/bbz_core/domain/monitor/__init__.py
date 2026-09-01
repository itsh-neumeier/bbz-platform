"""Monitor / KVM routing domain (roadmap E19, MASTER_PROMPT §9): the fixed
input/output catalog, the standard layout, and pure assignment validation."""

from __future__ import annotations

from bbz_core.domain.monitor.catalog import (
    BOTTOM_LEFT_OUTPUT_KEY,
    GRID_COLS,
    GRID_ROWS,
    INPUT_KEYS,
    INPUTS,
    OUTPUT_KEYS,
    OUTPUTS,
    STANDARD_LAYOUT,
    MonitorInputSpec,
    MonitorOutputSpec,
)
from bbz_core.domain.monitor.layout import (
    MonitorDomainError,
    standard_layout,
    validate_assignment,
    validate_layout,
)

__all__ = [
    "BOTTOM_LEFT_OUTPUT_KEY",
    "GRID_COLS",
    "GRID_ROWS",
    "INPUTS",
    "INPUT_KEYS",
    "OUTPUTS",
    "OUTPUT_KEYS",
    "STANDARD_LAYOUT",
    "MonitorDomainError",
    "MonitorInputSpec",
    "MonitorOutputSpec",
    "standard_layout",
    "validate_assignment",
    "validate_layout",
]
