# Account linking + auth-provider config (E21-08)

A BBZ user can hold several sign-in identities (`local` password, `ldap_ad`,
`entra_oidc`). "Local users must remain possible" (MASTER_PROMPT §11) — linking
never removes that option.

## Linking / unlinking (self-service)

All routes act on the **caller's own** account and require a **fresh
second-factor confirmation** when the account has a factor (a plain
password-only session is not fresh — do `POST /auth/mfa-policies/step-up` first;
a no-factor account is exempt).

| | |
|---|---|
| `GET /api/v1/auth/identities` | the caller's identities |
| `POST /api/v1/auth/identities/local` `{username, password}` | add a local password (account had none) |
| `POST /api/v1/auth/identities/ldap` `{username, password}` | bind, then attach the `ldap_ad` identity |
| `POST /api/v1/auth/identities/oidc/{provider}/start` | → `{authorization_url}` (a linking flow) |
| `POST /api/v1/auth/identities/oidc/{provider}/callback` `{code, state}` | verify + attach |
| `DELETE /api/v1/auth/identities/{id}` | unlink |

- Linking a verified external `(provider, subject)` that is already on another
  account → 409. A second identity for the same provider → 409.
- **Unlink guards**: the account's last identity → 409; an unlink that would
  reduce the last active administrator's sign-in methods → 409. Unlinking
  cascades to that identity's credentials / TOTP / WebAuthn.
- `IDENTITY_LINKED` / `IDENTITY_UNLINKED` audit (critical).

## Auth-provider config (`permissions.manage`)

`GET /api/v1/auth/providers` / `PUT /api/v1/auth/providers/{provider}`
`{enabled, display_name}` — a per-provider **display** toggle for the login /
linking UI. It is **not** a security control: it never enables auth that
`BBZ_AUTH_PROVIDERS` + the connection settings do not already back (those stay an
open external dependency). `AUTH_PROVIDER_CONFIGURED` audit.

Group→role mapping is `docs/auth/…` (E21-02, `/auth/group-mappings`); the MFA
policy is `docs/auth/mfa-policy.md` (E21-05, `/auth/mfa-policies`).

## Not built (→ Epic 07)

The admin UI (provider config, mappings, MFA policy screens) and the Playwright
link/unlink + "last identity" coverage.

---
Referenced from `.ai/SECURITY.md` and `.ai/CURRENT_STATE.md`.
