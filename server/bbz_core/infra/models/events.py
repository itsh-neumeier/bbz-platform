"""Event core tables: events, status history, assignments, notes.

MASTER_PROMPT §3/§13/§14, roadmap E03-01. Schema only.

Ownership is for the WHOLE event (§13.4): exactly one active row in
``event_assignments`` per event (a partial unique index). ``events.version``
is the optimistic-concurrency counter (starts at 1).
"""

from __future__ import annotations

import datetime as _dt
import enum
import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.domain.events.state import EventPriority, EventStatus
from bbz_core.infra.models.base import Base, TimestampMixin, uuid_pk

__all__ = [
    "Event",
    "EventAssignment",
    "EventNote",
    "EventNoteKind",
    "EventPriority",
    "EventStatus",
    "EventStatusHistory",
]


class EventNoteKind(enum.StrEnum):
    WORK = "work"
    POSTPROCESS = "postprocess"


def _in_check(column: str, values: type[enum.StrEnum], name: str) -> CheckConstraint:
    allowed = ", ".join(f"'{v.value}'" for v in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=name)


class Event(Base, TimestampMixin):
    __tablename__ = "events"
    __table_args__ = (
        _in_check("priority", EventPriority, "event_priority"),
        _in_check("status", EventStatus, "event_status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), server_default=EventStatus.NEW.value)
    # Scope fields (E02-07). No BBZ/workplace entities yet — plain UUIDs.
    bbz_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    workplace_id: Mapped[uuid.UUID | None] = mapped_column()
    source: Mapped[str] = mapped_column(String(32), server_default="manual")
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class EventStatusHistory(Base):
    __tablename__ = "event_status_history"

    id: Mapped[uuid.UUID] = uuid_pk()
    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(16))
    to_status: Mapped[str] = mapped_column(String(16))
    changed_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    correlation_id: Mapped[str | None] = mapped_column(String(64))


class EventAssignment(Base):
    __tablename__ = "event_assignments"
    __table_args__ = (
        Index(
            "uq_event_assignments_one_active",
            "event_id",
            unique=True,
            postgresql_where=text("active"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    assigned_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    active: Mapped[bool] = mapped_column(server_default=text("true"))


class EventNote(Base):
    __tablename__ = "event_notes"
    __table_args__ = (_in_check("kind", EventNoteKind, "event_note_kind"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16), server_default=EventNoteKind.WORK.value)
    body: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))
