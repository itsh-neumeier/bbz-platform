"""Weather refresh bookkeeping (roadmap E18-06).

One row per weather data kind (``warnings`` / ``radar`` / ``observations``): when
it was last polled from DWD, whether that succeeded, and the last error. The
refresh singleton writes it; the weather health status (`ok` / `stale` /
`degraded` / `down`) is computed from ``last_success_at`` vs the configured TTL
plus ``last_error``. Survives restarts and is the same on every node.
"""

from __future__ import annotations

import datetime as _dt

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base, TimestampMixin

#: the weather data kinds the refresh singleton tracks
WEATHER_DATA_KINDS: tuple[str, ...] = ("warnings", "radar", "observations")


class WeatherRefreshState(Base, TimestampMixin):
    __tablename__ = "weather_refresh_state"

    data_kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    last_attempt_at: Mapped[_dt.datetime | None] = mapped_column()
    last_success_at: Mapped[_dt.datetime | None] = mapped_column()
    #: item count of the last successful refresh (alerts / frames / observations)
    last_item_count: Mapped[int | None] = mapped_column(Integer)
    #: last failure message (redaction net applies — never a secret)
    last_error: Mapped[str | None] = mapped_column(Text)
