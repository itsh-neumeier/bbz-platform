from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from bbz_integration_sdk.providers.base import Provider


@runtime_checkable
class TelephonyProvider(Provider, Protocol):
    """Vendor-neutral telephony provider interface (MASTER_PROMPT §8.12).

    Implemented by ``telephony_mock`` now; ``telephony_sip`` and
    ``telephony_cucm`` in Phase 5. The ``telephony_cucm`` adapter talks to the
    separate ``cucm-cti-gateway`` service and never imports Cisco JTAPI classes
    into the Python side (ADR-0002).

    Payload types are intentionally ``Any`` in the foundation phase and become
    concrete normalized models in Phase 5.
    """

    async def list_lines(self) -> list[Any]: ...

    async def get_line_state(self, line_id: str) -> Any: ...

    async def get_active_calls(self) -> list[Any]: ...

    def subscribe_call_events(self) -> AsyncIterator[Any]: ...

    async def dial(self, *, line_id: str, destination: str, command_id: str) -> Any: ...

    async def answer(self, *, call_id: str, command_id: str) -> Any: ...

    async def hangup(self, *, call_id: str, command_id: str) -> Any: ...

    async def hold(self, *, call_id: str, command_id: str) -> Any: ...

    async def resume(self, *, call_id: str, command_id: str) -> Any: ...

    async def transfer(self, *, call_id: str, destination: str, command_id: str) -> Any: ...

    async def conference(self, *, call_ids: list[str], command_id: str) -> Any: ...

    async def send_dtmf(self, *, call_id: str, dtmf_profile_id: str, command_id: str) -> Any:
        """Send a configured DTMF profile. The raw code is a secret held by the
        integration/config store and must never be logged (SECURITY.md, ADR-0004)."""

    async def resolve_caller(self, *, number: str) -> Any: ...

    async def reconcile(self) -> Any:
        """Re-sync provider/call state after a failover or CONTROL_LEADER change."""
