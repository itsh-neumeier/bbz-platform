"""OIDC failure taxonomy (roadmap E21-01).

Every failure the login flow can hit is one of these, so the API can map it to a
precise status without leaking detail to the browser.
"""

from __future__ import annotations


class OidcError(Exception):
    """Base: any OIDC discovery / token / validation failure."""


class OidcDiscoveryError(OidcError):
    """The IdP's discovery document or JWKS could not be fetched or is malformed."""


class OidcTokenError(OidcError):
    """The token endpoint rejected the code exchange or returned an unusable body."""


class OidcIdTokenInvalid(OidcError):
    """The ID token failed signature / issuer / audience / expiry / nonce checks."""


class OidcStateError(OidcError):
    """The ``state`` on the callback is unknown, already used, or expired — a
    replayed or forged callback."""


class OidcNotConfigured(OidcError):
    """No OIDC configuration for the requested provider name."""
