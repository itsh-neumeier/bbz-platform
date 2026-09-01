"""The fixed monitor / KVM routing catalog (roadmap E19-02, MASTER_PROMPT §9).

This is the operational hardware layout, not configuration: seven logical
**inputs** and seven **outputs** (six workplace monitors in a 3x2 grid plus the
large display). Pure data — the migration ``0042_monitor_catalog_seed`` inserts
these rows, and the routing service validates against them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MonitorInputSpec:
    key: str
    label: str
    sort_order: int


@dataclass(frozen=True, slots=True)
class MonitorOutputSpec:
    key: str
    label: str
    #: 0 = top row, 1 = bottom row; ``None`` for the large display
    grid_row: int | None
    #: 0 = left .. 2 = right; ``None`` for the large display
    grid_col: int | None
    is_large_display: bool
    sort_order: int


#: 3 columns x 2 rows for the workplace monitors (MASTER_PROMPT §9)
GRID_COLS = 3
GRID_ROWS = 2

INPUTS: tuple[MonitorInputSpec, ...] = (
    MonitorInputSpec("bbz-os", "BBZ-OS", 0),
    MonitorInputSpec("bku1", "BKU 1", 1),
    MonitorInputSpec("bku2", "BKU 2", 2),
    MonitorInputSpec("bku3", "BKU 3", 3),
    MonitorInputSpec("bku4", "BKU 4", 4),
    # MASTER_PROMPT §9 writes "Cayuga 1/2"; the canonical name is Coda Video
    # (HxGN dC3, ``coda_video``, ex-"Cayuga" — see docs/domain/glossary.md).
    MonitorInputSpec("coda1", "Coda 1", 5),
    MonitorInputSpec("coda2", "Coda 2", 6),
)

OUTPUTS: tuple[MonitorOutputSpec, ...] = (
    MonitorOutputSpec("workplace1", "Arbeitsplatzmonitor 1", 0, 0, False, 0),
    MonitorOutputSpec("workplace2", "Arbeitsplatzmonitor 2", 0, 1, False, 1),
    MonitorOutputSpec("workplace3", "Arbeitsplatzmonitor 3", 0, 2, False, 2),
    MonitorOutputSpec("workplace4", "Arbeitsplatzmonitor 4", 1, 0, False, 3),
    MonitorOutputSpec("workplace5", "Arbeitsplatzmonitor 5", 1, 1, False, 4),
    MonitorOutputSpec("workplace6", "Arbeitsplatzmonitor 6", 1, 2, False, 5),
    MonitorOutputSpec("large-display", "Mittelmonitor / Großbild", None, None, True, 6),
)

INPUT_KEYS: frozenset[str] = frozenset(i.key for i in INPUTS)
OUTPUT_KEYS: frozenset[str] = frozenset(o.key for o in OUTPUTS)

_OUTPUT_BY_SLOT = {(o.grid_row, o.grid_col): o for o in OUTPUTS if not o.is_large_display}

#: the output at the lower-left grid slot — MASTER_PROMPT §9 pins BBZ-OS here
#: (the invariant is enforced by the routing service, E19-03)
BOTTOM_LEFT_OUTPUT_KEY: str = _OUTPUT_BY_SLOT[(GRID_ROWS - 1, 0)].key

#: The documented default routing (output key -> input key). A defensible
#: starting point for a shift; users/workplaces override it with saved profiles
#: (E19-05) and the operator can always reset to it (E19-04).
STANDARD_LAYOUT: dict[str, str] = {
    "workplace1": "bku1",
    "workplace2": "bku2",
    "workplace3": "bku3",
    BOTTOM_LEFT_OUTPUT_KEY: "bbz-os",  # §9 fixed rule
    "workplace5": "bku4",
    "workplace6": "coda1",
    "large-display": "coda2",
}
