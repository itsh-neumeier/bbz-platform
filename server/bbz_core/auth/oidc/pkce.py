"""PKCE (RFC 7636) — S256 only (roadmap E21-01, ``.ai/SECURITY.md`` "PKCE for OIDC").

The plain method is never used; the challenge method sent to the IdP is always
``S256``.
"""

from __future__ import annotations

import base64
import hashlib
import secrets

CHALLENGE_METHOD = "S256"


def new_verifier() -> str:
    """A fresh high-entropy code verifier (RFC 7636 section 4.1: 43-128 chars,
    unreserved). 64 random bytes -> 86 url-safe base64 chars."""
    return base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode("ascii")


def challenge(verifier: str) -> str:
    """``base64url(sha256(verifier))`` without padding (RFC 7636 §4.2)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
