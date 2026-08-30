"""BKU agent registration, enrollment and command history (roadmap E10-01).

MASTER_PROMPT §34, ``.ai/BKU_AGENT.md``. A ``bku-agent`` runs on a corporate BKU
workstation and is permanently bound to exactly one BBZ workplace. Schema only —
enrollment (E10-03) and the command bus (E10-04) come later.

Key rules encoded here:

* **one active agent per workplace** — a partial unique index on
  ``workplace_id`` where ``status = 'active'`` (a re-enroll revokes the old row
  and inserts a new one, E10-03);
* **enrollment tokens are only ever stored hashed** (``token_hash``), single-use
  (``used_at``) and time-boxed (``expires_at``);
* the agent command surface is a **closed set** (a CHECK constraint), never an
  arbitrary shell / URL / executable.
"""

from __future__ import annotations

import datetime as _dt
import enum
import uuid
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base, uuid_pk


class BkuAgentStatus(enum.StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


class BkuCommandType(enum.StrEnum):
    GET_STATUS = "get_status"
    GET_SESSION_STATE = "get_session_state"
    PING = "ping"
    LAUNCH_CATALOG_APP = "launch_catalog_app"
    FOCUS_CATALOG_APP = "focus_catalog_app"
    CLOSE_CATALOG_APP = "close_catalog_app"
    LOGOUT_INTERACTIVE_USER = "logout_interactive_user"
    RESTART_WORKSTATION = "restart_workstation"


class BkuCommandStatus(enum.StrEnum):
    PENDING = "pending"
    SENT = "sent"
    ACKED = "acked"
    DONE = "done"
    FAILED = "failed"
    EXPIRED = "expired"


def _enum_check(column: str, values: type[enum.StrEnum], name: str) -> CheckConstraint:
    allowed = ", ".join(f"'{v.value}'" for v in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=name)


class BkuAgent(Base):
    __tablename__ = "bku_agents"
    __table_args__ = (
        _enum_check("status", BkuAgentStatus, "bku_agent_status"),
        Index(
            "uq_bku_agents_one_active_per_workplace",
            "workplace_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    agent_id: Mapped[uuid.UUID] = uuid_pk()
    #: immutable binding to a BBZ workplace (plain UUID — no workplace entity yet)
    workplace_id: Mapped[uuid.UUID] = mapped_column(index=True)
    device_pubkey: Mapped[str] = mapped_column(Text)
    #: bumped on every (re-)enroll; commands may pin an expected generation
    generation: Mapped[int] = mapped_column(BigInteger, server_default=text("1"))
    status: Mapped[str] = mapped_column(String(16), server_default=BkuAgentStatus.ACTIVE.value)
    enrolled_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))
    last_seen_at: Mapped[_dt.datetime | None] = mapped_column()
    revoked_at: Mapped[_dt.datetime | None] = mapped_column()


class BkuAgentEnrollment(Base):
    __tablename__ = "bku_agent_enrollments"

    id: Mapped[uuid.UUID] = uuid_pk()
    #: SHA-256 of the one-time enrollment token — the token itself is never stored
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    workplace_id: Mapped[uuid.UUID] = mapped_column(index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))
    expires_at: Mapped[_dt.datetime] = mapped_column()
    #: set once, when the token is redeemed — a second redeem is rejected
    used_at: Mapped[_dt.datetime | None] = mapped_column()
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("bku_agents.agent_id", ondelete="SET NULL")
    )


class BkuAgentCommand(Base):
    __tablename__ = "bku_agent_commands"
    __table_args__ = (
        _enum_check("type", BkuCommandType, "bku_command_type"),
        _enum_check("status", BkuCommandStatus, "bku_command_status"),
    )

    command_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bku_agents.agent_id", ondelete="CASCADE"), index=True
    )
    workplace_id: Mapped[uuid.UUID] = mapped_column(index=True)
    type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    issued_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))
    expires_at: Mapped[_dt.datetime] = mapped_column()
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    #: pin the agent generation/session this command was issued for (E10-13)
    expected_generation: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), server_default=BkuCommandStatus.PENDING.value)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    completed_at: Mapped[_dt.datetime | None] = mapped_column()
