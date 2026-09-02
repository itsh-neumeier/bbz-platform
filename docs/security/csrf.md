# CSRF protection

Roadmap **E23-05**, MASTER_PROMPT §22. `bbz_core.api.csrf` + `bbz_core.auth.csrf`.

This is the review report the acceptance criteria ask for: every state-changing
`/api/v1` endpoint, and how it is protected against cross-site request forgery.

## Threat model

The web / kiosk clients authenticate with an **`HttpOnly` access cookie**
(`bbz_access`). A page on another origin can make the browser send that cookie
on a request to the BBZ API, so without a countermeasure it could drive writes
with the victim's session. Bearer-token clients (agents, integrations) send an
explicit `Authorization` header that no foreign page can set — they are not
exposed to CSRF and are out of scope.

## The layers

| # | Layer | Where |
|---|---|---|
| 1 | **`SameSite=Lax`** on `bbz_access` / `bbz_refresh` / `bbz_csrf` | `auth._set_cookie` |
| 2 | **Double-submit token**, session-bound | `CsrfMiddleware` + `issue_csrf_token` |
| 3 | **Origin / Referer allow-list** | `CsrfMiddleware` |

### 1. SameSite=Lax

The browser does **not** attach a `Lax` cookie to a cross-site `POST` / `PUT` /
`PATCH` / `DELETE`, so the classic form-CSRF never even authenticates — it
arrives as an anonymous request and gets `401`. `Lax` (not `Strict`) because the
OIDC login flow returns to the SPA via a top-level cross-site navigation that
must carry the session. `Lax` does **not** cover a same-site attacker (a
malicious sibling app, an HTML-injection on our own origin) or Chrome's
2-minute "Lax-allowing-unsafe" window — hence layers 2 and 3.

### 2. Session-bound double-submit token

On login the server issues `bbz_csrf`, a **non-`HttpOnly`** cookie the SPA reads
and echoes in the `X-CSRF-Token` header on every unsafe request. `CsrfMiddleware`
requires:

* the header and the cookie are both present and **equal** (a cross-origin
  attacker can neither read the cookie nor set the custom header — CORS forbids
  it), and
* the token is **valid for this session**. The token is
  `base64url(session_id) . base64url(HMAC-SHA256(jwt_secret, session_id))`, so a
  value planted by a same-site cookie-injection attacker fails the HMAC check,
  and a token lifted from a different session fails the binding check.

On `POST /api/v1/auth/refresh` the access cookie may already be expired, so the
session id isn't available; the signature alone is still verified (it proves the
token was minted by this server) and the cookie is re-issued.

Rotating `BBZ_JWT_SECRET` (ADR-0019) invalidates outstanding CSRF tokens along
with access tokens — clients re-authenticate.

### 3. Origin / Referer

For a cookie-authenticated write, if the request carries an `Origin` (or, failing
that, a `Referer`), its origin must be in `cors_allow_origins` **or** equal the
request's own host. A mismatch is rejected before the token is even checked. A
request with neither header is allowed through to the token check — some proxies
strip them, and the token is the primary control.

## What is enforced where

`CsrfMiddleware` runs for **every** `POST` / `PUT` / `PATCH` / `DELETE` under
`/api/v1`. It acts only when a session cookie (`bbz_csrf` or `bbz_access`) is
present and there is no `Authorization: Bearer` header. `tests/test_csrf.py`
walks the OpenAPI schema and fails the build if a write route escapes this net.

| Category | Count | Origin check | Double-submit token | Endpoints |
|---|---|---|---|---|
| **Standard cookie write** | 108 | yes | yes | events, calls, contacts, doors, monitor, rbac, users, workflows, trigger-rules, technical-endpoints, weather, system, `/auth/*` (refresh, logout, totp, webauthn, mfa-policies, identities, providers, group-mappings, directory-sync) … |
| **Pre-authentication** (`CSRF_TOKEN_EXEMPT`) | 2 | yes | n/a — no session yet | `POST /api/v1/auth/login`, `POST /api/v1/auth/oidc/{provider}/callback` |
| **Bearer / machine only** | 1 | n/a | n/a | `POST /api/v1/telephony/events` (inbound provider webhook — a service-account bearer token; documented exemption in `tests/test_csrf.py::_BEARER_ONLY`) |

Pre-authentication endpoints cannot present a token (the caller has no session).
They keep the Origin check; `SameSite=Lax` blocks the cross-site POST; and the
OIDC callback additionally validates the server-issued single-use OAuth `state`.

Non-`/api/v1` surfaces (`/health*`, `/cluster/*`, `/openapi.json`, `/docs`) have
**no** state-changing routes; the WebSocket endpoint is not HTTP and is skipped.

## Client contract

A browser client must, on every `POST` / `PUT` / `PATCH` / `DELETE` to
`/api/v1`, copy the `bbz_csrf` cookie value into an `X-CSRF-Token` header. The
value is also returned in the `POST /api/v1/auth/login` response body
(`csrf_token`). Requests from the same origin need nothing extra; a configured
cross-origin SPA must be listed in `BBZ_CORS_ALLOW_ORIGINS`.

## Rollback

`BBZ_CSRF_ENABLED=false` disables `CsrfMiddleware` entirely (Origin **and**
token checks). Use only as a temporary measure — `SameSite=Lax` is then the sole
protection.

## Not in scope

Login CSRF beyond what `SameSite=Lax` and the Origin check already prevent (an
attacker forcing a victim to log in as the attacker); it carries no session
escalation here. GET-triggered side effects — there are none: every state change
is a non-safe method.
