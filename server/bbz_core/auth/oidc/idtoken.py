"""ID-token validation (roadmap E21-01, ``.ai/SECURITY.md``).

The signature is verified against the IdP's JWKS (the key whose ``kid`` matches
the token header). Only asymmetric RS/ES/PS algorithms are accepted — ``none``
and HMAC are rejected outright. ``iss`` / ``aud`` / ``exp`` / ``iat`` are checked
by PyJWT; ``nonce`` is then compared in constant time to the value we stored when
the flow started.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import jwt

from bbz_core.auth.oidc.config import OidcConfig, OidcMetadata
from bbz_core.auth.oidc.errors import OidcIdTokenInvalid

#: asymmetric signatures only — never "none", never HMAC (a shared-secret alg
#: would let anyone who knows the client_secret forge a token)
_ALLOWED_ALGS = ("RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "PS256", "PS384", "PS512")

_LEEWAY_SECONDS = 60


@dataclass(frozen=True)
class IdTokenClaims:
    subject: str
    issuer: str
    email: str | None
    email_verified: bool
    name: str | None
    preferred_username: str | None
    groups: tuple[str, ...]
    raw: dict[str, Any]


def validate_id_token(
    id_token: str,
    *,
    cfg: OidcConfig,
    meta: OidcMetadata,
    jwks: list[dict[str, Any]],
    nonce: str,
    now: datetime | None = None,
) -> IdTokenClaims:
    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError as exc:
        raise OidcIdTokenInvalid(f"unreadable token header: {exc}") from exc

    alg = header.get("alg")
    if alg not in _ALLOWED_ALGS:
        raise OidcIdTokenInvalid(f"disallowed id_token alg {alg!r}")
    key = _select_key(jwks, kid=header.get("kid"), alg=alg)

    try:
        claims = jwt.decode(
            id_token,
            key=key,
            algorithms=[alg],
            audience=cfg.client_id,
            issuer=meta.issuer,
            leeway=_LEEWAY_SECONDS,
            options={"require": ["exp", "iat", "aud", "iss", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise OidcIdTokenInvalid(str(exc)) from exc

    token_nonce = claims.get("nonce")
    if not isinstance(token_nonce, str) or not hmac.compare_digest(token_nonce, nonce):
        raise OidcIdTokenInvalid("id_token nonce mismatch")

    if now is not None:  # extra explicit expiry check for tests / clock-skew audits
        exp = claims.get("exp")
        if isinstance(exp, int | float) and now.timestamp() - _LEEWAY_SECONDS > exp:
            raise OidcIdTokenInvalid("id_token expired")

    sub = claims["sub"]
    groups = claims.get("groups") or claims.get("roles") or ()
    return IdTokenClaims(
        subject=str(sub),
        issuer=str(claims["iss"]),
        email=_str_or_none(claims.get("email")),
        email_verified=bool(claims.get("email_verified")),
        name=_str_or_none(claims.get("name")),
        preferred_username=_str_or_none(claims.get("preferred_username")),
        groups=tuple(str(g) for g in groups) if isinstance(groups, list) else (),
        raw=claims,
    )


def _select_key(jwks: list[dict[str, Any]], *, kid: str | None, alg: str) -> Any:
    candidates = [k for k in jwks if k.get("use") in (None, "sig")]
    if kid is not None:
        candidates = [k for k in candidates if k.get("kid") == kid] or candidates
    for jwk in candidates:
        try:
            return jwt.PyJWK.from_dict(jwk).key
        except (jwt.PyJWTError, KeyError, ValueError, TypeError):
            continue
    raise OidcIdTokenInvalid(f"no usable JWKS key for kid={kid!r} alg={alg}")


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
