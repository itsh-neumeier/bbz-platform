"""SIP gateway connection config (roadmap E13-07, ADR-0033).

The ``telephony_sip`` provider's Asterisk/ARI connection lives in the DB and is
managed from the admin UI. The ARI **password** is a secret: stored only as
``ari_password_ciphertext`` (Fernet, key ``BBZ_SIP_ENCRYPTION_KEY`` via
:mod:`bbz_core.infra.sip_secrets`), entered only in a ``PUT`` body over TLS,
never returned by ``GET``, logged, or put in an audit row. The audit records a
redacted non-secret before/after diff and this row's id.

One row per adapter instance (``instance_id``, ``"sip"`` today); ``sip_lines``
maps BBZ line ids to Asterisk endpoints for that gateway.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base, TimestampMixin

#: the only gateway kind today (ADR-0023). FreeSWITCH/ESL stays a documented
#: fallback in the config schema, not a DB option yet.
SIP_GATEWAY_KINDS: tuple[str, ...] = ("asterisk_ari",)

#: how the resolved DTMF sequence goes on the wire — passed to Asterisk, not
#: branched in the adapter (ADR-0023).
SIP_DTMF_TRANSPORTS: tuple[str, ...] = ("rfc2833", "sip_info")


class SipGateway(Base, TimestampMixin):
    __tablename__ = "sip_gateway"

    #: the adapter instance this config drives (== ``SipTelephonyProvider.instance_id``)
    instance_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, server_default=text("'sip'")
    )
    kind: Mapped[str] = mapped_column(String(32), server_default=text("'asterisk_ari'"))
    host: Mapped[str] = mapped_column(String(255), server_default=text("''"))
    port: Mapped[int] = mapped_column(Integer, server_default=text("8088"))
    tls: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    #: the Stasis application the Asterisk dialplan hands calls to
    app_name: Mapped[str] = mapped_column(String(80), server_default=text("'bbz-sip'"))
    dtmf_transport: Mapped[str] = mapped_column(String(16), server_default=text("'rfc2833'"))
    ari_username: Mapped[str] = mapped_column(String(120), server_default=text("''"))
    #: Fernet ciphertext of the ARI password — opaque without the key; "" = unset
    ari_password_ciphertext: Mapped[str] = mapped_column(Text, server_default=text("''"))
    #: master switch — a disabled gateway builds no ARI client (provider stays inert)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class SipLine(Base, TimestampMixin):
    __tablename__ = "sip_lines"

    #: the logical BBZ line id (unique — one endpoint per line)
    bbz_line_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    gateway_instance_id: Mapped[str] = mapped_column(
        ForeignKey("sip_gateway.instance_id", ondelete="CASCADE"),
        server_default=text("'sip'"),
    )
    #: the Asterisk endpoint, e.g. ``PJSIP/1001`` (default is ``PJSIP/<bbz_line_id>``)
    asterisk_endpoint: Mapped[str] = mapped_column(String(255))
    label: Mapped[str] = mapped_column(String(120), server_default=text("''"))
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
