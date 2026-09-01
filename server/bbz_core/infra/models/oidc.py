"""In-flight OIDC login attempts (roadmap E21-01).

One short-lived row per ``GET /auth/oidc/{provider}/start``. The callback looks
the row up by ``state``, uses the ``nonce`` + ``code_verifier``, then deletes it —
so a replayed callback finds nothing. ``code_verifier`` is Fernet-encrypted at
rest (it is a PKCE secret); the row is also purged by the E22 housekeeping job
once ``expires_at`` passes.

DB-backed (not in-memory) so a callback that lands on a different node after a
failover still resolves (HA note in the roadmap).
"""

from __future__ import annotations

import datetime as _dt

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base


class OidcLoginFlow(Base):
    __tablename__ = "oidc_login_flows"

    #: the ``state`` value sent to the IdP — unguessable, so it is the PK
    state: Mapped[str] = mapped_column(String(128), primary_key=True)
    provider: Mapped[str] = mapped_column(String(64))
    nonce: Mapped[str] = mapped_column(String(128))
    #: Fernet ciphertext of the PKCE code_verifier
    code_verifier_enc: Mapped[str] = mapped_column(Text)
    redirect_uri: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[_dt.datetime] = mapped_column()
    expires_at: Mapped[_dt.datetime] = mapped_column(index=True)
