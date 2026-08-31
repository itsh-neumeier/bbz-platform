"""Alarm normalization: inbound technical/panic alarm -> immutable provider event.

Pure (no I/O, no integration SDK). An alarm-ingress provider edge hands its
alarm here as a plain dict (the ``IncomingAlarm`` model from the E16-03 SDK,
dumped by the infra caller); this turns it into the immutable, vendor-neutral
``provider_alarm_event.v1`` shape and derives a deterministic id when the
provider has no stable one.

The raw vendor payload is hashed here and then dropped -- only ``raw_hash``
survives into the normalized event (ADR-0004 / ADR-0006: a raw provider payload
never reaches business rules). Persisting + deduplicating the event through the
E04-07 provider inbox is :mod:`bbz_core.infra.alarm_ingest`; wiring it onto the
trigger engine is E16-07.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from typing import Any

import jsonschema

from bbz_event_schemas import provider_alarm_event_schema

#: derived-id marker for an alarm the provider gave no stable event id for
DERIVED_ID_PREFIX = "derived:"

#: optional fields copied verbatim (when present) from the incoming alarm dict
_COPY_OPTIONAL = (
    "provider_alarm_id",
    "alarm_subtype",
    "source_name",
    "site_external_id",
    "occurred_at",
    "severity_external",
    "state_external",
)


class AlarmEventRejected(ValueError):
    """The normalized alarm event does not validate against ``provider_alarm_event.v1``."""


@lru_cache
def _validator() -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(
        provider_alarm_event_schema(), format_checker=jsonschema.FormatChecker()
    )


def _canonical_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _derived_event_id(event: dict[str, Any]) -> str:
    """A deterministic id from documented stable fields when the provider has none.

    Built from source + type + subtype + occurred_at. When ``occurred_at`` is also
    absent the id degrades to source+type+subtype: a provider that supplies
    neither a stable id nor an occurrence time cannot be perfectly deduplicated
    and SHOULD supply at least one (INTEGRATIONS_CODA_VIDEO.md, HA and
    exactly-once behavior).
    """
    parts = [
        event.get("source_external_id", ""),
        event.get("alarm_type", ""),
        event.get("alarm_subtype") or "",
        event.get("occurred_at") or "",
    ]
    return DERIVED_ID_PREFIX + hashlib.sha256("|".join(parts).encode()).hexdigest()


def normalize_alarm_event(incoming: dict[str, Any]) -> dict[str, Any]:
    """Map an inbound alarm dict to the immutable ``provider_alarm_event.v1`` shape.

    Only allowlisted fields are copied -- a vendor field in ``incoming`` is
    dropped, never carried forward. ``raw_hash`` is computed from
    ``incoming['raw']`` and the payload itself is discarded. ``provider_event_id``
    is the provider's own id, or a ``derived:`` hash of stable fields when it has
    none. Raises :class:`AlarmEventRejected` on any schema violation (a missing
    mandatory field, a stray key, a malformed timestamp).
    """
    event: dict[str, Any] = {
        "provider": str(incoming.get("provider") or "").strip(),
        "provider_instance_id": str(incoming.get("provider_instance_id") or "").strip(),
        "alarm_type": str(incoming.get("alarm_type") or "").strip(),
        "source_external_id": str(incoming.get("source_external_id") or "").strip(),
        "received_at": incoming.get("received_at"),
        "raw_hash": _canonical_hash(incoming.get("raw", {})),
        "associated_camera_ids": sorted(set(incoming.get("associated_camera_ids") or [])),
    }
    for key in _COPY_OPTIONAL:
        if incoming.get(key) is not None:
            event[key] = incoming[key]
    # severity_external stays the provider's own raw string, unmapped -- the BBZ
    # priority is decided by admin config (E16-06), never by this value.

    stable_id = incoming.get("provider_event_id")
    event["provider_event_id"] = str(stable_id) if stable_id else _derived_event_id(event)

    errors = sorted(_validator().iter_errors(event), key=str)
    if errors:
        raise AlarmEventRejected("; ".join(e.message for e in errors[:5]))
    return event


def alarm_event_dedupe_key(event: dict[str, Any]) -> str:
    """Provider-inbox dedupe key for a normalized alarm event.

    ``{provider}:{provider_event_id}`` -- ``provider_event_id`` is already either
    the provider's stable id or the ``derived:`` fallback, so this is always
    deterministic and a replayed alarm collides on the inbox's UNIQUE key.
    """
    return f"{event['provider']}:{event['provider_event_id']}"
