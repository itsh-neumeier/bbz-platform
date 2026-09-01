"""OIDC authorization-code + PKCE login (roadmap E21-01, MASTER_PROMPT §11).

Pure, framework-free building blocks: discovery, PKCE, the two-step flow, and
ID-token validation. The stateful orchestration (persisting the per-attempt
``state`` / ``nonce`` / ``code_verifier``, minting a BBZ session) is
``bbz_core.infra.repositories.oidc_login``; the endpoints live in
``bbz_core.api.v1.auth``.
"""

from __future__ import annotations

from bbz_core.auth.oidc.config import OidcConfig, OidcMetadata
from bbz_core.auth.oidc.discovery import fetch_jwks, fetch_metadata
from bbz_core.auth.oidc.errors import (
    OidcDiscoveryError,
    OidcError,
    OidcIdTokenInvalid,
    OidcNotConfigured,
    OidcStateError,
    OidcTokenError,
)
from bbz_core.auth.oidc.flow import StartedFlow, TokenResponse, exchange, start
from bbz_core.auth.oidc.http import OidcHttp, UrllibOidcHttp
from bbz_core.auth.oidc.idtoken import IdTokenClaims, validate_id_token

__all__ = [
    "IdTokenClaims",
    "OidcConfig",
    "OidcDiscoveryError",
    "OidcError",
    "OidcHttp",
    "OidcIdTokenInvalid",
    "OidcMetadata",
    "OidcNotConfigured",
    "OidcStateError",
    "OidcTokenError",
    "StartedFlow",
    "TokenResponse",
    "UrllibOidcHttp",
    "exchange",
    "fetch_jwks",
    "fetch_metadata",
    "start",
    "validate_id_token",
]
