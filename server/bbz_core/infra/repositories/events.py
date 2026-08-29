"""Event repository + unit-of-work (roadmap E03-05, ADR-0011).

State and its domain events are written **in the same transaction**: every
method here assumes the caller has already opened one (``async with
session.begin(): ...``) — exactly like :func:`bbz_core.infra.event_log.append_event`,
which this module drives. A state change without its event, or vice versa, is
therefore impossible: both commit together or both roll back.

``events.version`` is the optimistic-concurrency counter. :meth:`EventRepository.save`
bumps it with a guarded ``UPDATE ... WHERE version = :expected``; a mismatch
raises :class:`VersionConflictError` (HTTP 409 via ADR-0012).
"""

from __future__ import annotations

import uuid
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.domain.events import EventAggregate, EventPriority, EventStatus
from bbz_core.infra.event_log import append_event
from bbz_core.infra.models.events import (
    Event,
    EventAssignment,
    EventStatusHistory,
)
from bbz_core.logging import correlation_id

_AGG_TYPE = "event"


class EventRepositoryError(Exception):
    pass


class VersionConflictError(EventRepositoryError):
    """``X-Expected-Version`` did not match the stored version (HTTP 409)."""

    def __init__(self, event_id: uuid.UUID, expected: int) -> None:
        super().__init__(f"event {event_id}: version {expected} is stale")
        self.event_id = event_id
        self.expected = expected


class EventNotFoundError(EventRepositoryError):
    pass


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # -- read ----------------------------------------------------------------
    async def get(self, event_id: uuid.UUID) -> EventAggregate | None:
        row = await self._s.get(Event, event_id)
        if row is None:
            return None
        assignee = (
            await self._s.execute(
                select(EventAssignment.user_id).where(
                    EventAssignment.event_id == event_id,
                    EventAssignment.active.is_(True),
                )
            )
        ).scalar_one_or_none()
        return EventAggregate(
            id=row.id,
            title=row.title,
            priority=EventPriority(row.priority),
            status=EventStatus(row.status),
            description=row.description,
            bbz_id=row.bbz_id,
            workplace_id=row.workplace_id,
            assignee_id=assignee,
            version=row.version,
        )

    async def require(self, event_id: uuid.UUID) -> EventAggregate:
        agg = await self.get(event_id)
        if agg is None:
            raise EventNotFoundError(str(event_id))
        return agg

    # -- write -------------------------------------------------------------------
    async def add(
        self,
        agg: EventAggregate,
        *,
        actor_id: uuid.UUID,
        command_id: uuid.UUID | None = None,
    ) -> int:
        """Persist a freshly created aggregate (status ``new``, version 1)."""
        self._require_tx()
        self._s.add(
            Event(
                id=agg.id,
                title=agg.title,
                description=agg.description,
                priority=agg.priority.value,
                status=agg.status.value,
                bbz_id=agg.bbz_id,
                workplace_id=agg.workplace_id,
                version=1,
            )
        )
        self._s.add(
            EventStatusHistory(
                event_id=agg.id,
                from_status=None,
                to_status=agg.status.value,
                changed_by=actor_id,
                correlation_id=correlation_id.get(),
            )
        )
        await self._append_pending(agg, actor_id=actor_id, command_id=command_id)
        agg.version = 1
        return 1

    async def save(
        self,
        agg: EventAggregate,
        *,
        actor_id: uuid.UUID,
        expected_version: int,
        command_id: uuid.UUID | None = None,
    ) -> int:
        """Persist a mutated aggregate under an optimistic-concurrency guard."""
        self._require_tx()
        new_version = expected_version + 1
        result = cast(
            "CursorResult[Any]",
            await self._s.execute(
                update(Event)
                .where(Event.id == agg.id, Event.version == expected_version)
                .values(
                    title=agg.title,
                    description=agg.description,
                    priority=agg.priority.value,
                    status=agg.status.value,
                    bbz_id=agg.bbz_id,
                    workplace_id=agg.workplace_id,
                    version=new_version,
                )
            ),
        )
        if result.rowcount == 0:
            raise VersionConflictError(agg.id, expected_version)

        for ev in agg.collect_events():
            src = ev.payload.get("from")
            dst = ev.payload.get("to")
            if src is not None and dst is not None and src != dst:
                self._s.add(
                    EventStatusHistory(
                        event_id=agg.id,
                        from_status=src,
                        to_status=dst,
                        changed_by=actor_id,
                        correlation_id=correlation_id.get(),
                    )
                )
            await self._reconcile_assignment(agg, ev.type, actor_id=actor_id)
            await append_event(
                self._s,
                aggregate_type=_AGG_TYPE,
                aggregate_id=agg.id,
                event_type=ev.type,
                payload=ev.payload,
                user_id=actor_id,
                command_id=command_id,
            )
        agg.version = new_version
        return new_version

    # -- internals ------------------------------------------------------------
    async def _append_pending(
        self,
        agg: EventAggregate,
        *,
        actor_id: uuid.UUID,
        command_id: uuid.UUID | None,
    ) -> None:
        for ev in agg.collect_events():
            await append_event(
                self._s,
                aggregate_type=_AGG_TYPE,
                aggregate_id=agg.id,
                event_type=ev.type,
                payload=ev.payload,
                user_id=actor_id,
                command_id=command_id,
            )

    async def _reconcile_assignment(
        self, agg: EventAggregate, event_type: str, *, actor_id: uuid.UUID
    ) -> None:
        if event_type not in ("EVENT_ASSIGNED", "EVENT_TAKEN_OVER"):
            return
        # Keep the "one active row per event" invariant (partial unique index):
        # retire any active row, then flush before inserting the replacement.
        await self._s.execute(
            update(EventAssignment)
            .where(EventAssignment.event_id == agg.id, EventAssignment.active.is_(True))
            .values(active=False)
        )
        await self._s.flush()
        assert agg.assignee_id is not None  # guaranteed by the aggregate for these events
        self._s.add(
            EventAssignment(
                event_id=agg.id, user_id=agg.assignee_id, assigned_by=actor_id, active=True
            )
        )

    def _require_tx(self) -> None:
        if not self._s.in_transaction():
            raise EventRepositoryError(
                "EventRepository writes must run inside the caller's transaction"
            )
