"""Directory sync bookkeeping (roadmap E21-04).

One row per directory source (``ldap_ad`` today). Records when the sync
singleton last ran, whether it succeeded, the last error, and a small summary of
the last run (counts). The singleton reads ``last_run_at`` to decide whether the
configured interval has elapsed; the summary feeds the reporting endpoint.
Survives restarts and is identical on every node.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base, TimestampMixin


class DirectorySyncState(Base, TimestampMixin):
    __tablename__ = "directory_sync_state"

    #: the directory source key (matches the ``AuthIdentity.provider``, e.g. ``ldap_ad``)
    source: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_run_at: Mapped[_dt.datetime | None] = mapped_column()
    last_success_at: Mapped[_dt.datetime | None] = mapped_column()
    #: last failure message (redaction net applies — never a secret)
    last_error: Mapped[str | None] = mapped_column(Text)
    #: counts of the last run: scanned / created / deactivated / role_changes / errors
    last_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
