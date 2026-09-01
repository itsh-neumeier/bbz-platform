"""WebAuthn / FIDO2 credentials + ceremony challenges (roadmap E21-06).

A credential belongs to a **local** auth identity (WebAuthn is a factor for
local accounts). ``webauthn_challenges`` holds the server-issued challenge
between the *options* call and the *verify* call — DB-backed so a ceremony that
starts on one node can finish on another (HA), single-use, TTL'd.
"""

from __future__ import annotations

import datetime as _dt
import uuid

from sqlalchemy import BigInteger, ForeignKey, LargeBinary, String, text
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base, TimestampMixin, uuid_pk


class WebauthnCredential(Base, TimestampMixin):
    __tablename__ = "webauthn_credentials"

    id: Mapped[uuid.UUID] = uuid_pk()
    auth_identity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("auth_identities.id", ondelete="CASCADE"), index=True
    )
    #: the raw credential id from the authenticator (unique across the RP)
    credential_id: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    public_key: Mapped[bytes] = mapped_column(LargeBinary)
    sign_count: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    #: comma-separated AuthenticatorTransport hints (usb / nfc / ble / internal / hybrid)
    transports: Mapped[str] = mapped_column(String(120), server_default=text("''"))
    #: authenticator model id (hex), for display / policy — not a secret
    aaguid: Mapped[str] = mapped_column(String(36), server_default=text("''"))
    #: user-chosen label
    name: Mapped[str] = mapped_column(String(80), server_default=text("''"))
    last_used_at: Mapped[_dt.datetime | None] = mapped_column()


class WebauthnChallenge(Base):
    __tablename__ = "webauthn_challenges"

    id: Mapped[uuid.UUID] = uuid_pk()
    #: 'register' or 'authenticate'
    kind: Mapped[str] = mapped_column(String(16))
    #: the local auth identity (register) or the user (authenticate); nullable so
    #: a username-less flow could be added later
    auth_identity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("auth_identities.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    challenge: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))
    expires_at: Mapped[_dt.datetime] = mapped_column()
