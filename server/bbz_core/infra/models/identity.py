"""Identity tables: users, external/local auth identities, and presence.

MASTER_PROMPT §11/§14, roadmap E02-01. No behaviour here - schema only.
Credential material is never stored inline: ``AuthIdentity.credential_ref``
points at a credential row / secret-store key created by later issues
(local password hash E02-03, TOTP E02-13, OIDC/LDAP Epic 21).

Enumerated columns are ``VARCHAR`` + a named ``CHECK`` (not a native PG enum):
adding a value is a plain migration, and Alembic autogenerate round-trips
cleanly. The Python ``StrEnum`` classes are the allow-list the service layer
validates against.
"""

from __future__ import annotations

import datetime as _dt
import enum
import uuid

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bbz_core.infra.models.base import Base, TimestampMixin, uuid_pk


class UserStatus(enum.StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class AuthProvider(enum.StrEnum):
    LOCAL = "local"
    ENTRA_OIDC = "entra_oidc"
    LDAP_AD = "ldap_ad"


class PresenceState(enum.StrEnum):
    AVAILABLE = "available"
    PAUSE = "pause"
    OFFLINE = "offline"


def _in_check(column: str, values: type[enum.StrEnum], name: str) -> CheckConstraint:
    allowed = ", ".join(f"'{v.value}'" for v in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=name)


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (_in_check("status", UserStatus, "user_status"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    display_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), server_default=UserStatus.ACTIVE.value)
    # Stable external reference (e.g. personnel id) for correlation/import; not an
    # auth identity - those live in ``auth_identities``.
    external_ref: Mapped[str | None] = mapped_column(String(255))

    identities: Mapped[list[AuthIdentity]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    presence: Mapped[UserPresence | None] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
        foreign_keys="UserPresence.user_id",
    )


class AuthIdentity(Base, TimestampMixin):
    __tablename__ = "auth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "subject"),
        _in_check("provider", AuthProvider, "auth_provider"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(16))
    # Provider-specific subject: username for ``local``, ``sub`` claim for OIDC,
    # distinguished name / objectGUID for LDAP.
    subject: Mapped[str] = mapped_column(String(255))
    # Opaque reference to credential material (hash row id, secret-store key).
    credential_ref: Mapped[str | None] = mapped_column(String(255))

    user: Mapped[User] = relationship(back_populates="identities")


class UserPresence(Base):
    __tablename__ = "user_presence"
    __table_args__ = (_in_check("state", PresenceState, "presence_state"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    state: Mapped[str] = mapped_column(String(16), server_default=PresenceState.OFFLINE.value)
    changed_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    user: Mapped[User] = relationship(back_populates="presence", foreign_keys=[user_id])


class LocalCredential(Base, TimestampMixin):
    """Password material for a ``provider='local'`` auth identity (E02-03).

    One row per local identity. Lockout counters live here so both application
    nodes share the same state.
    """

    __tablename__ = "local_credentials"

    auth_identity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("auth_identities.id", ondelete="CASCADE"), primary_key=True
    )
    password_hash: Mapped[str] = mapped_column(Text)
    must_change: Mapped[bool] = mapped_column(server_default=text("false"))
    failed_attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    locked_until: Mapped[_dt.datetime | None] = mapped_column()
    password_changed_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))


class LocalTotp(Base):
    """Optional second factor for a local identity (E02-13). Secret encrypted."""

    __tablename__ = "local_totp"

    auth_identity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("auth_identities.id", ondelete="CASCADE"), primary_key=True
    )
    secret_ciphertext: Mapped[str] = mapped_column(Text)
    activated: Mapped[bool] = mapped_column(server_default=text("false"))
    last_step: Mapped[int | None] = mapped_column(BigInteger)
    enrolled_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))


class LocalTotpRecoveryCode(Base):
    __tablename__ = "local_totp_recovery_codes"
    __table_args__ = (UniqueConstraint("auth_identity_id", "code_hash"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    auth_identity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("auth_identities.id", ondelete="CASCADE"), index=True
    )
    code_hash: Mapped[str] = mapped_column(String(64))
    used_at: Mapped[_dt.datetime | None] = mapped_column()
