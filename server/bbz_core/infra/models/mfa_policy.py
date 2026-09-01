"""MFA policy: which roles require a second factor (roadmap E21-05).

A user "requires MFA" iff they hold at least one role (direct or via a group)
that has a row here. ``grace_period_days`` gives a newly-assigned user time to
enrol before login is blocked (0 = enforce immediately).
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base, TimestampMixin


class MfaPolicy(Base, TimestampMixin):
    __tablename__ = "mfa_policies"

    role_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    grace_period_days: Mapped[int] = mapped_column(Integer, server_default=text("7"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
