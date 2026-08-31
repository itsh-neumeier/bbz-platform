"""Vendor-neutral inbound technical-alarm provider protocol (E16-03).

Sources: a ``coda_video`` panic / duress / intrusion / technical alarm, a future
alarm dialer. Every received alarm is normalised into an immutable provider
event **before** trigger evaluation (E16-04) so active/active nodes achieve
exactly-once event creation — a duplicated panic / BMA alarm must never create
two BBZ events (ADR-0004 / ADR-0006).

**Separation of concerns:** :meth:`acknowledge_external` tells the *vendor*
system an operator saw the alarm. It is a different domain action from accepting
or acknowledging the BBZ event; the two never call each other. It is present
only when the manifest declares ``alarm.acknowledge_external``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from bbz_integration_sdk.providers.alarm_types import (
    AlarmContext,
    AlarmSource,
    ExternalAckResult,
    IncomingAlarm,
)
from bbz_integration_sdk.providers.base import Provider

#: methods every alarm-ingress provider implements (acknowledge_external is opt-in)
ALARM_INGRESS_METHODS: tuple[str, ...] = (
    "subscribe_alarms",
    "resolve_source",
    "get_context",
    "get_associated_cameras",
)


@runtime_checkable
class AlarmIngressProvider(Provider, Protocol):
    def subscribe_alarms(self) -> AsyncIterator[IncomingAlarm]:
        """Yield each inbound alarm as it arrives (pre-normalisation, E16-04)."""
        ...

    async def resolve_source(self, *, external_source_id: str) -> AlarmSource | None:
        """The configured source behind an external id, or ``None`` if unknown."""
        ...

    async def get_context(self, *, provider_event_id: str) -> AlarmContext:
        """Provider-side context for an already-received alarm (source, cameras)."""
        ...

    async def get_associated_cameras(self, *, provider_event_id: str) -> list[str]:
        """Normalized camera ids the provider links to this alarm."""
        ...


@runtime_checkable
class ExternalAckCapable(Protocol):
    """Opt-in: implemented only when ``alarm.acknowledge_external`` is declared."""

    async def acknowledge_external(
        self, *, provider_event_id: str, actor_ref: str, command_id: str
    ) -> ExternalAckResult:
        """Tell the vendor system an operator saw this alarm. **Not** the BBZ
        event ack. Raises ``ExternalAckNotSupportedError`` if unavailable."""
        ...
