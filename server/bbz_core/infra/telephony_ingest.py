"""Normalized telephony event ingestion → provider inbox → dedupe (E11-03).

Every telephony provider edge (``telephony_mock`` in-process, the
``cucm-cti-gateway`` over HTTP in Epic 12) hands normalized events here. The
event is validated against ``telephony_event.v1.json`` (which is
``additionalProperties: false`` — a vendor field is a rejection, not a silent
pass), then deduplicated through the shared provider inbox (ADR-0011) so a
provider reconnect that replays its backlog, or both HA nodes seeing the same
event, processes it exactly once.

The dedupe key for a **call** event is ``(provider, source_call_id, event_type)``
— a replayed ``CALL_ANSWERED`` for the same call is a duplicate. Line / device /
CTI events (no ``source_call_id``) dedupe on the provider's own
``telephony_event_id``.

Hand-off to the call aggregate (E11-04) is a registered hook; until it is set,
ingestion just validates + stores + dedupes.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import lru_cache
from typing import Any

import jsonschema
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.inbox import IngestOutcome, IngestResult, ingest, mark_processed
from bbz_event_schemas import load_schema

_SCHEMA = "telephony_event.v1"

#: event types bound to a specific call — dedupe on call + type
_CALL_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "CALL_OFFERED",
        "CALL_RINGING",
        "CALL_ANSWERED",
        "CALL_CONNECTED",
        "CALL_HELD",
        "CALL_RESUMED",
        "CALL_TRANSFER_INITIATED",
        "CALL_TRANSFERRED",
        "CALL_CONFERENCED",
        "CALL_DISCONNECTED",
        "CALL_FAILED",
    }
)


class TelephonyEventRejected(ValueError):
    """The raw event does not validate against ``telephony_event.v1.json``."""


@lru_cache
def _validator() -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(
        load_schema(_SCHEMA), format_checker=jsonschema.FormatChecker()
    )


def telephony_dedupe_key(event: dict[str, Any]) -> str:
    provider = event["provider"]
    event_type = event["event_type"]
    source_call_id = event.get("source_call_id")
    if source_call_id and event_type in _CALL_EVENT_TYPES:
        return f"telephony:{provider}:call:{source_call_id}:{event_type}"
    return f"telephony:{provider}:evt:{event['telephony_event_id']}"


CallEventDispatch = Callable[[AsyncSession, dict[str, Any]], Awaitable[None]]
_dispatch: CallEventDispatch | None = None


def set_call_event_dispatch(fn: CallEventDispatch | None) -> None:
    """Register (or clear) the call-aggregate hand-off (E11-04 wires this)."""
    global _dispatch
    _dispatch = fn


async def ingest_telephony_event(session: AsyncSession, raw: dict[str, Any]) -> IngestResult:
    """Validate, dedupe and (if new) hand the event to the call aggregate.

    Raises :class:`TelephonyEventRejected` on a schema violation. Returns the
    :class:`IngestResult` — ``DUPLICATE`` means it was already processed.
    """
    errors = sorted(_validator().iter_errors(raw), key=str)
    if errors:
        raise TelephonyEventRejected("; ".join(e.message for e in errors[:5]))

    result = await ingest(
        session,
        provider=raw["provider"],
        normalized=raw,
        provider_event_id=raw["telephony_event_id"],
        dedupe_key=telephony_dedupe_key(raw),
    )
    if result.outcome is IngestOutcome.NEW:
        if _dispatch is not None:
            await _dispatch(session, raw)
        await mark_processed(session, result.inbox_id)
    return result
