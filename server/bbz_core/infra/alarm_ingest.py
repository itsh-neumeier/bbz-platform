"""Inbound alarm ingestion -> normalize -> provider inbox -> dedupe (E16-04)
-> queue a normalized inbound signal for the trigger engine (E16-07).

Mirrors :mod:`bbz_core.infra.telephony_ingest`. An alarm-ingress provider edge
(the ``coda_video`` adapter in-process now, a real HxGN dC3 client later) hands
each inbound alarm here as a plain dict (``IncomingAlarm.model_dump(mode="json")``
from the E16-03 SDK). It is normalized to the immutable ``provider_alarm_event.v1``
shape and deduplicated through the E04-07 provider inbox (ADR-0011): a provider
reconnect that replays its backlog, or both HA nodes observing the same panic
alarm, is stored and processed exactly once (ADR-0006).

A *new* alarm is also mapped to a normalized inbound signal
(``from_incoming_alarm`` — ``PANIC_ALARM_RAISED`` / ``TECHNICAL_ALARM_RAISED``)
and queued as its own ``signal:`` inbox row for the ``trigger-engine`` drain
worker (ADR-0024 / E15-15). A mapping failure there is logged and swallowed — the
alarm is already persisted and must not be undone by a trigger problem. Resolving
the endpoint mapping, creating the event and running the EPK / popup / camera
actions is the rule engine's job (E15-09 / E16-07 rule config).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.domain.triggers import (
    AlarmEventRejected,
    alarm_event_dedupe_key,
    from_incoming_alarm,
    normalize_alarm_event,
)
from bbz_core.infra.inbound_signals import record_inbound_signal
from bbz_core.infra.inbox import IngestOutcome, IngestResult, ingest
from bbz_core.logging import get_logger

_log = get_logger(__name__)

__all__ = ["AlarmEventRejected", "ingest_alarm_event"]


async def ingest_alarm_event(session: AsyncSession, incoming: dict[str, Any]) -> IngestResult:
    """Normalize, dedupe-store, and (if new) queue one inbound alarm.

    Raises :class:`~bbz_core.domain.triggers.AlarmEventRejected` when the alarm
    does not normalize cleanly (a missing mandatory field, a stray vendor key).
    Returns the :class:`~bbz_core.infra.inbox.IngestResult`; ``DUPLICATE`` means
    the alarm was already ingested (replay / other HA node) and no signal is
    re-queued.
    """
    event = normalize_alarm_event(incoming)
    result = await ingest(
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
    if result.outcome is IngestOutcome.NEW:
        await _queue_signal(session, event, provider_event_id=incoming.get("provider_event_id"))
    return result


async def _queue_signal(
    session: AsyncSession, event: dict[str, Any], *, provider_event_id: str | None
) -> None:
    """Queue the normalized inbound signal for the trigger-engine drain worker
    (ADR-0024). Best-effort: a mapping failure is logged, not raised.
    """
    try:
        signal = from_incoming_alarm(event)
    except Exception:
        _log.warning("alarm_signal_map_failed", provider_event_id=event.get("provider_event_id"))
        return
    await record_inbound_signal(
        session,
        signal=signal,
        provider_event_id=provider_event_id,
        dedupe_key=f"signal:{alarm_event_dedupe_key(event)}",
    )
