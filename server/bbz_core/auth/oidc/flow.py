"""The authorization-code + PKCE flow, split into its two round trips (E21-01).

``start`` builds the redirect to the IdP and returns the per-attempt secrets the
server must remember (``state`` / ``nonce`` / ``code_verifier``). ``exchange``
swaps the returned ``code`` for tokens at the token endpoint.
"""

from __future__ import annotations

import secrets
import urllib.parse
from dataclasses import dataclass
from typing import Any

from bbz_core.auth.oidc import pkce
from bbz_core.auth.oidc.config import OidcConfig, OidcMetadata
from bbz_core.auth.oidc.errors import OidcTokenError
from bbz_core.auth.oidc.http import OidcHttp


@dataclass(frozen=True)
class StartedFlow:
    authorization_url: str
    state: str
    nonce: str
    code_verifier: str


def start(cfg: OidcConfig, meta: OidcMetadata) -> StartedFlow:
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = pkce.new_verifier()
    params = {
        "response_type": "code",  # never a token/implicit grant
        "client_id": cfg.client_id,
        "redirect_uri": cfg.redirect_uri,
        "scope": cfg.scope_param,
        "state": state,
        "nonce": nonce,
        "code_challenge": pkce.challenge(verifier),
        "code_challenge_method": pkce.CHALLENGE_METHOD,
    }
    url = f"{meta.authorization_endpoint}?{urllib.parse.urlencode(params)}"
    return StartedFlow(authorization_url=url, state=state, nonce=nonce, code_verifier=verifier)


@dataclass(frozen=True)
class TokenResponse:
    id_token: str
    access_token: str | None
    raw: dict[str, Any]


async def exchange(
    cfg: OidcConfig, meta: OidcMetadata, *, code: str, code_verifier: str, http: OidcHttp
) -> TokenResponse:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": cfg.redirect_uri,
        "client_id": cfg.client_id,
        "code_verifier": code_verifier,
    }
    if cfg.client_secret:
        data["client_secret"] = cfg.client_secret

    body = await http.post_form(meta.token_endpoint, data)
    if "error" in body:
        raise OidcTokenError(f"token endpoint error: {body.get('error')}")
    id_token = body.get("id_token")
    if not isinstance(id_token, str) or not id_token:
        raise OidcTokenError("token response has no id_token")
    access = body.get("access_token")
    return TokenResponse(
        id_token=id_token,
        access_token=access if isinstance(access, str) else None,
        raw=body,
    )
