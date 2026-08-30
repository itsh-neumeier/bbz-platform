"""Two-step reactivation confirm token (roadmap E20-05).

Reactivating an archived event is a two-request flow: the client first asks for a
short-lived, single-purpose token (``POST /events/{id}/reactivation-intent``) and
then presents it on the actual ``POST /events/{id}/reactivate``. The token is a
**stateless** HMAC over ``(event_id, user_id, version, expiry)`` keyed with the
app secret, so it needs no table and survives failover. It is bound to the
event's current ``version`` — any other change to the event invalidates it.
"""

from __future__ import annotations

import base64
import hmac
import time
import uuid
from hashlib import sha256

from bbz_core.settings import get_settings

_CONTEXT = b"bbz-reactivation-confirm-v1"


class ReactivationTokenError(ValueError):
    """The confirm token is missing, malformed, expired, or does not match."""


def _key() -> bytes:
    return sha256(_CONTEXT + get_settings().jwt_secret.encode("utf-8")).digest()


def _payload(event_id: uuid.UUID, user_id: uuid.UUID, version: int, expiry: int) -> bytes:
    return f"{event_id}|{user_id}|{version}|{expiry}".encode()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def mint_token(
    event_id: uuid.UUID, user_id: uuid.UUID, version: int, *, now: float | None = None
) -> tuple[str, int]:
    """Return ``(token, expiry_epoch_seconds)`` for this exact event version."""
    ttl = get_settings().reactivation_token_ttl_seconds
    expiry = int((now if now is not None else time.time()) + ttl)
    body = _payload(event_id, user_id, version, expiry)
    sig = hmac.new(_key(), body, sha256).digest()
    return f"{_b64(body)}.{_b64(sig)}", expiry


def verify_token(
    token: str,
    event_id: uuid.UUID,
    user_id: uuid.UUID,
    version: int,
    *,
    now: float | None = None,
) -> None:
    """Raise :class:`ReactivationTokenError` unless ``token`` was minted for this
    exact ``(event_id, user_id, version)`` and has not expired."""
    if not token or token.count(".") != 1:
        raise ReactivationTokenError("malformed reactivation token")
    body_b64, sig_b64 = token.split(".", 1)
    try:
        body = base64.urlsafe_b64decode(body_b64 + "=" * (-len(body_b64) % 4))
        got_sig = base64.urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
    except (ValueError, TypeError) as exc:
        raise ReactivationTokenError("malformed reactivation token") from exc

    want_sig = hmac.new(_key(), body, sha256).digest()
    if not hmac.compare_digest(got_sig, want_sig):
        raise ReactivationTokenError("reactivation token signature mismatch")

    expected = _payload(event_id, user_id, version, 0).rsplit(b"|", 1)[0]
    if not body.startswith(expected + b"|"):
        raise ReactivationTokenError("reactivation token does not match this request")

    try:
        expiry = int(body.rsplit(b"|", 1)[1])
    except ValueError as exc:
        raise ReactivationTokenError("malformed reactivation token") from exc
    if (now if now is not None else time.time()) >= expiry:
        raise ReactivationTokenError("reactivation token has expired")
