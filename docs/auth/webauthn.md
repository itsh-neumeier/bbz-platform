# WebAuthn / FIDO2 (E21-06)

A phishing-resistant second factor for **local** accounts, built on
`py_webauthn` (WebAuthn L2). A credential belongs to the `local` auth identity;
an assertion satisfies the same MFA-policy check as a TOTP code (E21-05).
Passwordless first-factor is out of scope.

## Configuration

| Setting | Notes |
|---|---|
| `webauthn_rp_id` | the **registrable domain** (e.g. `bbz.example.org`). Empty ⇒ enrolment returns 503 |
| `webauthn_rp_name` | display name shown by the authenticator |
| `webauthn_origins` | comma-separated allowed browser origins (e.g. `https://bbz.example.org`) — must match what the browser sends |
| `webauthn_require_user_verification` | default `true` — require PIN / biometric for a credential to count as MFA |
| `webauthn_challenge_ttl_seconds` | default `300` |

The RP id + origin are a **deployment input**: they depend on the real
customer-facing hostname.

## Ceremonies

Registration (self-service, authenticated session):

1. `POST /api/v1/auth/webauthn/register/options` → `{ options }` — the raw
   `PublicKeyCredentialCreationOptions` JSON for `navigator.credentials.create`.
   The server stashes the challenge.
2. Browser creates the credential.
3. `POST /api/v1/auth/webauthn/register/verify` `{ response, name }` →
   `201` with the stored credential. `WEBAUTHN_REGISTERED` audit.

Login (second factor):

1. `POST /api/v1/auth/login` `{ username, password }` — if the account has a
   credential and no `webauthn` value: `401 { "code": "webauthn_required",
   "details": { "options": "<PublicKeyCredentialRequestOptions JSON>" } }`.
2. Browser runs `navigator.credentials.get`.
3. `POST /api/v1/auth/login` `{ username, password, webauthn: "<assertion JSON>" }`
   → session. The signature counter is verified to move forward.

Step-up / re-auth (authenticated):

- `POST /api/v1/auth/webauthn/authenticate/options` → `{ options }`
- `POST /api/v1/auth/mfa-policies/step-up` `{ webauthn: "<assertion JSON>" }` → 204

Management:

- `GET /api/v1/auth/webauthn/credentials` — this account's credentials
- `DELETE /api/v1/auth/webauthn/credentials/{id}` — `WEBAUTHN_REMOVED` audit

## Recovery

Register **more than one** credential (a backup key), and/or keep a TOTP factor
enrolled — the login and step-up flows accept a TOTP code, a TOTP recovery code,
or a WebAuthn assertion interchangeably. There is no server-side "reset my
WebAuthn" — losing the only factor while a policy requires MFA means an admin
must relax the policy (see `docs/auth/mfa-policy.md`).

## Not built

- Passwordless first-factor login.
- Challenging a WebAuthn factor during an **OIDC / LDAP** login (those paths
  treat "has a credential" as satisfied, like they do for TOTP — E21-05).
- The browser end-to-end test with a CDP virtual authenticator → Epic 07. The
  backend is covered by an in-process software authenticator
  (`test_webauthn.py`).

---
Referenced from `.ai/SECURITY.md` and `.ai/CURRENT_STATE.md`.
