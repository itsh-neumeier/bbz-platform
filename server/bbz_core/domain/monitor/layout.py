"""Monitor routing validation + the standard layout (roadmap E19-02 / E19-03).

Pure functions over the catalog. An invalid input->output assignment raises
:class:`MonitorDomainError` (or the more specific :class:`FixedRouteViolation`)
and changes nothing. Routing *execution* at the provider is E19-04.

**Fixed rule (MASTER_PROMPT §9, E19-03):** the lower-left output is permanently
bound to ``BBZ-OS``. It is enforced here, in the domain, so every write path — the
routing API, a reset to standard, an applied profile — is subject to it; there is
no UI-only bypass.
"""

from __future__ import annotations

from bbz_core.domain.monitor.catalog import (
    BOTTOM_LEFT_OUTPUT_KEY,
    INPUT_KEYS,
    OUTPUT_KEYS,
    STANDARD_LAYOUT,
)

#: MASTER_PROMPT §9: outputs whose input may never be changed by an operator.
FIXED_ASSIGNMENTS: dict[str, str] = {BOTTOM_LEFT_OUTPUT_KEY: "bbz-os"}


class MonitorDomainError(Exception):
    """An input->output assignment or a layout is not valid."""


class FixedRouteViolation(MonitorDomainError):
    """An attempt to route a permanently-bound output away from its fixed input
    (MASTER_PROMPT §9 — the lower-left monitor is always BBZ-OS)."""


def is_fixed_output(output_key: str) -> bool:
    """Whether ``output_key``'s input is locked (the UI renders it read-only)."""
    return output_key in FIXED_ASSIGNMENTS


def fixed_input_for(output_key: str) -> str | None:
    """The input ``output_key`` is locked to, or ``None`` if it is freely routable."""
    return FIXED_ASSIGNMENTS.get(output_key)


def validate_assignment(output_key: str, input_key: str) -> None:
    """Raise unless ``input_key`` may feed ``output_key``: both keys must be in
    the catalog, and a fixed output only accepts its bound input."""
    if output_key not in OUTPUT_KEYS:
        raise MonitorDomainError(f"unknown output {output_key!r}")
    if input_key not in INPUT_KEYS:
        raise MonitorDomainError(f"unknown input {input_key!r}")
    fixed = FIXED_ASSIGNMENTS.get(output_key)
    if fixed is not None and input_key != fixed:
        raise FixedRouteViolation(
            f"output {output_key!r} is permanently routed to {fixed!r} "
            f"(MASTER_PROMPT §9) and cannot be changed"
        )


def validate_layout(mapping: dict[str, str]) -> None:
    """Raise unless ``mapping`` assigns exactly one known input to every known
    output (and honours the fixed-route rule)."""
    keys = set(mapping)
    if missing := OUTPUT_KEYS - keys:
        raise MonitorDomainError(f"layout is missing outputs: {sorted(missing)}")
    if extra := keys - OUTPUT_KEYS:
        raise MonitorDomainError(f"layout has unknown outputs: {sorted(extra)}")
    for output_key, input_key in mapping.items():
        validate_assignment(output_key, input_key)


def standard_layout() -> dict[str, str]:
    """A fresh copy of the documented default routing (honours the fixed rule)."""
    return dict(STANDARD_LAYOUT)
