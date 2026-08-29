"""Pure event aggregate and state machine (roadmap E03-04, ADR-0008).

No I/O. Every transition method either

* mutates the aggregate **and** queues the matching domain-event(s), which the
  caller drains with :meth:`EventAggregate.collect_events`, or
* raises :class:`EventDomainError` and changes nothing.

Persistence, the ``version`` counter and ``event_status_history`` are the
repository's job (E03-05); the domain only decides *what* happened.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from bbz_core.domain.events.state import EventPriority, EventStatus, can_transition

MAX_TITLE = 300


class EventDomainError(Exception):
    """A command violated an event-domain rule; nothing was mutated."""


class InvalidTransition(EventDomainError):
    pass


@dataclass(frozen=True)
class DomainEventData:
    """A domain event the aggregate wants appended, as (type, payload)."""

    type: str
    payload: dict[str, Any]


def _clean_title(title: str) -> str:
    cleaned = title.strip()
    if not cleaned:
        raise EventDomainError("title must not be empty")
    if len(cleaned) > MAX_TITLE:
        raise EventDomainError(f"title must be <= {MAX_TITLE} characters")
    return cleaned


@dataclass
class EventAggregate:
    id: uuid.UUID
    title: str
    priority: EventPriority
    status: EventStatus
    bbz_id: uuid.UUID | None = None
    workplace_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    # Read-only here; the repository owns optimistic concurrency (E03-05).
    version: int = 1
    _pending: list[DomainEventData] = field(default_factory=list, repr=False)

    # -- construction ----------------------------------------------------------
    @classmethod
    def create(
        cls,
        *,
        event_id: uuid.UUID,
        title: str,
        priority: EventPriority,
        actor_id: uuid.UUID,
        bbz_id: uuid.UUID | None = None,
        workplace_id: uuid.UUID | None = None,
        source: str = "manual",
    ) -> EventAggregate:
        agg = cls(
            id=event_id,
            title=_clean_title(title),
            priority=EventPriority(priority),
            status=EventStatus.NEW,
            bbz_id=bbz_id,
            workplace_id=workplace_id,
        )
        agg._emit(
            "EVENT_CREATED",
            {
                "title": agg.title,
                "priority": agg.priority.value,
                "bbz_id": _s(bbz_id),
                "workplace_id": _s(workplace_id),
                "source": source,
                "actor_id": _s(actor_id),
            },
        )
        return agg

    # -- lifecycle transitions ----------------------------------------------------
    def accept(self, actor_id: uuid.UUID) -> None:
        self._transition(EventStatus.ACCEPTED, "EVENT_ACCEPTED", actor_id)

    def acknowledge(self, actor_id: uuid.UUID) -> None:
        self._transition(EventStatus.ACKNOWLEDGED, "EVENT_ACKNOWLEDGED", actor_id)

    def open(self, actor_id: uuid.UUID) -> None:
        # Only from acknowledged. Leaving "archived" is reactivate() (needs a reason).
        if self.status is not EventStatus.ACKNOWLEDGED:
            raise InvalidTransition(f"{self.status.value} -> opened is not allowed")
        self._transition(EventStatus.OPENED, "EVENT_OPENED", actor_id)

    def archive(self, actor_id: uuid.UUID, *, reason: str) -> None:
        reason = reason.strip()
        if not reason:
            raise EventDomainError("archive requires a reason")
        self._transition(EventStatus.ARCHIVED, "EVENT_ARCHIVED", actor_id, extra={"reason": reason})

    def reactivate(self, actor_id: uuid.UUID, *, reason: str) -> None:
        if self.status is not EventStatus.ARCHIVED:
            raise InvalidTransition(f"{self.status.value} -> reactivated is not allowed")
        reason = reason.strip()
        if not reason:
            raise EventDomainError("reactivation requires a reason")
        # archived -> opened, but the event type says "reactivated"
        self._transition(
            EventStatus.OPENED, "EVENT_REACTIVATED", actor_id, extra={"reason": reason}
        )

    # -- ownership (does not change status) --------------------------------------
    def assign(self, *, to_user_id: uuid.UUID, actor_id: uuid.UUID) -> None:
        if self.status in (EventStatus.ARCHIVED,):
            raise InvalidTransition("cannot assign an archived event")
        if self.assignee_id is not None:
            raise EventDomainError("event already has an owner; use take_over")
        self.assignee_id = to_user_id
        self._emit("EVENT_ASSIGNED", {"to_user_id": _s(to_user_id), "actor_id": _s(actor_id)})

    def take_over(self, *, new_user_id: uuid.UUID, actor_id: uuid.UUID) -> None:
        if self.status in (EventStatus.ARCHIVED,):
            raise InvalidTransition("cannot take over an archived event")
        if self.assignee_id is None:
            raise EventDomainError("event has no owner; use assign")
        if self.assignee_id == new_user_id:
            raise EventDomainError("event already owned by that user")
        previous = self.assignee_id
        self.assignee_id = new_user_id
        self._emit(
            "EVENT_TAKEN_OVER",
            {
                "from_user_id": _s(previous),
                "to_user_id": _s(new_user_id),
                "actor_id": _s(actor_id),
            },
        )

    # -- pending-event handling -------------------------------------------------
    def collect_events(self) -> list[DomainEventData]:
        """Return and clear the events produced since the last collect."""
        out = list(self._pending)
        self._pending.clear()
        return out

    # -- internals ------------------------------------------------------------
    def _transition(
        self,
        target: EventStatus,
        event_type: str,
        actor_id: uuid.UUID,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        if not can_transition(self.status, target):
            raise InvalidTransition(f"{self.status.value} -> {target.value} is not allowed")
        payload: dict[str, Any] = {
            "from": self.status.value,
            "to": target.value,
            "actor_id": _s(actor_id),
        }
        if extra:
            payload.update(extra)
        self.status = target
        self._emit(event_type, payload)

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        self._pending.append(DomainEventData(type=event_type, payload=payload))


def _s(value: uuid.UUID | None) -> str | None:
    return str(value) if value is not None else None
