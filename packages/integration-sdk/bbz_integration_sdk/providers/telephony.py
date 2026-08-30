from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from bbz_integration_sdk.providers.base import Provider
from bbz_integration_sdk.providers.telephony_types import (
    CallerResolution,
    CallEvent,
    CallSnapshot,
    CommandAccepted,
    LineInfo,
    ReconcileResult,
)

__all__ = ["TELEPHONY_METHODS", "TelephonyProvider"]

#: Every §8.12 method a telephony provider must expose (beyond the ``Provider``
#: lifecycle). Used by the conformance test.
TELEPHONY_METHODS: frozenset[str] = frozenset(
    {
        "list_lines",
        "get_line_state",
        "get_active_calls",
        "subscribe_call_events",
        "dial",
        "answer",
        "hangup",
        "hold",
        "resume",
        "transfer",
        "conference",
        "send_dtmf",
        "resolve_caller",
        "reconcile",
    }
)


@runtime_checkable
class TelephonyProvider(Provider, Protocol):
    """Vendor-neutral telephony provider interface (MASTER_PROMPT §8.12).

    Implemented by ``telephony_mock`` (E11-05); ``telephony_sip`` (Epic 13) and
    ``telephony_cucm`` (Epic 12) later. ``telephony_cucm`` talks to the separate
    ``cucm-cti-gateway`` service and never imports Cisco JTAPI classes into
    Python (ADR-0002).

    Lifecycle (``initialize`` / ``health`` / ``info`` / ``capabilities`` /
    ``shutdown``) is inherited from :class:`Provider`. The control commands
    (``dial`` … ``send_dtmf``) return a :class:`CommandAccepted` acknowledgement;
    the actual state change is delivered asynchronously through
    :meth:`subscribe_call_events`. Providers must treat a repeated ``command_id``
    as the same command (idempotent).
    """

    async def list_lines(self) -> list[LineInfo]: ...

    async def get_line_state(self, line_id: str) -> LineInfo: ...

    async def get_active_calls(self) -> list[CallSnapshot]: ...

    def subscribe_call_events(self) -> AsyncIterator[CallEvent]: ...

    async def dial(self, *, line_id: str, destination: str, command_id: str) -> CommandAccepted: ...

    async def answer(self, *, call_id: str, command_id: str) -> CommandAccepted: ...

    async def hangup(self, *, call_id: str, command_id: str) -> CommandAccepted: ...

    async def hold(self, *, call_id: str, command_id: str) -> CommandAccepted: ...

    async def resume(self, *, call_id: str, command_id: str) -> CommandAccepted: ...

    async def transfer(
        self, *, call_id: str, destination: str, command_id: str
    ) -> CommandAccepted: ...

    async def conference(self, *, call_ids: list[str], command_id: str) -> CommandAccepted: ...

    async def send_dtmf(
        self, *, call_id: str, dtmf_profile_id: str, command_id: str
    ) -> CommandAccepted:
        """Send a **configured** DTMF profile. The raw code is a secret held by
        the integration/config store and must never be logged or echoed
        (SECURITY.md, ADR-0004)."""

    async def resolve_caller(self, *, number: str) -> CallerResolution: ...

    async def reconcile(self) -> ReconcileResult:
        """Re-sync provider/call state after a failover or CONTROL_LEADER change
        (E11-14). Must be safe to call repeatedly."""
