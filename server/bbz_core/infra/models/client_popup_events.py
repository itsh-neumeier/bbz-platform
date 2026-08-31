"""Client-popup events — bottom-right, time-limited operator popups (E15-03).

MASTER_PROMPT §34 / ``.ai/TECHNICAL_TRIGGERS.md`` ``show_client_popup``. A
trigger action (or a call/alarm flow) persists a popup **bound to one
``workplace_id``** with an ``expires_at``; the client for that workplace picks
it up, marks ``delivered_at``, and later ``dismissed_at``. Delivery / expiry
sweeping is E15-14.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from typing import Any

from sqlalchemy import String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base, TimestampMixin, uuid_pk


class ClientPopupEvent(Base, TimestampMixin):
    __tablename__ = "client_popup_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    #: the workplace this popup is for — a popup is never broadcast. No
    #: workplaces table yet (plain UUID, like ``events.workplace_id``).
    workplace_id: Mapped[uuid.UUID] = mapped_column(index=True)
    #: popup kind (``incoming_call`` / ``technical_alarm`` / …). The closed
    #: vocabulary is owned by the popup-delivery layer (E15-14).
    kind: Mapped[str] = mapped_column(String(32), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    #: hard expiry — a client must not show a popup past this
    expires_at: Mapped[_dt.datetime] = mapped_column()
    delivered_at: Mapped[_dt.datetime | None] = mapped_column()
    dismissed_at: Mapped[_dt.datetime | None] = mapped_column()
