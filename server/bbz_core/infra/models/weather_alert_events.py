"""Link: a BBZ event created from a DWD weather warning (roadmap E18-08).

An operator turns a warning into a BBZ event on the Wetterlage page. This is the
queryable link back — one row per created event (``event_id`` unique; an event
comes from at most one warning), many events may reference the same alert. The
operator's assessment text is kept here alongside the event's own description.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base, TimestampMixin, uuid_pk


class WeatherAlertEvent(Base, TimestampMixin):
    __tablename__ = "weather_alert_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    #: nullable + SET NULL — a later refresh may drop the alert row; the link and
    #: its ``source_ref`` survive as the durable trace
    weather_alert_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("weather_alerts.id", ondelete="SET NULL"), index=True
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), unique=True
    )
    #: the DWD identifier the alert carried when the event was made
    source_ref: Mapped[str] = mapped_column(Text)
    #: the operator's operational assessment ("betriebliche Bewertung")
    assessment: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
