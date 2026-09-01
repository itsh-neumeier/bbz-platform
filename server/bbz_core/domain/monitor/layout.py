"""Monitor routing validation + the standard layout (roadmap E19-02).

Pure functions over the E19-02 catalog. An invalid input->output assignment
raises :class:`MonitorDomainError` and changes nothing. Routing *execution* (at
the provider) is E19-04; the "lower-left output is always BBZ-OS" invariant is
E19-03 (a hook is left in :func:`validate_assignment`).
"""

from __future__ import annotations

from bbz_core.domain.monitor.catalog import INPUT_KEYS, OUTPUT_KEYS, STANDARD_LAYOUT


class MonitorDomainError(Exception):
    """An input->output assignment or a layout is not valid."""


def validate_assignment(output_key: str, input_key: str) -> None:
    """Raise :class:`MonitorDomainError` unless ``input_key`` may feed
    ``output_key``. Currently: both keys must be in the catalog. The
    lower-left == BBZ-OS invariant is layered on in E19-03."""
    if output_key not in OUTPUT_KEYS:
        raise MonitorDomainError(f"unknown output {output_key!r}")
    if input_key not in INPUT_KEYS:
        raise MonitorDomainError(f"unknown input {input_key!r}")


def validate_layout(mapping: dict[str, str]) -> None:
    """Raise :class:`MonitorDomainError` unless ``mapping`` assigns exactly one
    known input to every known output."""
    keys = set(mapping)
    if missing := OUTPUT_KEYS - keys:
        raise MonitorDomainError(f"layout is missing outputs: {sorted(missing)}")
    if extra := keys - OUTPUT_KEYS:
        raise MonitorDomainError(f"layout has unknown outputs: {sorted(extra)}")
    for output_key, input_key in mapping.items():
        validate_assignment(output_key, input_key)


def standard_layout() -> dict[str, str]:
    """A fresh copy of the documented default routing."""
    return dict(STANDARD_LAYOUT)
