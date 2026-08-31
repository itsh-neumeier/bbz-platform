"""Call lifecycle service (roadmap E11-04).

Consumes a normalized telephony event (already validated + deduplicated by
``telephony_ingest``), resolves — or, on first sight, creates with a stable
``bbz_call_id`` — the ``calls`` row, runs the pure :class:`CallAggregate`
transition, persists the new state, records participants, and appends +
audits the business call events (``CALL_RINGING`` / ``CALL_ANSWERED`` /
``CALL_ENDED``).

``register_call_dispatch()`` wires this in as ``telephony_ingest``'s
``set_call_event_dispatch`` hook (called from ``app.create_app``).
"""

from __future__ import annotations

import datetime as _dt
import secrets
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import AuditAction, AuditService
from bbz_core.domain.telephony import TERMINAL, CallAggregate, CallDirection, CallState
from bbz_core.infra import telephony_ingest
from bbz_core.infra.event_log import append_event
from bbz_core.infra.models.telephony import Call, CallParticipant, Line
from bbz_core.infra.repositories.contact_matching import ContactMatcher

#: business call event -> its audit action. Explicit (not ``AuditAction[...]``)
#: so the "critical action must be wired to an audit write" contract test sees
#: the literal references.
_AUDIT: dict[str, AuditAction] = {
    "CALL_RINGING": AuditAction.CALL_RINGING,
    "CALL_ANSWERED": AuditAction.CALL_ANSWERED,
    "CALL_ENDED": AuditAction.CALL_ENDED,
}

_INBOUND_FIRST = {"CALL_OFFERED", "CALL_RINGING"}


def _mint_bbz_call_id() -> str:
    day = _dt.datetime.now(_dt.UTC).strftime("%Y%m%d")
    return f"CALL-{day}-{secrets.token_hex(4).upper()}"


class CallLifecycleService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def on_provider_event(self, event: dict[str, Any]) -> None:
        source_call_id = event.get("source_call_id")
        if not source_call_id:
            return  # line / device / CTI events do not touch a call

        provider = event["provider"]
        call = (
            await self._s.execute(
                select(Call).where(Call.provider == provider, Call.source_call_id == source_call_id)
            )
        ).scalar_one_or_none()

        if call is None:
            call = Call(
                bbz_call_id=_mint_bbz_call_id(),
                provider=provider,
                source_call_id=source_call_id,
                direction=self._infer_direction(event).value,
                state=CallState.OFFERED.value,
                line_id=await self._resolve_line_id(provider, event.get("line_id")),
            )
            self._s.add(call)
            await self._s.flush()

        agg = CallAggregate(
            bbz_call_id=call.bbz_call_id,
            direction=CallDirection(call.direction),
            state=CallState(call.state),
            source_call_id=source_call_id,
            line_id=str(call.line_id) if call.line_id else None,
        )
        agg.apply_provider_event(event["event_type"])

        now = _dt.datetime.now(_dt.UTC)
        if agg.state.value != call.state:
            call.state = agg.state.value
            if agg.state is CallState.CONNECTED and call.started_at is None:
                call.started_at = now
            if agg.state in TERMINAL and call.ended_at is None:
                call.ended_at = now

        await self._record_participants(call.id, event)
        await self._resolve_caller(call, event)

        for de in agg.collect_events():
            seq = await append_event(
                self._s,
                aggregate_type="call",
                aggregate_id=call.id,
                event_type=de.type,
                payload=de.payload,
            )
            await AuditService(self._s).write(
                _AUDIT[de.type],
                target_type="call",
                target_id=str(call.id),
                after=de.payload,
                event_seq_ref=seq,
            )

    def _infer_direction(self, event: dict[str, Any]) -> CallDirection:
        # a call we are *offered* / that *rings* at us is inbound; anything else
        # (we dialled) is outbound. Providers may also carry it in metadata.
        meta = event.get("metadata") or {}
        if isinstance(meta.get("direction"), str):
            try:
                return CallDirection(meta["direction"])
            except ValueError:
                pass
        return (
            CallDirection.INBOUND
            if event["event_type"] in _INBOUND_FIRST
            else CallDirection.OUTBOUND
        )

    async def _resolve_line_id(self, provider: str, external_line_id: str | None) -> Any:
        if not external_line_id:
            return None
        return (
            await self._s.execute(
                select(Line.id).where(
                    Line.provider == provider, Line.external_id == external_line_id
                )
            )
        ).scalar_one_or_none()

    async def _resolve_caller(self, call: Call, event: dict[str, Any]) -> None:
        """Snapshot the calling party's contact + priority on the call (E11-08).

        Inbound only; the number is normalized and longest-matched against the
        phone book (``ContactMatcher``). A number that resolves to no single
        contact leaves ``caller_contact_id`` NULL — that *is* the "unknown"
        state. Re-attempted on each event while still unresolved, so a contact
        created mid-call is picked up.
        """
        if call.caller_contact_id is not None:
            return
        number = event.get("calling_number")
        if not number or call.direction != CallDirection.INBOUND.value:
            return
        match = await ContactMatcher(self._s).resolve(number)
        if match.matched:
            call.caller_contact_id = match.contact_id
            call.caller_priority = match.priority

    async def _record_participants(self, call_id: Any, event: dict[str, Any]) -> None:
        existing = {
            (p.number, p.role)
            for p in (
                await self._s.execute(
                    select(CallParticipant).where(CallParticipant.call_id == call_id)
                )
            )
            .scalars()
            .all()
        }
        for number, role in (
            (event.get("calling_number"), "caller"),
            (event.get("called_number"), "callee"),
        ):
            if number and (number, role) not in existing:
                self._s.add(
                    CallParticipant(
                        call_id=call_id,
                        number=number,
                        display_name=event.get("display_name") if role == "caller" else None,
                        role=role,
                    )
                )


def register_call_dispatch() -> None:
    async def _dispatch(session: AsyncSession, event: dict[str, Any]) -> None:
        from bbz_core.infra.repositories.line_status import LineStatusService

        await CallLifecycleService(session).on_provider_event(event)
        await LineStatusService(session).on_line_event(event)

    telephony_ingest.set_call_event_dispatch(_dispatch)
