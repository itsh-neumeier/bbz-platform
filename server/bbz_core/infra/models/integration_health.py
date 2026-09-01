"""Integration health snapshot (roadmap E22-05, MASTER_PROMPT §14 / §8.14).

One row per integration (the manifest id). The ``integration-health`` singleton
probes each active integration's ``health()`` on a cadence and upserts here; the
row also survives restarts and is identical on every node. ``state`` is the
normalised vocabulary an operator / alert rule reads
(``ok`` / ``degraded`` / ``down`` / ``disabled``).
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from sqlalchemy import CheckConstraint, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base, TimestampMixin


class IntegrationHealth(Base, TimestampMixin):
    __tablename__ = "integration_health"
    __table_args__ = (
        CheckConstraint(
            "state IN ('ok', 'degraded', 'down', 'disabled')", name="ck_integration_health_state"
        ),
    )

    integration_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    domain: Mapped[str] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(16), server_default="down")
    summary: Mapped[str] = mapped_column(String(300), server_default="")
    checked_at: Mapped[_dt.datetime | None] = mapped_column()
    last_ok_at: Mapped[_dt.datetime | None] = mapped_column()
    last_error_at: Mapped[_dt.datetime | None] = mapped_column()
    consecutive_errors: Mapped[int] = mapped_column(Integer, server_default="0")
    #: last time this integration was observed doing work (newest provider-inbox row)
    last_activity_at: Mapped[_dt.datetime | None] = mapped_column()
    #: non-secret health detail from the provider's own report
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
