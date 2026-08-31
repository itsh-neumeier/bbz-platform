"""Inbound alarm ingestion -> normalize -> provider inbox -> dedupe (E16-04).

Mirrors :mod:`bbz_core.infra.telephony_ingest`. An alarm-ingress provider edge
(the ``coda_video`` adapter in-process now, a real HxGN dC3 client later) hands
each inbound alarm here as a plain dict (``IncomingAlarm.model_dump(mode="json")``
from the E16-03 SDK). It is normalized to the immutable ``provider_alarm_event.v1``
shape and deduplicated through the E04-07 provider inbox (ADR-0011): a provider
reconnect that replays its backlog, or both HA nodes observing the same panic
alarm, is stored and processed exactly once (ADR-0006).

Not in scope here (E16-07): resolving the technical-endpoint mapping, creating
the BBZ event, the EPK / popup / camera runtime flow. This stops at the
persisted, deduplicated provider event.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.domain.triggers import (
    AlarmEventRejected,
    alarm_event_dedupe_key,
    normalize_alarm_event,
)
from bbz_core.infra.inbox import IngestResult, ingest

__all__ = ["AlarmEventRejected", "ingest_alarm_event"]


async def ingest_alarm_event(session: AsyncSession, incoming: dict[str, Any]) -> IngestResult:
    """Normalize and dedupe-store one inbound alarm.

    Raises :class:`~bbz_core.domain.triggers.AlarmEventRejected` when the alarm
    does not normalize cleanly (a missing mandatory field, a stray vendor key).
    Returns the :class:`~bbz_core.infra.inbox.IngestResult`; ``DUPLICATE`` means
    the alarm was already ingested (replay / other HA node) and must not be
    acted on again.
    """
    event = normalize_alarm_event(incoming)
    return await ingest(
        session,
        provider=event["provider"],
        normalized=event,
        # the inbox column holds the provider's own stable id or NULL; the
        # normalized event's provider_event_id may be a derived hash (see
        # normalize_alarm_event) and is reflected only in the dedupe_key.
        provider_event_id=incoming.get("provider_event_id"),
        raw_hash=event["raw_hash"],
        dedupe_key=alarm_event_dedupe_key(event),
    )
