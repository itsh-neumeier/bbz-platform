"""Canonical event status / priority vocabulary (MASTER_PROMPT §13).

These live in the pure domain layer; ``bbz_core.infra`` re-uses them for its
``CHECK`` constraints, and the API serialises them as-is. New values are a plain
code + migration change — the DB columns are ``VARCHAR`` + named ``CHECK``, not
native enums.
"""

from __future__ import annotations

import enum


class EventPriority(enum.StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EventStatus(enum.StrEnum):
    NEW = "new"
    ACCEPTED = "accepted"
    ACKNOWLEDGED = "acknowledged"
    OPENED = "opened"
    ARCHIVED = "archived"


#: Allowed ``status`` transitions (MASTER_PROMPT §13 lifecycle). Reactivation is
#: ``archived -> opened`` and is deliberately the only way out of ``archived``.
ALLOWED_TRANSITIONS: dict[EventStatus, frozenset[EventStatus]] = {
    EventStatus.NEW: frozenset({EventStatus.ACCEPTED}),
    EventStatus.ACCEPTED: frozenset({EventStatus.ACKNOWLEDGED}),
    EventStatus.ACKNOWLEDGED: frozenset({EventStatus.OPENED}),
    EventStatus.OPENED: frozenset({EventStatus.ARCHIVED}),
    EventStatus.ARCHIVED: frozenset({EventStatus.OPENED}),
}


def can_transition(src: EventStatus, dst: EventStatus) -> bool:
    return dst in ALLOWED_TRANSITIONS.get(src, frozenset())
