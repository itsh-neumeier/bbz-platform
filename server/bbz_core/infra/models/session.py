"""Server-side session registry (E02-05).

One row per interactive login. Access tokens are short-lived JWTs; the refresh
token is opaque and stored only as a SHA-256 hash. Logout / user-deactivation
set ``revoked_at`` so both application nodes stop honouring the session.
"""

from __future__ import annotations

import datetime as _dt
import uuid

from sqlalchemy import ForeignKey, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base, uuid_pk


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))
    last_used_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))
    expires_at: Mapped[_dt.datetime] = mapped_column()
    revoked_at: Mapped[_dt.datetime | None] = mapped_column(index=True)
    client_id: Mapped[str | None] = mapped_column(String(64))
    workplace_id: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))
    #: when this session's login satisfied a TOTP/recovery challenge (E21-05) —
    #: NULL if it never did. Read by the step-up dependency; a step-up bumps it.
    mfa_verified_at: Mapped[_dt.datetime | None] = mapped_column()
