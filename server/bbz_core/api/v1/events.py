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
import uuid
from collections.abc import Callable, Iterator

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.api.errors import ConflictError, NotFoundError, ValidationError
from bbz_core.api.idempotency import CommandEnvelope, command_envelope
from bbz_core.domain.events import (
    EventAggregate,
    EventDomainError,
    EventPriority,
    EventStatus,
    InvalidTransition,
)
from bbz_core.infra.idempotency import (
    CommandConflictError,
    CommandInProgressError,
    idempotent,
    request_hash,
)
from bbz_core.infra.repositories.events import (
    EventNotFoundError,
    EventRepository,
    VersionConflictError,
)

router = APIRouter(prefix="/events", tags=["events"])

_ENDPOINT_CREATE = "POST /api/v1/events"

Mutator = Callable[[EventAggregate, uuid.UUID], None]


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
    bbz_id: uuid.UUID | None = None
    workplace_id: uuid.UUID | None = None
    source: str = Field(default="manual", max_length=32)


class EventOut(BaseModel):
    id: uuid.UUID
    title: str
    priority: EventPriority
    status: EventStatus
    bbz_id: uuid.UUID | None
    workplace_id: uuid.UUID | None
    version: int


def _to_out(agg: EventAggregate, version: int) -> EventOut:
    return EventOut(
        id=agg.id,
        title=agg.title,
        priority=agg.priority,
        status=agg.status,
        bbz_id=agg.bbz_id,
        workplace_id=agg.workplace_id,
        version=version,
    )


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
                bbz_id=body.bbz_id,
                workplace_id=body.workplace_id,
                source=body.source,
            )
            repo = EventRepository(session)
            async with session.begin():
                version = await repo.add(agg, actor_id=ctx.user_id, command_id=env.command_id)
            out = _to_out(agg, version)
            slot.set_result(status.HTTP_201_CREATED, out.model_dump(mode="json"))

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
) -> EventOut:
    """Shared body for the single-transition verbs (accept / acknowledge / open …)."""
    if env.expected_version is None:
        raise ValidationError("X-Expected-Version header is required")
    rhash = request_hash(
        {"event_id": str(event_id), "verb": verb, "expected_version": env.expected_version}
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
                mutate(agg, ctx.user_id)
                version = await repo.save(
                    agg,
                    actor_id=ctx.user_id,
                    expected_version=env.expected_version,
                    command_id=env.command_id,
                )
            out = _to_out(agg, version)
            slot.set_result(status.HTTP_200_OK, out.model_dump(mode="json"))
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
