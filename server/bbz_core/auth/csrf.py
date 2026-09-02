"""Session-bound CSRF tokens for the cookie auth flow (E23-05).

The web / kiosk clients authenticate with an ``HttpOnly`` access cookie, so a
cross-site page could otherwise drive state-changing requests with the victim's
ambient credentials. Defence is layered:

1. ``SameSite=Lax`` on every session cookie — the browser withholds them on a
   cross-site POST/PUT/PATCH/DELETE, so the classic form-CSRF never authenticates.
2. A **double-submit** token: a readable ``bbz_csrf`` cookie whose value the SPA
   echoes in the ``X-CSRF-Token`` header. A cross-origin attacker can neither
   read the cookie nor set the custom header (CORS forbids it).
3. **Binding**: the token is ``HMAC(jwt_secret, session_id)``, so a value planted
   by a same-site cookie-injection attacker, or lifted from another session,
   fails verification.

This module is pure (no FastAPI); :mod:`bbz_core.api.csrf` enforces it.
"""

from __future__ import annotations

import base64
import hmac
import uuid
from hashlib import sha256

from bbz_core.settings import get_settings

CSRF_COOKIE = "bbz_csrf"
CSRF_HEADER = "x-csrf-token"

#: Methods that never change state — always allowed through without a token.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(session_id: uuid.UUID) -> bytes:
    key = get_settings().jwt_secret.encode("utf-8")
    return hmac.new(key, session_id.bytes, sha256).digest()


def issue_csrf_token(session_id: uuid.UUID) -> str:
    """Mint a CSRF token bound to ``session_id``: ``<b64 sid>.<b64 HMAC>``."""
    return f"{_b64(session_id.bytes)}.{_b64(_sign(session_id))}"


def csrf_token_valid(token: str, *, session_id: uuid.UUID | None = None) -> bool:
    """Is ``token`` a well-formed, correctly-signed CSRF token?

    With ``session_id`` the embedded id must match it too (full binding). Without
    it — e.g. on ``/auth/refresh``, where the access token has expired and the
    session id is not yet known — only the signature is verified, which still
    proves the token was minted by this server.
    """
    try:
        sid_part, sig_part = token.split(".", 1)
        sid = uuid.UUID(bytes=_unb64(sid_part))
        signature = _unb64(sig_part)
    except (ValueError, TypeError):
        return False
    if not hmac.compare_digest(signature, _sign(sid)):
        return False
    return session_id is None or sid == session_id
