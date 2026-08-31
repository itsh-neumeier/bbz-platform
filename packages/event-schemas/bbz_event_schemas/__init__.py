"""Versioned JSON Schemas for BBZ events.

Single source of truth for the *shape* of:
* the domain/audit event envelope (MASTER_PROMPT §3)
* the normalized telephony event model (MASTER_PROMPT §8.4)

Backend and (later) frontend/agent code validate against these. Every schema
carries a ``schema_version``. Changes are additive within a major version.
"""

from bbz_event_schemas.loader import (
    UnknownEventTypeError,
    event_payload_schema,
    inbound_signal_schema,
    known_event_types,
    list_schemas,
    load_schema,
)

__all__ = [
    "UnknownEventTypeError",
    "event_payload_schema",
    "inbound_signal_schema",
    "known_event_types",
    "list_schemas",
    "load_schema",
]
__version__ = "0.0.0"
