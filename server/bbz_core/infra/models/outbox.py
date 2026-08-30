"""Transactional outbox for external side effects (ADR-0011, MASTER_PROMPT §29).

A command that must cause an external effect (open a door, raise an alarm, send
a notification) writes an :class:`ExternalActionOutbox` row **in the same
transaction** as its state change. A dispatcher worker then delivers it
idempotently, with retry + backoff. ``dedupe_key`` is UNIQUE — a retry of the
same logical action (same ``provider_event_id + rule_version + action_index``,
say) can never enqueue twice.
"""

from __future__ import annotations

import datetime as _dt
import enum
import uuid
from typing import Any

from sqlalchemy import CheckConstraint, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base, uuid_pk


class OutboxStatus(enum.StrEnum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    FAILED = "failed"


def _status_check() -> CheckConstraint:
    allowed = ", ".join(f"'{s.value}'" for s in OutboxStatus)
    return CheckConstraint(f"status IN ({allowed})", name="status")


class ExternalActionOutbox(Base):
    __tablename__ = "external_action_outbox"
    __table_args__ = (_status_check(),)

    id: Mapped[uuid.UUID] = uuid_pk()
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True)
    action_type: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(
        String(16), server_default=OutboxStatus.PENDING.value, index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    next_attempt_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"), index=True)
    last_error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))
    dispatched_at: Mapped[_dt.datetime | None] = mapped_column()
