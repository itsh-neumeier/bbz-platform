"""Admin-facing auth-provider display config (roadmap E21-08).

One row per provider (``local`` / ``entra_oidc`` / ``ldap_ad``). This governs
whether the SPA **offers** the provider for login / account linking and its
display label — it never enables auth that the deployment's env / secrets do not
already back (that stays an open external dependency). Absent row ⇒ the provider
is offered iff it is env-configured.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base, TimestampMixin


class AuthProviderConfig(Base, TimestampMixin):
    __tablename__ = "auth_provider_config"

    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    display_name: Mapped[str] = mapped_column(String(80), server_default=text("''"))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
