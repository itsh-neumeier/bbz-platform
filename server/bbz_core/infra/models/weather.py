"""Persisted DWD weather data (roadmap E18-05).

The weather refresh singleton (E18-06) upserts normalized DWD warnings and
station observations here; the read API (E18-07) and "create a BBZ event from a
warning" (E18-08) read them. A row is a *snapshot* of DWD's published state, not
an authoritative BBZ record — everything here can be re-fetched.

MASTER_PROMPT §14. All timestamps are ``timestamptz`` (ADR-0017: store/transmit
UTC). Normalisation of the raw DWD payloads (CAP XML / POI CSV) is ADR-0026 /
E18-02 / E18-04.
"""

from __future__ import annotations

import datetime as _dt
import uuid

from sqlalchemy import Float, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base, TimestampMixin, uuid_pk


class WeatherAlert(Base, TimestampMixin):
    """One normalized DWD warning for one warncell / region.

    A single CAP alert can cover several warncells → one row per (source_ref,
    region). Upserted on that key by the refresh worker; superseded rows are
    deleted when DWD drops them.
    """

    __tablename__ = "weather_alerts"
    __table_args__ = (
        UniqueConstraint("source_ref", "region", name="uq_weather_alerts_source_region"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    #: the configured place / warncell label this alert applies to
    region: Mapped[str] = mapped_column(String(120), index=True)
    #: DWD event type, e.g. "Sturmböen", "Gewitter" (verbatim from DWD)
    type: Mapped[str] = mapped_column(String(120))
    #: DWD warning level — normalised value convention owned by E18-02
    level: Mapped[str] = mapped_column(String(32))
    valid_from: Mapped[_dt.datetime | None] = mapped_column()
    valid_to: Mapped[_dt.datetime | None] = mapped_column()
    headline: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    #: the DWD identifier (CAP ``identifier``) — stable across refreshes, used to
    #: dedupe and to link a created BBZ event back to its warning (E18-08)
    source_ref: Mapped[str] = mapped_column(String(200), index=True)
    #: when this snapshot was fetched from DWD
    received_at: Mapped[_dt.datetime] = mapped_column()


class WeatherObservation(Base, TimestampMixin):
    """One normalized DWD station measurement for one place + metric + time."""

    __tablename__ = "weather_observations"
    __table_args__ = (
        UniqueConstraint(
            "place", "metric", "observed_at", name="uq_weather_observations_place_metric_time"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    #: the configured place name
    place: Mapped[str] = mapped_column(String(120), index=True)
    #: "temperature" / "wind_speed" / "precipitation" / … (E18-04 vocabulary)
    metric: Mapped[str] = mapped_column(String(32))
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16))
    observed_at: Mapped[_dt.datetime] = mapped_column()
    #: the DWD POI station id this value came from
    station_ref: Mapped[str] = mapped_column(String(64))
