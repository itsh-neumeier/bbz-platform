"""Short-lived access tokens (signed JWT) and opaque refresh tokens.

Access tokens are stateless JWTs (HS256, secret from ``BBZ_JWT_SECRET``).
Refresh tokens are opaque random strings; only their SHA-256 hash is stored
(see :mod:`bbz_core.auth.sessions`).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import secrets
import uuid
from dataclasses import dataclass

import jwt

from bbz_core.settings import get_settings

_ALG = "HS256"


class TokenError(Exception):
    """Access token missing, malformed, expired or wrong type."""


@dataclass(frozen=True)
class AccessClaims:
    user_id: uuid.UUID
    session_id: uuid.UUID


def issue_access_token(user_id: uuid.UUID, session_id: uuid.UUID) -> str:
    s = get_settings()
    now = _dt.datetime.now(_dt.UTC)
    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "typ": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + _dt.timedelta(seconds=s.access_token_ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=_ALG)


def decode_access_token(token: str) -> AccessClaims:
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[_ALG])
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    if payload.get("typ") != "access":
        raise TokenError("not an access token")
    try:
        return AccessClaims(uuid.UUID(payload["sub"]), uuid.UUID(payload["sid"]))
    except (KeyError, ValueError) as exc:
        raise TokenError("malformed claims") from exc


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
