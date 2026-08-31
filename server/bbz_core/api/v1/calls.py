"""Call control API (roadmap E11-06).

Permission-gated, idempotent endpoints that translate an operator action into a
call on the **active** telephony provider (``telephony_mock`` today; a real CTI
gateway in Epic 12). Every attempt is audited (``CALL_CONTROL_ACTION``) with the
action and the provider's acknowledgement. A repeated ``X-Command-Id`` replays
the stored response and never re-hits the provider — no double "answer".
"""

from __future__ import annotations

import datetime as _dt
import uuid
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.api.errors import ConflictError, NotFoundError, ValidationError
from bbz_core.api.idempotency import CommandEnvelope, command_envelope
from bbz_core.audit import AuditAction, AuditService
from bbz_core.infra.event_log import append_event
from bbz_core.infra.idempotency import idempotent, request_hash
from bbz_core.infra.models.telephony import (
    Call,
    CallCategory,
    CallDirection,
    CallDocumentation,
    CallState,
)
from bbz_core.infra.repositories.call_queries import CallHistoryItem, CallQueryRepository
from bbz_core.integrations_host.providers import NoActiveProvider, active_telephony_provider

router = APIRouter(prefix="/calls", tags=["calls"])

_ProviderCall = Callable[[object, str, str], Awaitable[object]]


class DialIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    line_id: str = Field(min_length=1)
    destination: str = Field(min_length=1)


class TransferIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    destination: str = Field(min_length=1)


class ControlOut(BaseModel):
    call_id: uuid.UUID | None
    action: str
    accepted: bool
    detail: str | None = None


def _ack_fields(ack: object) -> tuple[bool, str | None, str | None]:
    accepted = bool(getattr(ack, "accepted", True))
    detail = getattr(ack, "detail", None)
    provider_call_id = getattr(ack, "call_id", None)
    return accepted, detail, provider_call_id


async def _provider() -> object:
    try:
        return await active_telephony_provider()
    except NoActiveProvider as exc:
        raise ConflictError(f"telephony is not available: {exc}") from exc


_FINAL_STATES = {CallState.DISCONNECTED.value, CallState.FAILED.value}


async def _finalize_ended(session: AsyncSession, call: Call, *, actor_id: uuid.UUID | None) -> None:
    """Move a call to ``disconnected`` and append + audit ``CALL_ENDED`` once
    (the hangup guard, E11-10). No-op if the call is already final."""
    if call.state in _FINAL_STATES:
        return
    from_state = call.state
    call.state = CallState.DISCONNECTED.value
    if call.ended_at is None:
        call.ended_at = _dt.datetime.now(_dt.UTC)
    seq = await append_event(
        session,
        aggregate_type="call",
        aggregate_id=call.id,
        event_type="CALL_ENDED",
        payload={
            "bbz_call_id": call.bbz_call_id,
            "source_call_id": call.source_call_id,
            "direction": call.direction,
            "from": from_state,
            "to": CallState.DISCONNECTED.value,
        },
        user_id=actor_id,
    )
    await AuditService(session).write(
        AuditAction.CALL_ENDED,
        actor_user_id=actor_id,
        target_type="call",
        target_id=str(call.id),
        after={"bbz_call_id": call.bbz_call_id, "from": from_state, "to": "disconnected"},
        event_seq_ref=seq,
    )


_Finalize = Callable[[AsyncSession, Call], Awaitable[str | None]]


async def _control(
    *,
    call_id: uuid.UUID,
    action: str,
    invoke: _ProviderCall,
    ctx: AuthContext,
    env: CommandEnvelope,
    session: AsyncSession,
    finalize: _Finalize | None = None,
) -> ControlOut:
    rhash = request_hash({"call_id": str(call_id), "action": action})
    async with idempotent(
        session,
        command_id=env.command_id,
        endpoint=f"POST /api/v1/calls/{{id}}/{action}",
        request_hash=rhash,
        user_id=ctx.user_id,
    ) as slot:
        if slot.replay is not None:
            return ControlOut.model_validate(slot.replay.body)

        call = await session.get(Call, call_id)
        if call is None:
            raise NotFoundError("call not found")
        if not call.source_call_id:
            raise ConflictError("the provider has not assigned this call an id yet")
        source_call_id, bbz_call_id = call.source_call_id, call.bbz_call_id

        provider = await _provider()
        ack = await invoke(provider, source_call_id, str(env.command_id))
        accepted, detail, _ = _ack_fields(ack)

        await session.rollback()
        note = detail
        async with session.begin():
            fresh = await session.get(Call, call_id)
            assert fresh is not None
            if finalize is not None:
                note = await finalize(session, fresh) or detail
            await AuditService(session).write(
                AuditAction.CALL_CONTROL_ACTION,
                actor_user_id=ctx.user_id,
                target_type="call",
                target_id=str(call_id),
                after={
                    "action": action,
                    "bbz_call_id": bbz_call_id,
                    "accepted": accepted,
                    "detail": note,
                },
            )
        out = ControlOut(call_id=call_id, action=action, accepted=accepted, detail=note)
        slot.set_result(status.HTTP_200_OK, out.model_dump(mode="json"))
        return out


@router.post("/{call_id}/answer", response_model=ControlOut)
async def answer_call(
    call_id: uuid.UUID,
    ctx: AuthContext = Depends(require("calls.answer")),
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> ControlOut:
    return await _control(
        call_id=call_id,
        action="answer",
        invoke=lambda p, scid, cid: p.answer(call_id=scid, command_id=cid),  # type: ignore[attr-defined]
        ctx=ctx,
        env=env,
        session=session,
    )


@router.post("/{call_id}/hangup", response_model=ControlOut)
async def hangup_call(
    call_id: uuid.UUID,
    ctx: AuthContext = Depends(require("calls.hangup")),
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> ControlOut:
    """Hang up. The connection ends, but the call is only **closed** once it has a
    documentation category — until then it sits in ``ended_pending_documentation``
    and shows up in ``GET /calls/pending-documentation`` (E11-10, §13.10)."""

    async def _guard(sess: AsyncSession, call: Call) -> str | None:
        doc = await sess.get(CallDocumentation, call.id)
        if doc is not None and doc.mandatory_done:
            await _finalize_ended(sess, call, actor_id=ctx.user_id)
            return "closed"
        call.state = CallState.ENDED_PENDING_DOCUMENTATION.value
        if call.ended_at is None:
            call.ended_at = _dt.datetime.now(_dt.UTC)
        return "pending documentation"

    return await _control(
        call_id=call_id,
        action="hangup",
        invoke=lambda p, scid, cid: p.hangup(call_id=scid, command_id=cid),  # type: ignore[attr-defined]
        ctx=ctx,
        env=env,
        session=session,
        finalize=_guard,
    )


@router.post("/{call_id}/hold", response_model=ControlOut)
async def hold_call(
    call_id: uuid.UUID,
    ctx: AuthContext = Depends(require("calls.hold")),
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> ControlOut:
    return await _control(
        call_id=call_id,
        action="hold",
        invoke=lambda p, scid, cid: p.hold(call_id=scid, command_id=cid),  # type: ignore[attr-defined]
        ctx=ctx,
        env=env,
        session=session,
    )


@router.post("/{call_id}/resume", response_model=ControlOut)
async def resume_call(
    call_id: uuid.UUID,
    ctx: AuthContext = Depends(require("calls.hold")),  # resume shares the hold permission
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> ControlOut:
    return await _control(
        call_id=call_id,
        action="resume",
        invoke=lambda p, scid, cid: p.resume(call_id=scid, command_id=cid),  # type: ignore[attr-defined]
        ctx=ctx,
        env=env,
        session=session,
    )


@router.post("/{call_id}/transfer", response_model=ControlOut)
async def transfer_call(
    call_id: uuid.UUID,
    body: TransferIn,
    ctx: AuthContext = Depends(require("calls.transfer")),
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> ControlOut:
    dest = body.destination
    return await _control(
        call_id=call_id,
        action="transfer",
        invoke=lambda p, scid, cid: p.transfer(call_id=scid, destination=dest, command_id=cid),  # type: ignore[attr-defined]
        ctx=ctx,
        env=env,
        session=session,
    )


class DialOut(BaseModel):
    action: str = "dial"
    accepted: bool
    detail: str | None = None


@router.post("/dial", response_model=DialOut)
async def dial(
    body: DialIn,
    ctx: AuthContext = Depends(require("calls.dial")),
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> DialOut:
    """Start an outbound call. The ``calls`` row appears once the provider's
    ``CALL_RINGING`` event is ingested (E11-03/04)."""
    rhash = request_hash({"line_id": body.line_id, "destination": body.destination})
    async with idempotent(
        session,
        command_id=env.command_id,
        endpoint="POST /api/v1/calls/dial",
        request_hash=rhash,
        user_id=ctx.user_id,
    ) as slot:
        if slot.replay is not None:
            return DialOut.model_validate(slot.replay.body)

        provider = await _provider()
        ack = await provider.dial(  # type: ignore[attr-defined]
            line_id=body.line_id, destination=body.destination, command_id=str(env.command_id)
        )
        accepted, detail, _ = _ack_fields(ack)
        await session.rollback()
        async with session.begin():
            await AuditService(session).write(
                AuditAction.CALL_CONTROL_ACTION,
                actor_user_id=ctx.user_id,
                target_type="call",
                after={
                    "action": "dial",
                    "line_id": body.line_id,
                    "destination": body.destination,
                    "accepted": accepted,
                },
            )
        out = DialOut(accepted=accepted, detail=detail)
        slot.set_result(status.HTTP_200_OK, out.model_dump(mode="json"))
        return out


# --- call documentation (E11-09) -------------------------------------------


class DocumentationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    #: §13.10 categories; an unknown value is a 422. None = not categorised yet.
    category: CallCategory | None = None
    free_text: str | None = Field(default=None, max_length=20_000)


class DocumentationOut(BaseModel):
    call_id: uuid.UUID
    category: str | None
    free_text: str | None
    documented_by: uuid.UUID | None
    documented_at: _dt.datetime | None
    mandatory_done: bool


def _doc_out(call_id: uuid.UUID, doc: CallDocumentation) -> DocumentationOut:
    return DocumentationOut(
        call_id=call_id,
        category=doc.category,
        free_text=doc.free_text,
        documented_by=doc.documented_by,
        documented_at=doc.documented_at,
        mandatory_done=doc.mandatory_done,
    )


@router.put("/{call_id}/documentation", response_model=DocumentationOut)
async def put_documentation(
    call_id: uuid.UUID,
    body: DocumentationIn,
    ctx: AuthContext = Depends(require("calls.document")),
    session: AsyncSession = Depends(db_session),
) -> DocumentationOut:
    """Categorise / annotate a call — inline during or after the conversation.
    Re-saving overwrites (last state wins). ``CALL_DOCUMENTED`` is emitted and
    audited only once a category is set (§13.10)."""
    free_text = (body.free_text or "").strip() or None
    await session.rollback()
    async with session.begin():
        call = await session.get(Call, call_id)
        if call is None:
            raise NotFoundError("call not found")
        bbz_call_id = call.bbz_call_id

        doc = await session.get(CallDocumentation, call_id)
        if doc is None:
            doc = CallDocumentation(call_id=call_id)
            session.add(doc)
        doc.category = body.category.value if body.category is not None else None
        doc.free_text = free_text
        doc.mandatory_done = doc.category is not None
        if doc.category is not None:
            doc.documented_by = ctx.user_id
            doc.documented_at = _dt.datetime.now(_dt.UTC)
            seq = await append_event(
                session,
                aggregate_type="call",
                aggregate_id=call_id,
                event_type="CALL_DOCUMENTED",
                payload={
                    "bbz_call_id": bbz_call_id,
                    "category": doc.category,
                    "has_free_text": free_text is not None,
                    "actor_id": str(ctx.user_id),
                },
                user_id=ctx.user_id,
            )
            await AuditService(session).write(
                AuditAction.CALL_DOCUMENTED,
                actor_user_id=ctx.user_id,
                target_type="call",
                target_id=str(call_id),
                after={"category": doc.category, "has_free_text": free_text is not None},
                event_seq_ref=seq,
            )
            # the call was hung up and only waiting on this category (E11-10)
            if call.state == CallState.ENDED_PENDING_DOCUMENTATION.value:
                await _finalize_ended(session, call, actor_id=ctx.user_id)
        await session.flush()
        return _doc_out(call_id, doc)


@router.get("/{call_id}/documentation", response_model=DocumentationOut)
async def get_documentation(
    call_id: uuid.UUID,
    _: AuthContext = Depends(require("calls.view")),
    session: AsyncSession = Depends(db_session),
) -> DocumentationOut:
    if await session.get(Call, call_id) is None:
        raise NotFoundError("call not found")
    doc = await session.get(CallDocumentation, call_id)
    if doc is None:
        return DocumentationOut(
            call_id=call_id,
            category=None,
            free_text=None,
            documented_by=None,
            documented_at=None,
            mandatory_done=False,
        )
    return _doc_out(call_id, doc)


class PendingDocItem(BaseModel):
    call_id: uuid.UUID
    bbz_call_id: str
    direction: str
    ended_at: _dt.datetime | None


class PendingDocOut(BaseModel):
    calls: list[PendingDocItem]


@router.get("/pending-documentation", response_model=PendingDocOut)
async def pending_documentation(
    _: AuthContext = Depends(require("calls.document")),
    session: AsyncSession = Depends(db_session),
) -> PendingDocOut:
    """Calls that were hung up without a documentation category — the open
    obligations (E11-10). Oldest first."""
    rows = (
        (
            await session.execute(
                select(Call)
                .where(Call.state == CallState.ENDED_PENDING_DOCUMENTATION.value)
                .order_by(Call.ended_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return PendingDocOut(
        calls=[
            PendingDocItem(
                call_id=c.id,
                bbz_call_id=c.bbz_call_id,
                direction=c.direction,
                ended_at=c.ended_at,
            )
            for c in rows
        ]
    )


# --- call history (E11-11) + waiting-call queue (E11-12) ----------------


class HistoryParticipant(BaseModel):
    number: str | None
    display_name: str | None
    role: str


class CallHistoryItemOut(BaseModel):
    id: uuid.UUID
    bbz_call_id: str
    provider: str
    direction: str
    state: str
    line_id: uuid.UUID | None
    workplace_id: uuid.UUID | None
    started_at: _dt.datetime | None
    ended_at: _dt.datetime | None
    created_at: _dt.datetime
    category: str | None
    has_free_text: bool
    caller_contact_id: uuid.UUID | None
    caller_priority: str | None
    participants: list[HistoryParticipant]


class CallHistoryOut(BaseModel):
    items: list[CallHistoryItemOut]
    next_cursor: str | None


def _history_item_out(it: CallHistoryItem) -> CallHistoryItemOut:
    return CallHistoryItemOut(
        id=it.id,
        bbz_call_id=it.bbz_call_id,
        provider=it.provider,
        direction=it.direction,
        state=it.state,
        line_id=it.line_id,
        workplace_id=it.workplace_id,
        started_at=it.started_at,
        ended_at=it.ended_at,
        created_at=it.created_at,
        category=it.category,
        has_free_text=it.has_free_text,
        caller_contact_id=it.caller_contact_id,
        caller_priority=it.caller_priority,
        participants=[
            HistoryParticipant(number=p.number, display_name=p.display_name, role=p.role)
            for p in it.participants
        ],
    )


@router.get("/ringing", response_model=CallHistoryOut)
async def ringing_queue(
    _: AuthContext = Depends(require("calls.view")),
    session: AsyncSession = Depends(db_session),
) -> CallHistoryOut:
    """Die Warteschlange wartender Anrufe (§13.8/§13.9, E11-12): Anrufe im
    Zustand ``offered`` / ``ringing``, sortiert nach Anrufer-Priorität
    (hoch→niedrig, unbekannt zuletzt), dann Wartezeit (längste zuerst).
    Unpaginiert — die Queue ist eine Handvoll Anrufe. Ein Client holt sie neu,
    sobald ein ``CALL_*``-Frame über ``GET /api/v1/events/stream`` ankommt.
    Read-only, kein Audit-Event."""
    items = await CallQueryRepository(session).ringing_queue()
    return CallHistoryOut(items=[_history_item_out(it) for it in items], next_cursor=None)


@router.get("", response_model=CallHistoryOut)
async def list_calls(
    direction: CallDirection | None = None,
    state: CallState | None = None,
    number: str | None = Query(default=None, max_length=64),
    category: CallCategory | None = None,
    since: _dt.datetime | None = None,
    until: _dt.datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
    _: AuthContext = Depends(require("calls.view_history")),
    session: AsyncSession = Depends(db_session),
) -> CallHistoryOut:
    """Rufhistorie (§13.8) — personenbeziehbar, daher ``calls.view_history`` +
    Scope (scope-Filter greift ab E23). Filter: Zeitraum (``since``/``until`` auf
    ``created_at``), Richtung, Nummer (exakter Treffer auf einen Teilnehmer),
    Kategorie, Status. Keyset-Pagination: ``next_cursor`` zurückgeben als
    ``cursor``. Ordnung ``created_at`` desc, dann ``id`` desc — deterministisch
    und stabil unter Inserts. Read-only, kein Audit-Event."""
    try:
        page = await CallQueryRepository(session).history(
            limit=limit,
            cursor=cursor,
            direction=direction.value if direction is not None else None,
            state=state.value if state is not None else None,
            number=number,
            category=category.value if category is not None else None,
            since=since,
            until=until,
        )
    except (ValueError, KeyError) as exc:
        raise ValidationError("invalid cursor") from exc

    return CallHistoryOut(
        items=[_history_item_out(it) for it in page.items], next_cursor=page.next_cursor
    )
