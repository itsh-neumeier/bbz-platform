"""Centrally managed operational web-app / link catalog (roadmap E10-02).

MASTER_PROMPT §28.2, ``.ai/BKU_AGENT.md`` ("Application / Link Catalog"). The
catalog is the **allow-list**: the BKU agent may only ever launch a URL that
appears here (E10-07/E10-12). Schema only — the admin API is E10-10, the consume
API E10-11.

* ``url`` must be ``http``/``https`` (a CHECK constraint — no ``javascript:``,
  ``file:``, shell, …);
* ``launch_mode`` is a closed CHECK set (``window`` / ``app_window`` / ``tab``);
* ``application_catalog_scopes`` rows are **optional** — an app with none is
  visible everywhere; a row narrows it to a role and/or a BBZ/workplace.
"""

from __future__ import annotations

import datetime as _dt
import enum
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base, TimestampMixin, uuid_pk


class LaunchMode(enum.StrEnum):
    WINDOW = "window"
    APP_WINDOW = "app_window"
    TAB = "tab"


_LAUNCH_MODES = ", ".join(f"'{m.value}'" for m in LaunchMode)


class ApplicationCatalogEntry(Base, TimestampMixin):
    __tablename__ = "application_catalog"
    __table_args__ = (
        CheckConstraint("url ~* '^https?://'", name="application_catalog_url_scheme"),
        CheckConstraint(
            f"launch_mode IN ({_LAUNCH_MODES})", name="application_catalog_launch_mode"
        ),
    )

    app_id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    #: an icon name or a data/https URL — rendered by the client
    icon: Mapped[str | None] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(Text)
    #: named Chrome profile to open the app in (operating concept, E10-07)
    browser_profile: Mapped[str | None] = mapped_column(String(100))
    launch_mode: Mapped[str] = mapped_column(String(16), server_default=LaunchMode.WINDOW.value)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    #: optimistic-concurrency / change counter (bumped by the admin API on edit)
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    #: which workplace monitor the client should prefer (hint only, E19)
    target_monitor_hint: Mapped[str | None] = mapped_column(String(64))


class ApplicationCatalogScope(Base):
    __tablename__ = "application_catalog_scopes"

    id: Mapped[uuid.UUID] = uuid_pk()
    app_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("application_catalog.app_id", ondelete="CASCADE"), index=True
    )
    #: narrow to a role (``roles.key``); ``NULL`` = any role
    role_key: Mapped[str | None] = mapped_column(String(64))
    #: narrow to a BBZ / workplace (plain UUIDs — scope entities land in E23)
    bbz_id: Mapped[uuid.UUID | None] = mapped_column()
    workplace_id: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))
