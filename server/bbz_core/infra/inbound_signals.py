"""Persist a normalized inbound signal through the provider inbox (E15-04).

The pure shape + telephony mapper live in
:mod:`bbz_core.domain.triggers.signals`; this is the thin infra hook that
validates a signal and hands it to the E04-07 provider inbox for dedupe **before**
any trigger-rule evaluation (E15-09). A provider reconnect that replays events,
or both HA nodes seeing the same event, is deduplicated here.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.domain.triggers.signals import validate_inbound_signal
from bbz_core.infra.inbox import IngestResult, ingest


async def record_inbound_signal(
    session: AsyncSession,
    *,
    signal: dict[str, Any],
    provider_event_id: str | None = None,
    dedupe_key: str | None = None,
) -> IngestResult:
    """Validate ``signal`` against ``inbound_signal.v1`` then dedupe-store it.

    Raises :class:`~bbz_core.domain.triggers.signals.InboundSignalRejected` on a
    schema violation (a vendor field, a missing required key). The stored
    ``normalized`` payload is the signal itself — no raw provider payload.
    """
    validate_inbound_signal(signal)
    return await ingest(
        session,
        provider=signal["provider"],
        normalized=signal,
        provider_event_id=provider_event_id,
        dedupe_key=dedupe_key,
    )
