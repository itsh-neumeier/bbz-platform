"""CSRF enforcement for cookie-authenticated writes (E23-05).

Enforced as ASGI middleware rather than a per-route dependency, so the guarantee
is structural: *every* state-changing request under ``/api/v1`` that carries a
session cookie and no bearer token must present a valid, session-bound
double-submit CSRF token — and, when the browser sends one, an allowed
``Origin`` / ``Referer``. New write routes are covered the moment they are added;
``tests/test_csrf.py`` fails the build if one slips outside this net.

Exempt by design:

* **Bearer-token clients** (agents, integrations). A caller that authenticates
  with ``Authorization: Bearer`` has no ambient credential for a foreign page to
  ride on, so CSRF does not apply. Documented in ``docs/security/csrf.md``.
* **Pre-authentication writes** (:data:`CSRF_TOKEN_EXEMPT`). No session exists
  yet, so there is no token to present. They keep the Origin/Referer check;
  ``SameSite=Lax`` and a per-endpoint measure (login: nothing rides a login
  itself that Lax does not already block; OIDC callback: the single-use OAuth
  ``state``) are the backstop.
"""

from __future__ import annotations

import hmac
import json
import re
import uuid
from urllib.parse import urlsplit

from starlette.types import ASGIApp, Receive, Scope, Send

from bbz_core.api.deps import ACCESS_COOKIE
from bbz_core.auth.csrf import CSRF_COOKIE, CSRF_HEADER, SAFE_METHODS, csrf_token_valid
from bbz_core.auth.tokens import TokenError, decode_access_token
from bbz_core.logging import correlation_id, get_logger
from bbz_core.settings import get_settings

_log = get_logger(__name__)

PROTECTED_PREFIX = "/api/v1"

#: Route templates (as they appear in the OpenAPI schema) whose writes run
#: before a session is established, so no double-submit token can exist yet.
CSRF_TOKEN_EXEMPT: frozenset[str] = frozenset(
    {
        "/api/v1/auth/login",
        "/api/v1/auth/oidc/{provider}/callback",
    }
)

_EXEMPT_PATTERNS = tuple(
    re.compile("^" + re.sub(r"\{[^/]+\}", "[^/]+", tpl) + "$") for tpl in CSRF_TOKEN_EXEMPT
)

_MESSAGES = {
    "origin_not_allowed": "cross-origin request rejected",
    "csrf_token_missing": "missing CSRF token",
    "csrf_token_mismatch": "CSRF cookie and header differ",
    "csrf_token_invalid": "invalid CSRF token",
}


def is_token_exempt(path: str) -> bool:
    """True for a concrete path that matches a :data:`CSRF_TOKEN_EXEMPT` template."""
    return any(pat.match(path) for pat in _EXEMPT_PATTERNS)


def csrf_guards(method: str, path: str) -> bool:
    """Whether the middleware would require a CSRF token for this write.

    The contract test walks every ``/api/v1`` write operation and asserts this is
    ``True`` unless the operation is explicitly listed as bearer-only.
    """
    return (
        method.upper() not in SAFE_METHODS
        and path.startswith(PROTECTED_PREFIX)
        and not is_token_exempt(path)
    )


def _headers(scope: Scope) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw_key, raw_val in scope.get("headers", []):
        key = raw_key.decode("latin-1").lower()
        val = raw_val.decode("latin-1")
        out[key] = f"{out[key]}, {val}" if key in out else val
    return out


def _cookies(header_value: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for chunk in header_value.split(";"):
        name, sep, value = chunk.strip().partition("=")
        if sep and name and name not in out:
            out[name] = value
    return out


def _referer_origin(referer: str) -> str:
    if not referer:
        return ""
    parts = urlsplit(referer)
    if parts.scheme and parts.netloc:
        return f"{parts.scheme}://{parts.netloc}"
    return ""


def _origin_allowed(origin: str, headers: dict[str, str]) -> bool:
    settings = get_settings()
    if origin in settings.cors_allow_origins:
        return True
    parts = urlsplit(origin)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return False
    fwd_host = headers.get("x-forwarded-host", "").split(",")[0].strip()
    host = fwd_host or headers.get("host", "")
    return bool(host) and parts.netloc == host


def _session_id(access_token: str | None) -> uuid.UUID | None:
    if not access_token:
        return None
    try:
        return decode_access_token(access_token).session_id
    except TokenError:
        return None  # expired / invalid — signature-only check still applies


class CsrfMiddleware:
    """Reject unsafe cookie-authenticated requests that fail the CSRF checks."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        reason = self._reject_reason(scope)
        if reason is None:
            await self.app(scope, receive, send)
            return
        _log.warning("csrf_blocked", path=scope.get("path", ""), reason=reason)
        await self._forbidden(send, reason)

    def _reject_reason(self, scope: Scope) -> str | None:
        if scope.get("method", "GET").upper() in SAFE_METHODS:
            return None
        raw_path, root = scope.get("path", ""), scope.get("root_path", "")
        path = raw_path[len(root) :] if root and raw_path.startswith(root) else raw_path
        if not path.startswith(PROTECTED_PREFIX):
            return None
        if not get_settings().csrf_enabled:
            return None

        headers = _headers(scope)
        if headers.get("authorization", "").lower().startswith("bearer "):
            return None  # bearer clients are immune to CSRF by construction

        cookies = _cookies(headers.get("cookie", ""))
        if CSRF_COOKIE not in cookies and ACCESS_COOKIE not in cookies:
            return None  # not a browser session — the auth layer guards it

        origin = headers.get("origin") or _referer_origin(headers.get("referer", ""))
        if origin and not _origin_allowed(origin, headers):
            return "origin_not_allowed"

        if is_token_exempt(path):
            return None  # pre-auth: no token can exist; Origin was still checked

        header_token = headers.get(CSRF_HEADER, "")
        cookie_token = cookies.get(CSRF_COOKIE, "")
        if not header_token or not cookie_token:
            return "csrf_token_missing"
        if not hmac.compare_digest(header_token, cookie_token):
            return "csrf_token_mismatch"
        if not csrf_token_valid(header_token, session_id=_session_id(cookies.get(ACCESS_COOKIE))):
            return "csrf_token_invalid"
        return None

    async def _forbidden(self, send: Send, reason: str) -> None:
        cid = correlation_id.get()
        payload = {
            "error": {
                "code": "forbidden",
                "message": _MESSAGES.get(reason, "CSRF check failed"),
                "details": {"reason": reason},
                "correlation_id": cid,
            }
        }
        body = json.dumps(payload).encode("utf-8")
        headers = [(b"content-type", b"application/json")]
        if cid:
            headers.append((b"x-correlation-id", cid.encode("latin-1")))
        await send({"type": "http.response.start", "status": 403, "headers": headers})
        await send({"type": "http.response.body", "body": body})
