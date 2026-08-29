"""Command dedupe / replay store (MASTER_PROMPT §15, ADR-0011/0012).

One row per ``X-Command-Id``. A duplicate command returns the stored result
instead of re-executing. A row with ``result_status IS NULL`` is in flight.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base


class Command(Base):
    __tablename__ = "commands"
    __table_args__ = (
        # purge_stale() scans pending rows by age.
        Index(
            "ix_commands_pending_created_at",
            "created_at",
            postgresql_where=text("result_status IS NULL"),
        ),
    )

    command_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    endpoint: Mapped[str] = mapped_column(String(200))
    request_hash: Mapped[str] = mapped_column(String(64))
    result_status: Mapped[int | None] = mapped_column(Integer)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))
    completed_at: Mapped[_dt.datetime | None] = mapped_column()
