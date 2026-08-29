"""Append-only domain-event log (MASTER_PROMPT §3, ADR-0011).

``event_seq`` is a ``BIGINT`` identity — assigned by the PostgreSQL primary
only, so it is strictly monotonic (gaps tolerated after a failover, order
guaranteed). Clients catch up by ``event_seq``, never by timestamp.

No UPDATE/DELETE path. The DB grant enforcing that is E04-10 / E23-09.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from typing import Any

from sqlalchemy import BigInteger, Identity, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base


class DomainEvent(Base):
    __tablename__ = "domain_events"

    event_seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    event_uuid: Mapped[uuid.UUID] = mapped_column(
        server_default=text("gen_random_uuid()"), unique=True
    )
    aggregate_type: Mapped[str] = mapped_column(String(64), index=True)
    aggregate_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    occurred_at_utc: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))
    occurred_at_local: Mapped[str | None] = mapped_column(String(40))
    node_id: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[uuid.UUID | None] = mapped_column()
    client_id: Mapped[str | None] = mapped_column(String(64))
    command_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    schema_version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
