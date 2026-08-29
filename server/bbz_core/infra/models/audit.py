"""Immutable audit log (MASTER_PROMPT §17).

Append-only: no ``updated_at``, and the DB grant that forbids UPDATE/DELETE is
added in E04-10 / E23-09. E04 extends this with the transactional outbox/inbox
and the audit-write service; E02-12 seeds it with authentication events.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from typing import Any

from sqlalchemy import String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base, uuid_pk


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    occurred_at_utc: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"), index=True)
    node_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64), index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    actor_client_id: Mapped[str | None] = mapped_column(String(64))
    workplace_id: Mapped[str | None] = mapped_column(String(64))
    target_type: Mapped[str | None] = mapped_column(String(64))
    target_id: Mapped[str | None] = mapped_column(String(64))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True)
