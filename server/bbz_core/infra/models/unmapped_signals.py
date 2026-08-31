"""Unmapped-source queue (roadmap E15-12).

A normalized inbound signal (E15-04) that the engine (E15-09) matched to **no
published trigger rule** lands here for admin diagnosis / mapping — it is never
an error (``.ai/TECHNICAL_TRIGGERS.md`` "Unmapped-source queue for diagnostics").

Rows are deduplicated on ``dedupe_key`` (provider + signal type + the source's
identifying fields): the same doorbell ringing an unconfigured station a hundred
times is one row with ``occurrences = 100``, not a hundred rows.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base, uuid_pk


class UnmappedSignal(Base):
    __tablename__ = "unmapped_signals"

    id: Mapped[uuid.UUID] = uuid_pk()
    #: provider + signal type + a stable fingerprint of the source identifiers
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    signal_type: Mapped[str] = mapped_column(String(64), index=True)
    #: the signal's ``source`` object (ani / dnis / external_source_id / …) — the
    #: identifiers an admin uses to decide which endpoint this should map to
    source: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    #: the full normalized signal, kept for inspection / replay after mapping
    sample: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    occurrences: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    first_seen_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))
    last_seen_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))
    #: set when an admin maps this source (E15-12 "Zuordnung")
    resolved_at: Mapped[_dt.datetime | None] = mapped_column()
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    resolved_endpoint_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("technical_endpoints.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(Text)
