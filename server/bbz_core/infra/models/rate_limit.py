"""Cluster-wide rate-limit counter (roadmap E23-04).

Fixed window: one row per ``(bucket, window_start)``, ``count`` incremented on
each hit via an upsert. Both app nodes write the same rows, so a threshold is
enforced across the cluster. ``expires_at`` lets the retention worker prune.
"""

from __future__ import annotations

import datetime as _dt

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base


class RateLimitHit(Base):
    __tablename__ = "rate_limit_hits"

    bucket: Mapped[str] = mapped_column(String(160), primary_key=True)
    window_start: Mapped[_dt.datetime] = mapped_column(primary_key=True)
    count: Mapped[int] = mapped_column(Integer, server_default="0")
    expires_at: Mapped[_dt.datetime] = mapped_column(index=True)
