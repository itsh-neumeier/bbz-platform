"""Full in-memory telephony provider mock (roadmap E11-05).

Implements the whole ``TelephonyProvider`` protocol with the typed SDK payload
models and a deterministic, driveable event stream. Test / demo code triggers
scenarios (incoming call, provider OOS→IS, reconnect replay) through the
``simulate_*`` helpers; ``subscribe_call_events()`` yields everything that
happened.

Never logs or echoes an actual DTMF code — only the profile id (ADR-0004).
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import itertools
from collections.abc import AsyncIterator
from typing import Any

from bbz_integration_sdk.capabilities import Capability, CapabilitySet
from bbz_integration_sdk.diagnostics import DiagnosticsReport, HealthState
from bbz_integration_sdk.normalized_events import NormalizedTelephonyEvent
from bbz_integration_sdk.providers.base import ProviderInfo
from bbz_integration_sdk.providers.telephony_types import (
    CallDirection,
    CallerResolution,
    CallEvent,
    CallLifecycleState,
    CallSnapshot,
    CommandAccepted,
    LineInfo,
    LineState,
    PartyRef,
    ReconcileResult,
)

_ID = itertools.count(1)


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


class _Call:
    __slots__ = ("call_id", "called", "calling", "direction", "line_id", "started_at", "state")

    def __init__(
        self,
        call_id: str,
        direction: CallDirection,
        line_id: str | None,
        calling: PartyRef | None,
        called: PartyRef | None,
    ) -> None:
        self.call_id = call_id
        self.direction = direction
        self.state = CallLifecycleState.OFFERED
        self.line_id = line_id
        self.calling = calling
        self.called = called
        self.started_at: _dt.datetime | None = None

    def snapshot(self) -> CallSnapshot:
        return CallSnapshot(
            call_id=self.call_id,
            direction=self.direction,
            state=self.state,
            line_id=self.line_id,
            calling=self.calling,
            called=self.called,
            started_at=self.started_at,
        )


class MockTelephonyProvider:
    _CAPS = (
        Capability.CALL_ANSWER,
        Capability.CALL_DIAL,
        Capability.CALL_HANGUP,
        Capability.CALL_HOLD,
        Capability.CALL_RESUME,
        Capability.CALL_TRANSFER,
        Capability.CALL_CONFERENCE,
        Capability.CALL_SEND_DTMF,
        Capability.CALL_MONITORING,
        Capability.DEVICE_MONITORING,
        Capability.DIRECTORY_LOOKUP,
    )

    def __init__(
        self,
        *,
        lines: list[str] | None = None,
        instance_id: str = "mock",
        auto_answer: bool = False,
        directory: dict[str, str] | None = None,
    ) -> None:
        self._lines = {
            lid: LineInfo(line_id=lid, label=f"Platz {lid}", state=LineState.IN_SERVICE)
            for lid in (lines or ["1001", "1002"])
        }
        self._instance_id = instance_id
        self._auto_answer = auto_answer
        self._directory = dict(directory or {"+49911500": "EVU Nord", "110": "Polizei"})
        self._calls: dict[str, _Call] = {}
        self._events: asyncio.Queue[CallEvent] = asyncio.Queue()
        self._backlog: list[CallEvent] = []
        self._seen: dict[str, CommandAccepted] = {}
        #: command ids of DTMF sequences actually emitted (a repeated command_id
        #: is deduped and not re-counted) — test observability, never the code
        self._dtmf_sends: list[str] = []
        self._in_service = True
        self._initialized = False

    # --- lifecycle --------------------------------------------------------
    async def initialize(self) -> None:
        self._initialized = True

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            integration_id="telephony_mock",
            provider="mock",
            instance_id=self._instance_id,
            mock=True,
        )

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet(self._CAPS)

    async def health(self) -> DiagnosticsReport:
        return DiagnosticsReport(
            integration_id="telephony_mock",
            state=(
                HealthState.HEALTHY
                if self._initialized and self._in_service
                else HealthState.DEGRADED
                if self._initialized
                else HealthState.UNKNOWN
            ),
            summary="in-memory mock",
            checked_at=_now(),
            details={"active_calls": len(self._calls), "lines": len(self._lines)},
        )

    async def shutdown(self) -> None:
        self._calls.clear()
        self._initialized = False

    # --- queries ---------------------------------------------------------
    async def list_lines(self) -> list[LineInfo]:
        return list(self._lines.values())

    async def get_line_state(self, line_id: str) -> LineInfo:
        return self._lines.get(line_id, LineInfo(line_id=line_id, state=LineState.UNKNOWN))

    async def get_active_calls(self) -> list[CallSnapshot]:
        return [c.snapshot() for c in self._calls.values()]

    async def subscribe_call_events(self) -> AsyncIterator[CallEvent]:
        while True:
            yield await self._events.get()

    # --- commands (idempotent on command_id) ----------------------------
    async def dial(self, *, line_id: str, destination: str, command_id: str) -> CommandAccepted:
        if command_id in self._seen:
            return self._seen[command_id]
        call = _Call(
            call_id=f"mock-{next(_ID)}",
            direction=CallDirection.OUTBOUND,
            line_id=line_id,
            calling=PartyRef(number=line_id),
            called=PartyRef(number=destination),
        )
        self._calls[call.call_id] = call
        self._emit(call, NormalizedTelephonyEvent.CALL_RINGING)
        if self._auto_answer:
            self._advance(
                call, CallLifecycleState.CONNECTED, NormalizedTelephonyEvent.CALL_ANSWERED
            )
        return self._ack(command_id, call.call_id)

    async def answer(self, *, call_id: str, command_id: str) -> CommandAccepted:
        if command_id in self._seen:
            return self._seen[command_id]
        call = self._require(call_id)
        self._advance(call, CallLifecycleState.CONNECTED, NormalizedTelephonyEvent.CALL_ANSWERED)
        return self._ack(command_id, call_id)

    async def hangup(self, *, call_id: str, command_id: str) -> CommandAccepted:
        if command_id in self._seen:
            return self._seen[command_id]
        call = self._calls.get(call_id)
        if call is not None:
            self._advance(
                call, CallLifecycleState.DISCONNECTED, NormalizedTelephonyEvent.CALL_DISCONNECTED
            )
            self._calls.pop(call_id, None)
        return self._ack(command_id, call_id)

    async def hold(self, *, call_id: str, command_id: str) -> CommandAccepted:
        if command_id in self._seen:
            return self._seen[command_id]
        self._advance(
            self._require(call_id), CallLifecycleState.HELD, NormalizedTelephonyEvent.CALL_HELD
        )
        return self._ack(command_id, call_id)

    async def resume(self, *, call_id: str, command_id: str) -> CommandAccepted:
        if command_id in self._seen:
            return self._seen[command_id]
        self._advance(
            self._require(call_id),
            CallLifecycleState.CONNECTED,
            NormalizedTelephonyEvent.CALL_RESUMED,
        )
        return self._ack(command_id, call_id)

    async def transfer(self, *, call_id: str, destination: str, command_id: str) -> CommandAccepted:
        if not destination:
            raise ValueError("transfer requires a destination")
        if command_id in self._seen:
            return self._seen[command_id]
        call = self._require(call_id)
        call.called = PartyRef(number=destination)
        self._advance(
            call,
            CallLifecycleState.TRANSFERRING,
            NormalizedTelephonyEvent.CALL_TRANSFER_INITIATED,
        )
        self._advance(call, CallLifecycleState.CONNECTED, NormalizedTelephonyEvent.CALL_TRANSFERRED)
        return self._ack(command_id, call_id)

    async def conference(self, *, call_ids: list[str], command_id: str) -> CommandAccepted:
        if command_id in self._seen:
            return self._seen[command_id]
        for cid in call_ids:
            call = self._calls.get(cid)
            if call is not None:
                self._advance(
                    call,
                    CallLifecycleState.CONNECTED,
                    NormalizedTelephonyEvent.CALL_CONFERENCED,
                )
        return self._ack(command_id, call_ids[0] if call_ids else None)

    async def send_dtmf(self, *, call_id: str, dtmf: str, command_id: str) -> CommandAccepted:
        if command_id in self._seen:
            return self._seen[command_id]
        self._require(call_id)
        if not dtmf:
            raise ValueError("send_dtmf requires a non-empty sequence")
        # `dtmf` is a secret sequence (ADR-0025) — count it, never echo it back
        self._dtmf_sends.append(command_id)
        return self._ack(command_id, call_id, detail="dtmf sent")

    async def resolve_caller(self, *, number: str) -> CallerResolution:
        name = self._directory.get(number)
        return CallerResolution(number=number, matched=name is not None, display_name=name)

    async def reconcile(self) -> ReconcileResult:
        return ReconcileResult(
            lines=list(self._lines.values()),
            active_calls=[c.snapshot() for c in self._calls.values()],
            note="mock reconcile",
        )

    # --- scenario drivers (tests / demo) --------------------------------
    def simulate_incoming(
        self, *, from_number: str, to_line: str, display_name: str | None = None
    ) -> str:
        call = _Call(
            call_id=f"mock-{next(_ID)}",
            direction=CallDirection.INBOUND,
            line_id=to_line,
            calling=PartyRef(number=from_number, display_name=display_name),
            called=PartyRef(number=to_line),
        )
        self._calls[call.call_id] = call
        self._emit(call, NormalizedTelephonyEvent.CALL_OFFERED)
        self._advance(call, CallLifecycleState.RINGING, NormalizedTelephonyEvent.CALL_RINGING)
        if self._auto_answer:
            self._advance(
                call, CallLifecycleState.CONNECTED, NormalizedTelephonyEvent.CALL_ANSWERED
            )
        return call.call_id

    def simulate_provider_out_of_service(self) -> None:
        self._in_service = False
        self._push(self._bare_event(NormalizedTelephonyEvent.CTI_PROVIDER_OUT_OF_SERVICE))

    def simulate_provider_in_service(self) -> None:
        self._in_service = True
        self._push(self._bare_event(NormalizedTelephonyEvent.CTI_PROVIDER_IN_SERVICE))

    def replay_backlog(self) -> None:
        """Re-deliver every event so far — a provider reconnect."""
        for ev in list(self._backlog):
            self._events.put_nowait(ev)

    async def drain_events(self, limit: int = 100) -> list[CallEvent]:
        out: list[CallEvent] = []
        for _ in range(limit):
            if self._events.empty():
                break
            out.append(await self._events.get())
        return out

    # --- internals -----------------------------------------------------
    def _require(self, call_id: str) -> _Call:
        try:
            return self._calls[call_id]
        except KeyError as exc:
            raise LookupError(f"no such call: {call_id}") from exc

    def _advance(
        self, call: _Call, state: CallLifecycleState, event: NormalizedTelephonyEvent
    ) -> None:
        call.state = state
        if state is CallLifecycleState.CONNECTED and call.started_at is None:
            call.started_at = _now()
        self._emit(call, event)

    def _ack(
        self, command_id: str, call_id: str | None, *, detail: str | None = None
    ) -> CommandAccepted:
        ack = CommandAccepted(command_id=command_id, call_id=call_id, detail=detail)
        self._seen[command_id] = ack
        return ack

    def _emit(self, call: _Call, event_type: NormalizedTelephonyEvent) -> None:
        ev = CallEvent(
            telephony_event_id=f"mockev-{next(_ID)}",
            provider="telephony_mock",
            event_type=event_type,
            raw_event_type=f"Mock{event_type.value}",
            source_call_id=call.call_id,
            line_id=call.line_id,
            calling_number=call.calling.number if call.calling else None,
            called_number=call.called.number if call.called else None,
            display_name=call.calling.display_name if call.calling else None,
            occurred_at=_now(),
            received_at=_now(),
            gateway_node="mock",
            metadata={"direction": call.direction.value},
        )
        self._push(ev)

    def _bare_event(self, event_type: NormalizedTelephonyEvent) -> CallEvent:
        return CallEvent(
            telephony_event_id=f"mockev-{next(_ID)}",
            provider="telephony_mock",
            event_type=event_type,
            raw_event_type=f"Mock{event_type.value}",
            occurred_at=_now(),
            received_at=_now(),
            gateway_node="mock",
        )

    def _push(self, ev: CallEvent) -> None:
        self._backlog.append(ev)
        self._events.put_nowait(ev)


def build(config: dict[str, Any] | None = None) -> MockTelephonyProvider:
    """Manifest entry point — construct from validated config."""
    cfg = config or {}
    return MockTelephonyProvider(
        lines=cfg.get("lines"),
        auto_answer=bool(cfg.get("auto_answer", False)),
        directory=cfg.get("directory"),
    )
