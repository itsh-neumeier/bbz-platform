"""Read models for the event views (roadmap E03-12).

Pure reads — no aggregate, no transaction requirement. Three shapes:

* :meth:`EventQueryRepository.work_queue` — the shared active work queue
  (non-archived, priority then age; MASTER_PROMPT §13.3);
* :meth:`EventQueryRepository.list_events` — the chronological list including
  archived, keyset-paginated on ``(created_at, id)`` so inserts never shift a
  page (MASTER_PROMPT §13.6);
* :meth:`EventQueryRepository.detail` — one event with its status history,
  active assignee and notes.

Scope filtering (a user only sees permitted BBZ/scopes) is a no-op until user
placement exists; the hook is :meth:`_scope_filter` and it is wired in E23.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, and_, case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.domain.events import EventPriority, EventStatus
from bbz_core.infra.models.domain_events import DomainEvent
from bbz_core.infra.models.events import (
    Event,
    EventAssignment,
    EventNote,
    EventStatusHistory,
)

_PRIORITY_RANK = case(
    (Event.priority == "critical", 0),
    (Event.priority == "high", 1),
    (Event.priority == "medium", 2),
    else_=3,
)


@dataclass(frozen=True)
class EventListItem:
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


@dataclass(frozen=True)
class EventPage:
    items: list[EventListItem]
    next_cursor: str | None


@dataclass(frozen=True)
class StatusHistoryItem:
    from_status: str | None
    to_status: str
    changed_at: _dt.datetime
    changed_by: uuid.UUID | None


@dataclass(frozen=True)
class NoteItem:
    id: uuid.UUID
    kind: str
    body: str
    created_by: uuid.UUID | None
    created_at: _dt.datetime


@dataclass(frozen=True)
class EventDetail:
    event: EventListItem
    description: str | None
    status_history: list[StatusHistoryItem]
    notes: list[NoteItem]


@dataclass(frozen=True)
class DomainEventItem:
    event_seq: int
    event_type: str
    occurred_at_utc: _dt.datetime
    user_id: uuid.UUID | None
    payload: dict[str, Any]


@dataclass(frozen=True)
class EventExport:
    detail: EventDetail
    domain_events: list[DomainEventItem]


def _cursor(item_created_at: _dt.datetime, item_id: uuid.UUID) -> str:
    return f"{item_created_at.timestamp():.6f}|{item_id}"


def _parse_cursor(raw: str) -> tuple[_dt.datetime, uuid.UUID]:
    ts, _, rid = raw.partition("|")
    return _dt.datetime.fromtimestamp(float(ts), tz=_dt.UTC), uuid.UUID(rid)


class EventQueryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    def _scope_filter(self, stmt: Select[tuple[Event]]) -> Select[tuple[Event]]:
        # E23: restrict to the caller's permitted BBZ/scopes. No-op for now.
        return stmt

    async def _assignees(self, event_ids: list[uuid.UUID]) -> dict[uuid.UUID, uuid.UUID]:
        if not event_ids:
            return {}
        rows = await self._s.execute(
            select(EventAssignment.event_id, EventAssignment.user_id).where(
                EventAssignment.active.is_(True),
                EventAssignment.event_id.in_(event_ids),
            )
        )
        return {row.event_id: row.user_id for row in rows.all()}

    async def _rows(self, stmt: Select[tuple[Event]]) -> list[EventListItem]:
        events = list((await self._s.execute(stmt)).scalars().all())
        assignees = await self._assignees([e.id for e in events])
        return [
            EventListItem(
                id=e.id,
                title=e.title,
                priority=e.priority,
                status=e.status,
                bbz_id=e.bbz_id,
                workplace_id=e.workplace_id,
                version=e.version,
                assignee_id=assignees.get(e.id),
                created_at=e.created_at,
                updated_at=e.updated_at,
            )
            for e in events
        ]

    async def priority_alert(self) -> list[EventListItem]:
        """High/critical events still in ``new`` (not yet accepted) — MASTER_PROMPT §13.7."""
        stmt = (
            select(Event)
            .where(
                Event.status == EventStatus.NEW.value,
                Event.priority.in_([EventPriority.CRITICAL.value, EventPriority.HIGH.value]),
            )
            .order_by(_PRIORITY_RANK.asc(), Event.created_at.asc(), Event.id.asc())
        )
        return await self._rows(self._scope_filter(stmt))

    async def work_queue(self, *, limit: int = 100) -> list[EventListItem]:
        stmt = (
            select(Event)
            .where(Event.status != EventStatus.ARCHIVED.value)
            .order_by(_PRIORITY_RANK.asc(), Event.created_at.asc(), Event.id.asc())
            .limit(limit)
        )
        return await self._rows(self._scope_filter(stmt))

    async def list_events(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        include_archived: bool = True,
        status: str | None = None,
    ) -> EventPage:
        stmt = select(Event).order_by(Event.created_at.desc(), Event.id.desc())
        if not include_archived:
            stmt = stmt.where(Event.status != EventStatus.ARCHIVED.value)
        if status is not None:
            stmt = stmt.where(Event.status == status)
        if cursor is not None:
            c_at, c_id = _parse_cursor(cursor)
            stmt = stmt.where(
                or_(
                    Event.created_at < c_at,
                    and_(Event.created_at == c_at, Event.id < c_id),
                )
            )
        rows = await self._rows(self._scope_filter(stmt.limit(limit + 1)))
        nxt: str | None = None
        if len(rows) > limit:
            rows = rows[:limit]
            last = rows[-1]
            nxt = _cursor(last.created_at, last.id)
        return EventPage(items=rows, next_cursor=nxt)

    async def detail(self, event_id: uuid.UUID) -> EventDetail | None:
        rows = await self._rows(self._scope_filter(select(Event).where(Event.id == event_id)))
        if not rows:
            return None
        row = await self._s.get(Event, event_id)
        assert row is not None
        history = (
            (
                await self._s.execute(
                    select(EventStatusHistory)
                    .where(EventStatusHistory.event_id == event_id)
                    .order_by(EventStatusHistory.changed_at.asc())
                )
            )
            .scalars()
            .all()
        )
        notes = (
            (
                await self._s.execute(
                    select(EventNote)
                    .where(EventNote.event_id == event_id)
                    .order_by(EventNote.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        return EventDetail(
            event=rows[0],
            description=row.description,
            status_history=[
                StatusHistoryItem(
                    from_status=h.from_status,
                    to_status=h.to_status,
                    changed_at=h.changed_at,
                    changed_by=h.changed_by,
                )
                for h in history
            ],
            notes=[
                NoteItem(
                    id=n.id,
                    kind=n.kind,
                    body=n.body,
                    created_by=n.created_by,
                    created_at=n.created_at,
                )
                for n in notes
            ],
        )

    async def export(self, event_id: uuid.UUID) -> EventExport | None:
        """Full bundle for one event, domain events ordered by ``event_seq``."""
        detail = await self.detail(event_id)
        if detail is None:
            return None
        rows = (
            (
                await self._s.execute(
                    select(DomainEvent)
                    .where(DomainEvent.aggregate_id == str(event_id))
                    .order_by(DomainEvent.event_seq.asc())
                )
            )
            .scalars()
            .all()
        )
        return EventExport(
            detail=detail,
            domain_events=[
                DomainEventItem(
                    event_seq=r.event_seq,
                    event_type=r.event_type,
                    occurred_at_utc=r.occurred_at_utc,
                    user_id=r.user_id,
                    payload=r.payload,
                )
                for r in rows
            ],
        )
