from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from typing import Any

import jsonschema


class UnknownEventTypeError(KeyError):
    """No payload schema is registered for this ``event_type`` (ADR-0011)."""


def list_schemas() -> list[str]:
    root = files("bbz_event_schemas.schemas")
    return sorted(p.name for p in root.iterdir() if p.name.endswith(".json"))


def load_schema(name: str) -> dict[str, Any]:
    if not name.endswith(".json"):
        name = f"{name}.json"
    text = (files("bbz_event_schemas.schemas") / name).read_text("utf-8")
    schema: dict[str, Any] = json.loads(text)
    # Fail fast if a shipped schema is itself invalid.
    jsonschema.Draft202012Validator.check_schema(schema)
    return schema


@lru_cache
def _payloads(schema_version: int) -> dict[str, Any]:
    doc = load_schema(f"event.payloads.v{schema_version}")
    props: dict[str, Any] = doc.get("properties", {})
    # resolve local $ref/$defs once by keeping the whole doc as the base
    for sub in props.values():
        sub.setdefault("$defs", doc.get("$defs", {}))
    return props


def known_event_types(schema_version: int = 1) -> frozenset[str]:
    return frozenset(_payloads(schema_version))


def inbound_signal_schema(schema_version: int = 1) -> dict[str, Any]:
    """The JSON Schema for the normalized inbound signal (E15-04)."""
    return load_schema(f"inbound_signal.v{schema_version}")


def event_payload_schema(event_type: str, schema_version: int = 1) -> dict[str, Any]:
    """The JSON Schema for one ``event_type`` payload at ``schema_version``.

    Raises :class:`UnknownEventTypeError` for a type that has no registered
    schema — the ``append_event`` path turns that into a reject (ADR-0011).
    """
    try:
        schema: dict[str, Any] = _payloads(schema_version)[event_type]
    except KeyError as exc:
        raise UnknownEventTypeError(
            f"no payload schema for event_type={event_type!r} (v{schema_version})"
        ) from exc
    return schema
