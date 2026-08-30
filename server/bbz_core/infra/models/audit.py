"""Immutable audit log (MASTER_PROMPT §17).

Append-only. The ORM mapping refuses UPDATE and DELETE (the listeners below);
the matching DB grant / trigger that enforces the same at the database level is
E04-10 / E23-09. E04 extends this with the transactional outbox/inbox and the
audit-write service; E02-12 seeds it with authentication events.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from typing import Any

from sqlalchemy import BigInteger, String, Text, event, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from bbz_core.infra.models.base import Base, make_append_only, uuid_pk


class AuditImmutableError(RuntimeError):
    """An UPDATE or DELETE was attempted against the append-only audit log."""


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
    # The domain event this audit row corresponds to, when there is one
    # (MASTER_PROMPT §17). Null for infrastructure actions (e.g. login).
    event_seq_ref: Mapped[int | None] = mapped_column(BigInteger)


@event.listens_for(AuditEvent, "before_update")
def _block_audit_update(_mapper: Mapper[AuditEvent], _conn: object, _target: AuditEvent) -> None:
    raise AuditImmutableError("audit_events is append-only; UPDATE is not allowed")


@event.listens_for(AuditEvent, "before_delete")
def _block_audit_delete(_mapper: Mapper[AuditEvent], _conn: object, _target: AuditEvent) -> None:
    raise AuditImmutableError("audit_events is append-only; DELETE is not allowed")


# ADR-0020: enforce append-only in the database too (any client, not just the ORM).
make_append_only(AuditEvent.__table__)
