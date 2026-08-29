"""Event domain: canonical status vocabulary and the pure event aggregate."""

from __future__ import annotations

from bbz_core.domain.events.aggregate import (
    DomainEventData,
    EventAggregate,
    EventDomainError,
    InvalidTransition,
)
from bbz_core.domain.events.state import (
    ALLOWED_TRANSITIONS,
    EventPriority,
    EventStatus,
    can_transition,
)

__all__ = [
    "ALLOWED_TRANSITIONS",
    "DomainEventData",
    "EventAggregate",
    "EventDomainError",
    "EventPriority",
    "EventStatus",
    "InvalidTransition",
    "can_transition",
]
