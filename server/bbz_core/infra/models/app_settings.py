"""Runtime app settings — the DB overlay over the env-based ``Settings`` (ADR-0031).

One row per **overridden** key. No row ⇒ the value comes from the environment or
the code default (see :mod:`bbz_core.settings_catalog` /
:class:`bbz_core.infra.repositories.settings_store.SettingsStore`). Written only
by the admin settings API; every change is a ``SETTING_CHANGED`` audit row.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_at: Mapped[_dt.datetime] = mapped_column(
        server_default=text("now()"), onupdate=text("now()")
    )
