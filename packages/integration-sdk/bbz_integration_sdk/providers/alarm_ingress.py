from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from bbz_integration_sdk.providers.base import Provider


@runtime_checkable
class AlarmIngressProvider(Provider, Protocol):
    """Inbound technical-alarm source (ADR-0004 / ADR-0006).

    Every received alarm is normalized into an immutable provider event BEFORE
    trigger evaluation. The provider must expose a stable ``provider_event_id``
    (or a deterministic dedupe key from documented stable fields) so active/active
    nodes achieve exactly-once event creation — a duplicated panic/BMA alarm must
    never create two BBZ events.
    """

    def subscribe_alarms(self) -> AsyncIterator[Any]: ...

    async def resolve_source(self, *, external_source_id: str) -> Any: ...

    async def get_context(self, *, provider_event_id: str) -> Any: ...

    async def get_associated_cameras(self, *, provider_event_id: str) -> list[Any]: ...
