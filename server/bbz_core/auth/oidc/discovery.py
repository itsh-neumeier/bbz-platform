"""OIDC discovery (roadmap E21-01).

Fetches ``<issuer>/.well-known/openid-configuration`` and checks that the
document's ``issuer`` is exactly the one we configured — a mismatch means we are
talking to the wrong IdP.
"""

from __future__ import annotations

from typing import Any

from bbz_core.auth.oidc.config import OidcConfig, OidcMetadata
from bbz_core.auth.oidc.errors import OidcDiscoveryError
from bbz_core.auth.oidc.http import OidcHttp

_REQUIRED = ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri")


async def fetch_metadata(cfg: OidcConfig, http: OidcHttp) -> OidcMetadata:
    doc = await http.get_json(cfg.well_known)
    for key in _REQUIRED:
        if not isinstance(doc.get(key), str) or not doc[key]:
            raise OidcDiscoveryError(f"discovery document missing {key!r}")
    if doc["issuer"].rstrip("/") != cfg.issuer.rstrip("/"):
        raise OidcDiscoveryError(
            f"discovery issuer {doc['issuer']!r} != configured issuer {cfg.issuer!r}"
        )
    algs = doc.get("id_token_signing_alg_values_supported")
    return OidcMetadata(
        issuer=doc["issuer"],
        authorization_endpoint=doc["authorization_endpoint"],
        token_endpoint=doc["token_endpoint"],
        jwks_uri=doc["jwks_uri"],
        id_token_signing_alg_values_supported=(
            tuple(a for a in algs if isinstance(a, str)) if isinstance(algs, list) else ()
        ),
    )


async def fetch_jwks(meta: OidcMetadata, http: OidcHttp) -> list[dict[str, Any]]:
    doc = await http.get_json(meta.jwks_uri)
    keys = doc.get("keys")
    if not isinstance(keys, list) or not keys:
        raise OidcDiscoveryError("JWKS document has no keys")
    return [k for k in keys if isinstance(k, dict)]
