"""Provider-event inbox (ADR-0011, .ai/TECHNICAL_TRIGGERS.md).

Every inbound external event (CTI, camera, door, weather …) is persisted here
and deduplicated **before** any trigger / rule evaluation, so a provider
reconnect that replays events, or both HA nodes seeing the same event, can
never cause double processing. ``dedupe_key`` is UNIQUE.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from typing import Any

from sqlalchemy import String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base, uuid_pk


class ProviderEventInbox(Base):
    __tablename__ = "provider_event_inbox"

    id: Mapped[uuid.UUID] = uuid_pk()
    provider: Mapped[str] = mapped_column(String(64), index=True)
    # The provider's own event id when it has a stable one; else null and the
    # dedupe_key is derived from documented fields (see infra/inbox.py).
    provider_event_id: Mapped[str | None] = mapped_column(String(200))
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True)
    # The raw payload is only referenced / hashed here, never used by rules.
    raw_ref: Mapped[str | None] = mapped_column(String(200))
    raw_hash: Mapped[str | None] = mapped_column(String(64))
    normalized: Mapped[dict[str, Any]] = mapped_column(JSONB)
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    received_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"), index=True)
    processed_at: Mapped[_dt.datetime | None] = mapped_column()
    note: Mapped[str | None] = mapped_column(Text)
