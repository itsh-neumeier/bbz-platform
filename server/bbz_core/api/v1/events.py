"""Event commands API (roadmap E03-06 ff.).

Every write here follows the same shape (MASTER_PROMPT §15, ADR-0011/0012):

1. ``require("events.<verb>")`` gates the caller.
2. The command envelope (``X-Command-Id`` / ``X-Expected-Version``) is parsed
   from headers; ``idempotent()`` makes a repeated ``X-Command-Id`` replay the
   stored response instead of acting twice.
3. The pure :class:`EventAggregate` decides what happened; :class:`EventRepository`
   persists state and the domain event(s) in one transaction.

CSRF: cookie-auth write protection is applied centrally in E23 (hardening), the
same as the other admin routers — not per route here.

TODO(E04-03): emit the matching audit-log entries once the domain-event audit
catalog exists; the immutable record today is the ``domain_events`` row.
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import uuid
from collections.abc import Awaitable, Callable, Iterator
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.api.errors import (
    ConflictError,
    NotFoundError,
    RateLimitedError,
    ValidationError,
)
from bbz_core.api.idempotency import CommandEnvelope, command_envelope
from bbz_core.api.reactivation import ReactivationTokenError, mint_token, verify_token
from bbz_core.audit import AuditAction, AuditService
from bbz_core.domain.events import (
    EventAggregate,
    EventDomainError,
    EventPriority,
    EventStatus,
    InvalidTransition,
)
from bbz_core.infra.event_log import append_event, head_seq
from bbz_core.infra.event_stream import notify_event_appended, sse_stream
from bbz_core.infra.idempotency import (
    CommandConflictError,
    CommandInProgressError,
    idempotent,
    request_hash,
)
from bbz_core.infra.models.domain_events import DomainEvent
from bbz_core.infra.models.events import Event, EventNote
from bbz_core.infra.models.identity import PresenceState, User, UserStatus
from bbz_core.infra.outbox import enqueue
from bbz_core.infra.repositories.archive_queries import (
    ArchiveDetail,
    ArchiveQueryRepository,
)
from bbz_core.infra.repositories.event_queries import (
    EventDetail,
    EventExport,
    EventListItem,
    EventQueryRepository,
)
from bbz_core.infra.repositories.events import (
    EventNotFoundError,
    EventRepository,
    VersionConflictError,
)
from bbz_core.infra.repositories.presence import PresenceRepository
from bbz_core.settings import get_settings

router = APIRouter(prefix="/events", tags=["events"])

_ENDPOINT_CREATE = "POST /api/v1/events"

Mutator = Callable[[EventAggregate, uuid.UUID], None]
Precondition = Callable[[AsyncSession, EventAggregate], Awaitable[None]]


@contextlib.contextmanager
def _translate() -> Iterator[None]:
    try:
        yield
    except CommandConflictError as exc:
        raise ConflictError("command id reused with a different body") from exc
    except CommandInProgressError as exc:
        raise ConflictError("an identical command is still being processed") from exc
    except VersionConflictError as exc:
        raise ConflictError(
            "event was modified by someone else",
            details={"event_id": str(exc.event_id), "expected_version": exc.expected},
        ) from exc
    except EventNotFoundError as exc:
        raise NotFoundError("event not found") from exc
    except InvalidTransition as exc:
        raise ConflictError(str(exc)) from exc
    except EventDomainError as exc:
        raise ValidationError(str(exc)) from exc


class CreateEventIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    priority: EventPriority
    description: str | None = Field(default=None, max_length=20_000)
    bbz_id: uuid.UUID | None = None
    workplace_id: uuid.UUID | None = None
    source: str = Field(default="manual", max_length=32)


class UpdateEventIn(BaseModel):
    """Whitelist of editable fields. Unknown fields are rejected (422)."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=20_000)
    priority: EventPriority | None = None


class EventOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    priority: EventPriority
    status: EventStatus
    bbz_id: uuid.UUID | None
    workplace_id: uuid.UUID | None
    version: int


class EventListItemOut(BaseModel):
    id: uuid.UUID
    title: str
    priority: str
    status: str
    bbz_id: uuid.UUID | None
    workplace_id: uuid.UUID | None
    version: int
    assignee_id: uuid.UUID | None
    created_at: _dt.datetime
    updated_at: _dt.datetime


class EventPageOut(BaseModel):
    items: list[EventListItemOut]
    next_cursor: str | None


class PriorityAlertItemOut(BaseModel):
    id: uuid.UUID
    priority: str
    title: str


class PriorityAlertOut(BaseModel):
    active: bool
    events: list[PriorityAlertItemOut]


class StatusHistoryOut(BaseModel):
    from_status: str | None
    to_status: str
    changed_at: _dt.datetime
    changed_by: uuid.UUID | None


class NoteOut(BaseModel):
    id: uuid.UUID
    kind: str
    body: str
    created_by: uuid.UUID | None
    created_at: _dt.datetime
    version: int = 1
    edited_by: uuid.UUID | None = None
    edited_at: _dt.datetime | None = None


class EventDetailOut(EventListItemOut):
    description: str | None
    status_history: list[StatusHistoryOut]
    notes: list[NoteOut]


class AddNoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=20_000)
    kind: Literal["work", "postprocess"] = "work"


class EditNoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=20_000)


class NoteVersionOut(BaseModel):
    id: uuid.UUID
    version: int
    body: str
    author_id: uuid.UUID | None
    written_at: _dt.datetime


class NoteThreadOut(BaseModel):
    """The current version of a note plus every superseded version, oldest first."""

    id: uuid.UUID
    thread_id: uuid.UUID
    kind: str
    body: str
    version: int
    created_by: uuid.UUID | None
    created_at: _dt.datetime
    edited_by: uuid.UUID | None
    edited_at: _dt.datetime | None
    history: list[NoteVersionOut]


class NoteThreadsOut(BaseModel):
    notes: list[NoteThreadOut]


class DomainEventOut(BaseModel):
    event_seq: int
    event_type: str
    occurred_at_utc: _dt.datetime
    user_id: uuid.UUID | None
    payload: dict[str, object]


class EventExportOut(BaseModel):
    event: EventDetailOut
    domain_events: list[DomainEventOut]


class WorkflowTaskResultOut(BaseModel):
    node_key: str
    result: dict[str, object]
    completed_by: uuid.UUID | None
    completed_at: _dt.datetime


class WorkflowDecisionOut(BaseModel):
    connector_node_key: str
    chosen_branches: list[str]
    auto: bool
    decided_by: uuid.UUID | None
    decided_at: _dt.datetime


class WorkflowInstanceOut(BaseModel):
    id: uuid.UUID
    template_key: str | None
    template_name: str | None
    template_version: int | None
    status: str
    started_at: _dt.datetime
    ended_at: _dt.datetime | None
    task_results: list[WorkflowTaskResultOut]
    decisions: list[WorkflowDecisionOut]


class AuditRefOut(BaseModel):
    id: uuid.UUID
    occurred_at_utc: _dt.datetime
    action: str
    actor_user_id: uuid.UUID | None
    correlation_id: str | None
    event_seq_ref: int | None


class ArchiveDetailOut(BaseModel):
    """Full, deterministically ordered history for one event — identical depth
    whether the event is active or archived (E20-03; see docs/domain/archive.md).
    """

    event: EventDetailOut
    domain_events: list[DomainEventOut]
    workflows: list[WorkflowInstanceOut]
    audit_refs: list[AuditRefOut]
    calls: list[object]


def _item_out(item: EventListItem) -> EventListItemOut:
    return EventListItemOut.model_validate(item, from_attributes=True)


def _export_out(export: EventExport) -> EventExportOut:
    return EventExportOut(
        event=_detail_out(export.detail),
        domain_events=[
            DomainEventOut(
                event_seq=d.event_seq,
                event_type=d.event_type,
                occurred_at_utc=d.occurred_at_utc,
                user_id=d.user_id,
                payload=d.payload,
            )
            for d in export.domain_events
        ],
    )


def _archive_detail_out(bundle: ArchiveDetail) -> ArchiveDetailOut:
    return ArchiveDetailOut(
        event=_detail_out(bundle.detail),
        domain_events=[
            DomainEventOut(
                event_seq=d.event_seq,
                event_type=d.event_type,
                occurred_at_utc=d.occurred_at_utc,
                user_id=d.user_id,
                payload=d.payload,
            )
            for d in bundle.domain_events
        ],
        workflows=[
            WorkflowInstanceOut(
                id=w.id,
                template_key=w.template_key,
                template_name=w.template_name,
                template_version=w.template_version,
                status=w.status,
                started_at=w.started_at,
                ended_at=w.ended_at,
                task_results=[
                    WorkflowTaskResultOut.model_validate(t, from_attributes=True)
                    for t in w.task_results
                ],
                decisions=[
                    WorkflowDecisionOut.model_validate(d, from_attributes=True) for d in w.decisions
                ],
            )
            for w in bundle.workflows
        ],
        audit_refs=[AuditRefOut.model_validate(a, from_attributes=True) for a in bundle.audit_refs],
        calls=list(bundle.calls),
    )


def _detail_out(detail: EventDetail) -> EventDetailOut:
    return EventDetailOut(
        **_item_out(detail.event).model_dump(),
        description=detail.description,
        status_history=[
            StatusHistoryOut.model_validate(h, from_attributes=True) for h in detail.status_history
        ],
        notes=[NoteOut.model_validate(n, from_attributes=True) for n in detail.notes],
    )


def _to_out(agg: EventAggregate, version: int) -> EventOut:
    return EventOut(
        id=agg.id,
        title=agg.title,
        description=agg.description,
        priority=agg.priority,
        status=agg.status,
        bbz_id=agg.bbz_id,
        workplace_id=agg.workplace_id,
        version=version,
    )


def _as_utc(value: _dt.datetime | None) -> _dt.datetime | None:
    """Query datetimes are interpreted as UTC when they carry no offset (ADR-0017)."""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=_dt.UTC)


@router.get("", response_model=EventPageOut)
async def list_events(
    queue: Literal["active"] | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    include_archived: bool = Query(default=True),
    status_filter: str | None = Query(default=None, alias="status"),
    priority: list[EventPriority] | None = Query(default=None),
    bbz_id: uuid.UUID | None = Query(default=None),
    assignee_id: uuid.UUID | None = Query(default=None),
    created_from: _dt.datetime | None = Query(default=None),
    created_to: _dt.datetime | None = Query(default=None),
    _: AuthContext = Depends(require("events.view")),
    session: AsyncSession = Depends(db_session),
) -> EventPageOut:
    """Chronological event list including archived — the backing query for the
    archive view (E20-02). ``queue=active`` returns the live work queue instead
    and ignores the archive filters; archived events never appear there.
    """
    q = EventQueryRepository(session)
    if queue == "active":
        items = await q.work_queue(limit=limit)
        return EventPageOut(items=[_item_out(i) for i in items], next_cursor=None)
    page = await q.list_events(
        limit=limit,
        cursor=cursor,
        include_archived=include_archived,
        status=status_filter,
        priority=[p.value for p in priority] if priority else None,
        bbz_id=bbz_id,
        assignee_id=assignee_id,
        created_from=_as_utc(created_from),
        created_to=_as_utc(created_to),
    )
    return EventPageOut(items=[_item_out(i) for i in page.items], next_cursor=page.next_cursor)


@router.get("/stream")
async def event_stream(
    request: Request,
    after_seq: int = Query(default=0, ge=0),
    _: AuthContext = Depends(require("events.view")),
) -> StreamingResponse:
    """SSE: missed events from ``after_seq`` (ADR-0011 catch-up) then live.

    Scope filtering per connection is deferred to E23 (as the read queries).
    """
    return StreamingResponse(
        sse_stream(after_seq, is_disconnected=request.is_disconnected),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class StreamHeadOut(BaseModel):
    event_seq: int


@router.get("/stream/head", response_model=StreamHeadOut)
async def stream_head(
    _: AuthContext = Depends(require("events.view")),
    session: AsyncSession = Depends(db_session),
) -> StreamHeadOut:
    """The current highest ``event_seq`` on this node's log. A client compares
    its last-seen seq to this on (re)connect to know whether it is behind; the
    value is identical on every node once replicated (docs/client-catchup)."""
    return StreamHeadOut(event_seq=await head_seq(session))


@router.get("/priority-alert", response_model=PriorityAlertOut)
async def priority_alert(
    _: AuthContext = Depends(require("events.view")),
    session: AsyncSession = Depends(db_session),
) -> PriorityAlertOut:
    """Is at least one high/critical event still unaccepted? (MASTER_PROMPT §13.7)"""
    items = await EventQueryRepository(session).priority_alert()
    return PriorityAlertOut(
        active=bool(items),
        events=[PriorityAlertItemOut(id=i.id, priority=i.priority, title=i.title) for i in items],
    )


@router.get("/{event_id}", response_model=EventDetailOut)
async def get_event(
    event_id: uuid.UUID,
    _: AuthContext = Depends(require("events.view")),
    session: AsyncSession = Depends(db_session),
) -> EventDetailOut:
    detail = await EventQueryRepository(session).detail(event_id)
    if detail is None:
        raise NotFoundError("event not found")
    return _detail_out(detail)


@router.post("", response_model=EventOut, status_code=status.HTTP_201_CREATED)
async def create_event(
    body: CreateEventIn,
    response: Response,
    ctx: AuthContext = Depends(require("events.create")),
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> EventOut:
    rhash = request_hash(body.model_dump(mode="json"))
    with _translate():
        async with idempotent(
            session,
            command_id=env.command_id,
            endpoint=_ENDPOINT_CREATE,
            request_hash=rhash,
            user_id=ctx.user_id,
        ) as slot:
            if slot.replay is not None:
                response.status_code = slot.replay.status
                out = EventOut.model_validate(slot.replay.body)
                response.headers["Location"] = f"/api/v1/events/{out.id}"
                return out

            agg = EventAggregate.create(
                event_id=uuid.uuid4(),
                title=body.title,
                priority=body.priority,
                actor_id=ctx.user_id,
                description=body.description,
                bbz_id=body.bbz_id,
                workplace_id=body.workplace_id,
                source=body.source,
            )
            repo = EventRepository(session)
            async with session.begin():
                version = await repo.add(agg, actor_id=ctx.user_id, command_id=env.command_id)
            out = _to_out(agg, version)
            slot.set_result(status.HTTP_201_CREATED, out.model_dump(mode="json"))
            await notify_event_appended()

    response.headers["Location"] = f"/api/v1/events/{out.id}"
    return out


async def _apply_transition(
    *,
    event_id: uuid.UUID,
    verb: str,
    mutate: Mutator,
    response: Response,
    ctx: AuthContext,
    env: CommandEnvelope,
    session: AsyncSession,
    body_fields: dict[str, object] | None = None,
    audit_action: AuditAction | None = None,
    audit_reason: str | None = None,
    precondition: Precondition | None = None,
) -> EventOut:
    """Shared body for the single-transition verbs (accept / acknowledge / open …).

    When ``audit_action`` is set, a status before/after audit row is written in
    the same transaction as the state change (mandatory audit — E03-10/11).
    ``precondition`` (if given) runs inside that transaction, on the loaded
    aggregate, before the mutation — it may raise to abort.
    """
    if env.expected_version is None:
        raise ValidationError("X-Expected-Version header is required")
    rhash = request_hash(
        {
            "event_id": str(event_id),
            "verb": verb,
            "expected_version": env.expected_version,
            "fields": body_fields or {},
        }
    )
    with _translate():
        async with idempotent(
            session,
            command_id=env.command_id,
            endpoint=f"POST /api/v1/events/{{id}}/{verb}",
            request_hash=rhash,
            user_id=ctx.user_id,
        ) as slot:
            if slot.replay is not None:
                response.status_code = slot.replay.status
                return EventOut.model_validate(slot.replay.body)

            repo = EventRepository(session)
            async with session.begin():
                agg = await repo.require(event_id)
                if precondition is not None:
                    await precondition(session, agg)
                before = {
                    "status": agg.status.value,
                    "assignee_id": str(agg.assignee_id) if agg.assignee_id else None,
                }
                mutate(agg, ctx.user_id)
                version = await repo.save(
                    agg,
                    actor_id=ctx.user_id,
                    expected_version=env.expected_version,
                    command_id=env.command_id,
                )
                if audit_action is not None:
                    after = {
                        "status": agg.status.value,
                        "assignee_id": str(agg.assignee_id) if agg.assignee_id else None,
                    }
                    await AuditService(session).write(
                        audit_action,
                        actor_user_id=ctx.user_id,
                        target_type="event",
                        target_id=str(event_id),
                        before=before,
                        after=after,
                        reason=audit_reason,
                    )
            out = _to_out(agg, version)
            slot.set_result(status.HTTP_200_OK, out.model_dump(mode="json"))
            await notify_event_appended()
    return out


@router.post("/{event_id}/accept", response_model=EventOut)
async def accept_event(
    event_id: uuid.UUID,
    response: Response,
    ctx: AuthContext = Depends(require("events.accept")),
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> EventOut:
    return await _apply_transition(
        event_id=event_id,
        verb="accept",
        mutate=lambda agg, actor: agg.accept(actor),
        response=response,
        ctx=ctx,
        env=env,
        session=session,
    )


@router.post("/{event_id}/acknowledge", response_model=EventOut)
async def acknowledge_event(
    event_id: uuid.UUID,
    response: Response,
    ctx: AuthContext = Depends(require("events.acknowledge")),
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> EventOut:
    return await _apply_transition(
        event_id=event_id,
        verb="acknowledge",
        mutate=lambda agg, actor: agg.acknowledge(actor),
        response=response,
        ctx=ctx,
        env=env,
        session=session,
    )


@router.post("/{event_id}/open", response_model=EventOut)
async def open_event(
    event_id: uuid.UUID,
    response: Response,
    ctx: AuthContext = Depends(require("events.open")),
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> EventOut:
    return await _apply_transition(
        event_id=event_id,
        verb="open",
        mutate=lambda agg, actor: agg.open(actor),
        response=response,
        ctx=ctx,
        env=env,
        session=session,
    )


@router.patch("/{event_id}", response_model=EventOut)
async def update_event(
    event_id: uuid.UUID,
    body: UpdateEventIn,
    response: Response,
    ctx: AuthContext = Depends(require("events.edit")),
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> EventOut:
    if env.expected_version is None:
        raise ValidationError("X-Expected-Version header is required")
    provided = body.model_dump(exclude_unset=True)
    if not provided:
        raise ValidationError("no fields to update")
    rhash = request_hash(
        {"event_id": str(event_id), "expected_version": env.expected_version, "fields": provided}
    )
    with _translate():
        async with idempotent(
            session,
            command_id=env.command_id,
            endpoint="PATCH /api/v1/events/{id}",
            request_hash=rhash,
            user_id=ctx.user_id,
        ) as slot:
            if slot.replay is not None:
                response.status_code = slot.replay.status
                return EventOut.model_validate(slot.replay.body)

            edits: dict[str, object] = {}
            if "title" in provided:
                edits["title"] = body.title
            if "description" in provided:
                edits["description"] = body.description
            if "priority" in provided:
                edits["priority"] = body.priority

            repo = EventRepository(session)
            async with session.begin():
                agg = await repo.require(event_id)
                agg.update(actor_id=ctx.user_id, **edits)  # type: ignore[arg-type]
                version = await repo.save(
                    agg,
                    actor_id=ctx.user_id,
                    expected_version=env.expected_version,
                    command_id=env.command_id,
                )
            out = _to_out(agg, version)
            slot.set_result(status.HTTP_200_OK, out.model_dump(mode="json"))
            await notify_event_appended()
    return out


class AssignEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_user_id: uuid.UUID


async def _require_active_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    row = await session.get(User, user_id)
    if row is None or row.status != UserStatus.ACTIVE.value:
        raise ValidationError("target_user_id must be an existing active user")


@router.post("/{event_id}/assign", response_model=EventOut)
async def assign_event(
    event_id: uuid.UUID,
    body: AssignEventIn,
    response: Response,
    ctx: AuthContext = Depends(require("events.assign")),
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> EventOut:
    if env.expected_version is None:
        raise ValidationError("X-Expected-Version header is required")
    await _require_active_user(session, body.target_user_id)
    return await _apply_transition(
        event_id=event_id,
        verb="assign",
        mutate=lambda agg, actor: agg.assign(to_user_id=body.target_user_id, actor_id=actor),
        response=response,
        ctx=ctx,
        env=env,
        session=session,
        body_fields={"target_user_id": str(body.target_user_id)},
        audit_action=AuditAction.EVENT_ASSIGNED,
    )


class TakeoverEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=2_000)


_TAKEOVER_ALLOWED_PRESENCE = {PresenceState.PAUSE.value, PresenceState.OFFLINE.value}


@router.post("/{event_id}/takeover", response_model=EventOut)
async def takeover_event(
    event_id: uuid.UUID,
    response: Response,
    body: TakeoverEventIn | None = None,
    ctx: AuthContext = Depends(require("events.takeover")),
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> EventOut:
    """Grab an event whose owner is on break / offline (MASTER_PROMPT §13.4).

    Presence is checked against the server-side effective state, never the
    client. The takeover is always audited (mandatory) in the same transaction
    as the state change. Scope ``bbz`` enforcement is deferred to E23.
    """
    if env.expected_version is None:
        raise ValidationError("X-Expected-Version header is required")
    reason = (body.reason if body else None) or None
    rhash = request_hash(
        {"event_id": str(event_id), "verb": "takeover", "expected_version": env.expected_version}
    )
    with _translate():
        async with idempotent(
            session,
            command_id=env.command_id,
            endpoint="POST /api/v1/events/{id}/takeover",
            request_hash=rhash,
            user_id=ctx.user_id,
        ) as slot:
            if slot.replay is not None:
                response.status_code = slot.replay.status
                return EventOut.model_validate(slot.replay.body)

            repo = EventRepository(session)
            async with session.begin():
                agg = await repo.require(event_id)
                previous = agg.assignee_id
                if previous is None:
                    raise ValidationError("event has no owner; use assign")
                await _require_owner_away(session, previous)
                agg.take_over(new_user_id=ctx.user_id, actor_id=ctx.user_id)
                version = await repo.save(
                    agg,
                    actor_id=ctx.user_id,
                    expected_version=env.expected_version,
                    command_id=env.command_id,
                )
                await AuditService(session).write(
                    AuditAction.EVENT_TAKEN_OVER,
                    actor_user_id=ctx.user_id,
                    target_type="event",
                    target_id=str(event_id),
                    before={"assignee_id": str(previous)},
                    after={"assignee_id": str(ctx.user_id)},
                    reason=reason,
                )
                # notify the person who lost the event (transport wired later);
                # in the same TX so it commits with the state change (ADR-0011).
                await enqueue(
                    session,
                    dedupe_key=f"event-takeover-notify:{event_id}:{version}",
                    action_type="notify",
                    payload={
                        "channel": "user",
                        "user_id": str(previous),
                        "subject": "event_taken_over",
                        "event_id": str(event_id),
                    },
                )
            out = _to_out(agg, version)
            slot.set_result(status.HTTP_200_OK, out.model_dump(mode="json"))
            await notify_event_appended()
    return out


async def _require_owner_away(session: AsyncSession, owner_id: uuid.UUID) -> None:
    view = await PresenceRepository(session).get(owner_id)
    state = view.state if view is not None else PresenceState.OFFLINE.value
    if state not in _TAKEOVER_ALLOWED_PRESENCE:
        raise ConflictError(
            "current owner is available; takeover is only allowed on break / offline",
            details={"owner_presence": state},
        )


class ArchiveEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=2_000)


class ReactivateEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm: bool = False
    reason: str = Field(min_length=1, max_length=2_000)
    #: the single-use token from ``POST /events/{id}/reactivation-intent`` (E20-05)
    token: str = Field(min_length=1)


class ReactivationIntentOut(BaseModel):
    token: str
    expires_at: _dt.datetime
    event_version: int


@router.post("/{event_id}/archive", response_model=EventOut)
async def archive_event(
    event_id: uuid.UUID,
    response: Response,
    body: ArchiveEventIn | None = None,
    ctx: AuthContext = Depends(require("events.archive")),
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> EventOut:
    reason = (body.reason if body else None) or None
    return await _apply_transition(
        event_id=event_id,
        verb="archive",
        mutate=lambda agg, actor: agg.archive(actor, reason=reason),
        response=response,
        ctx=ctx,
        env=env,
        session=session,
        body_fields={"reason": reason},
        audit_action=AuditAction.EVENT_ARCHIVED,
        audit_reason=reason,
    )


@router.post("/{event_id}/reactivation-intent", response_model=ReactivationIntentOut)
async def reactivation_intent(
    event_id: uuid.UUID,
    ctx: AuthContext = Depends(require("events.reactivate")),
    session: AsyncSession = Depends(db_session),
) -> ReactivationIntentOut:
    """Step one of the two-step reactivation (E20-05): mint a short-lived,
    single-purpose token bound to this event's current version. The client then
    presents it on ``POST /events/{id}/reactivate`` together with ``confirm`` and
    a reason. Read-only; not audited (the reactivation itself is)."""
    ev = await session.get(Event, event_id)
    if ev is None:
        raise NotFoundError("event not found")
    if ev.status != EventStatus.ARCHIVED.value:
        raise ConflictError("only an archived event can be reactivated")
    token, expiry = mint_token(event_id, ctx.user_id, ev.version)
    return ReactivationIntentOut(
        token=token,
        expires_at=_dt.datetime.fromtimestamp(expiry, tz=_dt.UTC),
        event_version=ev.version,
    )


async def _reactivation_cooldown(session: AsyncSession, agg: EventAggregate) -> None:
    seconds = get_settings().reactivation_cooldown_seconds
    if seconds <= 0:
        return
    last = (
        await session.execute(
            select(DomainEvent.occurred_at_utc)
            .where(
                DomainEvent.aggregate_id == str(agg.id),
                DomainEvent.event_type == "EVENT_REACTIVATED",
            )
            .order_by(DomainEvent.event_seq.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if last is None:
        return
    if last.tzinfo is None:
        last = last.replace(tzinfo=_dt.UTC)
    if _dt.datetime.now(_dt.UTC) - last < _dt.timedelta(seconds=seconds):
        raise RateLimitedError(
            f"this event was reactivated less than {seconds}s ago — wait before retrying"
        )


@router.post("/{event_id}/reactivate", response_model=EventOut)
async def reactivate_event(
    event_id: uuid.UUID,
    body: ReactivateEventIn,
    response: Response,
    ctx: AuthContext = Depends(require("events.reactivate")),
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> EventOut:
    # Two-step, no reactivation by accident (MASTER_PROMPT §13.6/§26.8):
    # explicit confirm + a valid single-use token bound to the exact version.
    if not body.confirm:
        raise ValidationError("reactivation requires confirm=true")
    if env.expected_version is None:
        raise ValidationError("X-Expected-Version header is required")
    try:
        verify_token(body.token, event_id, ctx.user_id, env.expected_version)
    except ReactivationTokenError as exc:
        raise ValidationError(str(exc)) from exc
    return await _apply_transition(
        event_id=event_id,
        verb="reactivate",
        mutate=lambda agg, actor: agg.reactivate(actor, reason=body.reason),
        response=response,
        ctx=ctx,
        env=env,
        session=session,
        body_fields={"reason": body.reason},
        audit_action=AuditAction.EVENT_REACTIVATED,
        audit_reason=body.reason,
        precondition=_reactivation_cooldown,
    )


class NoteAddedOut(BaseModel):
    note_id: uuid.UUID
    event_seq: int


@router.post("/{event_id}/notes", response_model=NoteAddedOut, status_code=status.HTTP_201_CREATED)
async def add_note(
    event_id: uuid.UUID,
    body: AddNoteIn,
    ctx: AuthContext = Depends(require("events.postprocess")),
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> NoteAddedOut:
    note_body = body.body.strip()
    if not note_body:
        raise ValidationError("note body must not be empty")
    rhash = request_hash({"event_id": str(event_id), "kind": body.kind, "body": note_body})
    with _translate():
        async with idempotent(
            session,
            command_id=env.command_id,
            endpoint="POST /api/v1/events/{id}/notes",
            request_hash=rhash,
            user_id=ctx.user_id,
        ) as slot:
            if slot.replay is not None:
                return NoteAddedOut.model_validate(slot.replay.body)

            note = EventNote(
                event_id=event_id,
                kind=body.kind,
                body=note_body,
                created_by=ctx.user_id,
            )
            async with session.begin():
                if await session.get(Event, event_id) is None:
                    raise NotFoundError("event not found")
                session.add(note)
                await session.flush()
                seq = await append_event(
                    session,
                    aggregate_type="event",
                    aggregate_id=event_id,
                    event_type="EVENT_NOTE_ADDED",
                    payload={
                        "note_id": str(note.id),
                        "kind": body.kind,
                        "body": note_body,
                        "actor_id": str(ctx.user_id),
                    },
                    user_id=ctx.user_id,
                    command_id=env.command_id,
                )
                await AuditService(session).write(
                    AuditAction.EVENT_NOTE_ADDED,
                    actor_user_id=ctx.user_id,
                    target_type="event",
                    target_id=str(event_id),
                    after={"note_id": str(note.id), "kind": body.kind, "version": 1},
                )
            out = NoteAddedOut(note_id=note.id, event_seq=seq)
            slot.set_result(status.HTTP_201_CREATED, out.model_dump(mode="json"))
    await notify_event_appended()
    return out


@router.get("/{event_id}/notes", response_model=NoteThreadsOut)
async def list_notes(
    event_id: uuid.UUID,
    _: AuthContext = Depends(require("events.view")),
    session: AsyncSession = Depends(db_session),
) -> NoteThreadsOut:
    """All note threads for the event — each current version plus its ordered
    history of superseded versions (E20-04)."""
    if await session.get(Event, event_id) is None:
        raise NotFoundError("event not found")
    threads = await EventQueryRepository(session).note_threads(event_id)
    return NoteThreadsOut(
        notes=[
            NoteThreadOut(
                id=t.id,
                thread_id=t.thread_id,
                kind=t.kind,
                body=t.body,
                version=t.version,
                created_by=t.created_by,
                created_at=t.created_at,
                edited_by=t.edited_by,
                edited_at=t.edited_at,
                history=[
                    NoteVersionOut(
                        id=v.id,
                        version=v.version,
                        body=v.body,
                        author_id=v.author_id,
                        written_at=v.written_at,
                    )
                    for v in t.history
                ],
            )
            for t in threads
        ]
    )


@router.patch("/{event_id}/notes/{note_id}", response_model=NoteAddedOut)
async def edit_note(
    event_id: uuid.UUID,
    note_id: uuid.UUID,
    body: EditNoteIn,
    ctx: AuthContext = Depends(require("events.postprocess")),
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> NoteAddedOut:
    """Edit a note — append-only: a new version is written and the previous one
    is kept, marked superseded (E20-04). ``note_id`` may be any version in the
    thread (or the thread root); the edit always targets the current version.
    """
    new_body = body.body.strip()
    if not new_body:
        raise ValidationError("note body must not be empty")
    rhash = request_hash({"note_id": str(note_id), "body": new_body})
    with _translate():
        async with idempotent(
            session,
            command_id=env.command_id,
            endpoint="PATCH /api/v1/events/{id}/notes/{note_id}",
            request_hash=rhash,
            user_id=ctx.user_id,
        ) as slot:
            if slot.replay is not None:
                return NoteAddedOut.model_validate(slot.replay.body)

            async with session.begin():
                if await session.get(Event, event_id) is None:
                    raise NotFoundError("event not found")
                referenced = await session.get(EventNote, note_id)
                if referenced is None or referenced.event_id != event_id:
                    raise NotFoundError("note not found")
                thread_id = referenced.thread_id or referenced.id
                old = (
                    await session.execute(
                        select(EventNote)
                        .where(
                            EventNote.event_id == event_id,
                            EventNote.superseded_by_id.is_(None),
                            or_(EventNote.id == thread_id, EventNote.thread_id == thread_id),
                        )
                        .with_for_update()
                    )
                ).scalar_one()
                if new_body == old.body:
                    raise ValidationError("note body is unchanged")

                new = EventNote(
                    event_id=event_id,
                    kind=old.kind,
                    body=new_body,
                    created_by=old.created_by,
                    version=old.version + 1,
                    thread_id=thread_id,
                    edited_by=ctx.user_id,
                    edited_at=_dt.datetime.now(_dt.UTC),
                )
                session.add(new)
                await session.flush()
                old.superseded_by_id = new.id
                seq = await append_event(
                    session,
                    aggregate_type="event",
                    aggregate_id=event_id,
                    event_type="EVENT_NOTE_UPDATED",
                    payload={
                        "note_id": str(new.id),
                        "thread_id": str(thread_id),
                        "supersedes_note_id": str(old.id),
                        "version": new.version,
                        "kind": old.kind,
                        "body": new_body,
                        "actor_id": str(ctx.user_id),
                    },
                    user_id=ctx.user_id,
                    command_id=env.command_id,
                )
                await AuditService(session).write(
                    AuditAction.EVENT_NOTE_UPDATED,
                    actor_user_id=ctx.user_id,
                    target_type="event",
                    target_id=str(event_id),
                    before={"note_id": str(old.id), "version": old.version, "body": old.body},
                    after={"note_id": str(new.id), "version": new.version, "body": new_body},
                )
            out = NoteAddedOut(note_id=new.id, event_seq=seq)
            slot.set_result(status.HTTP_200_OK, out.model_dump(mode="json"))
    await notify_event_appended()
    return out


@router.get("/{event_id}/export", response_model=EventExportOut)
async def export_event(
    event_id: uuid.UUID,
    ctx: AuthContext = Depends(require("events.export")),
    session: AsyncSession = Depends(db_session),
) -> EventExportOut:
    export = await EventQueryRepository(session).export(event_id)
    if export is None:
        raise NotFoundError("event not found")
    await session.rollback()  # close the read tx before the audit write tx
    async with session.begin():
        await AuditService(session).write(
            AuditAction.EVENT_EXPORTED,
            actor_user_id=ctx.user_id,
            target_type="event",
            target_id=str(event_id),
        )
    return _export_out(export)


@router.get("/{event_id}/archive-detail", response_model=ArchiveDetailOut)
async def archive_detail(
    event_id: uuid.UUID,
    _: AuthContext = Depends(require("events.view")),
    session: AsyncSession = Depends(db_session),
) -> ArchiveDetailOut:
    """Complete history for one event — status, notes, workflow results, calls
    (Epic 11), and audit references — with the same depth and deterministic
    ordering whether the event is active or archived (E20-03). Read-only, no
    audit. See ``docs/domain/archive.md``.
    """
    bundle = await ArchiveQueryRepository(session).detail(event_id)
    if bundle is None:
        raise NotFoundError("event not found")
    return _archive_detail_out(bundle)
