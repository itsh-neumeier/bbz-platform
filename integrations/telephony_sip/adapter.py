"""``telephony_sip`` adapter — scaffold (roadmap E13-01).

A protocol-conformant :class:`~bbz_integration_sdk.providers.TelephonyProvider`
that carries **no SIP stack yet**. Lifecycle + read queries answer with safe
empty/unknown values so the core can register and health-check the provider;
every *control* command raises :class:`SipNotConfiguredError` until the concrete
gateway binding lands (E13-03+).

Never depends on ``integrations.telephony_cucm`` or Cisco JTAPI (ADR-0002 §8.17).
The raw DTMF code is always a secret — only the profile id is ever handled here
(ADR-0004).
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import AsyncIterator
from typing import Any

from bbz_integration_sdk.capabilities import Capability, CapabilitySet
from bbz_integration_sdk.diagnostics import DiagnosticsReport, HealthState
from bbz_integration_sdk.providers.base import ProviderInfo
from bbz_integration_sdk.providers.telephony_types import (
    CallerResolution,
    CallEvent,
    CallSnapshot,
    LineInfo,
    LineState,
    ReconcileResult,
)

_CAPABILITIES = (
    Capability.CALL_ANSWER,
    Capability.CALL_DIAL,
    Capability.CALL_HANGUP,
    Capability.CALL_HOLD,
    Capability.CALL_RESUME,
    Capability.CALL_TRANSFER,
    Capability.CALL_SEND_DTMF,
    Capability.CALL_MONITORING,
)


class SipNotConfiguredError(RuntimeError):
    """A control command was issued before the SIP gateway binding exists (E13-03+)."""


class SipTelephonyProvider:
    def __init__(self, *, instance_id: str = "sip", lines: list[str] | None = None) -> None:
        self._instance_id = instance_id
        self._lines = {lid: LineInfo(line_id=lid, state=LineState.UNKNOWN) for lid in (lines or [])}
        self._initialized = False

    # --- lifecycle ------------------------------------------------------

    async def initialize(self) -> None:
        self._initialized = True

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            integration_id="telephony_sip",
            provider="sip",
            instance_id=self._instance_id,
            mock=False,
        )

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet(_CAPABILITIES)

    async def health(self) -> DiagnosticsReport:
        return DiagnosticsReport(
            integration_id="telephony_sip",
            state=HealthState.UNKNOWN,
            summary="SIP stack not implemented yet (Epic 13); scaffold only",
            checked_at=_dt.datetime.now(_dt.UTC),
            details={"initialized": self._initialized, "lines": len(self._lines)},
        )

    async def shutdown(self) -> None:
        self._initialized = False

    # --- read queries (safe defaults) --------------------------------

    async def list_lines(self) -> list[LineInfo]:
        return list(self._lines.values())

    async def get_line_state(self, line_id: str) -> LineInfo:
        return self._lines.get(line_id, LineInfo(line_id=line_id, state=LineState.UNKNOWN))

    async def get_active_calls(self) -> list[CallSnapshot]:
        return []

    async def subscribe_call_events(self) -> AsyncIterator[CallEvent]:
        # no gateway yet — an empty stream. E13-03+ implements the real one.
        for event in ():
            yield event

    async def resolve_caller(self, *, number: str) -> CallerResolution:
        return CallerResolution(number=number, matched=False)

    async def reconcile(self) -> ReconcileResult:
        return ReconcileResult(
            lines=list(self._lines.values()),
            active_calls=[],
            note="telephony_sip scaffold — nothing to reconcile",
        )

    # --- control commands (not wired yet) ---------------------------

    async def dial(self, *, line_id: str, destination: str, command_id: str) -> Any:
        raise SipNotConfiguredError("dial")

    async def answer(self, *, call_id: str, command_id: str) -> Any:
        raise SipNotConfiguredError("answer")

    async def hangup(self, *, call_id: str, command_id: str) -> Any:
        raise SipNotConfiguredError("hangup")

    async def hold(self, *, call_id: str, command_id: str) -> Any:
        raise SipNotConfiguredError("hold")

    async def resume(self, *, call_id: str, command_id: str) -> Any:
        raise SipNotConfiguredError("resume")

    async def transfer(self, *, call_id: str, destination: str, command_id: str) -> Any:
        raise SipNotConfiguredError("transfer")

    async def conference(self, *, call_ids: list[str], command_id: str) -> Any:
        raise SipNotConfiguredError("conference")

    async def send_dtmf(self, *, call_id: str, dtmf: str, command_id: str) -> Any:
        # `dtmf` is the resolved secret sequence (ADR-0025) — a real adapter emits
        # it via SIP INFO / RFC 2833 and must never log or echo it (ADR-0004)
        raise SipNotConfiguredError("send_dtmf")


def build(config: dict[str, Any] | None = None) -> SipTelephonyProvider:
    """Entry point for the integration host's dynamic loader (E11-06)."""
    cfg = config or {}
    return SipTelephonyProvider(lines=list(cfg.get("lines", [])))
