# MFA policy engine + step-up (E21-05)

Makes a second factor **mandatory for chosen roles**, and demands a *fresh* MFA
check before a few sensitive actions. Builds on the TOTP factor from E02-13
(WebAuthn is E21-06).

## Role-based MFA requirement

A row in `mfa_policies` (`role_key`, `grace_period_days`) means: everyone who
holds that role — directly or through a group — must have a second factor.

`MfaPolicyService.evaluate(user_id)` returns:

| field | meaning |
|---|---|
| `required` | the user holds at least one policy'd role |
| `in_grace` | `now` is before the earliest `grant_time + grace_period_days` across their policy'd roles |
| `grace_until` | that deadline |

Enforcement runs on **every** login path (local password, OIDC callback, LDAP
fallback), via the shared `_enforce_mfa_policy` helper:

- **no factor, grace elapsed** → `401 { "code": "mfa_required" }`, `LOGIN_FAILED`
  audit. The account cannot log in until an admin gives it a factor or relaxes
  the policy.
- **no factor, still in grace** → login succeeds; the response carries
  `mfa_enrolment_required: true` and `mfa_grace_until`. The client should route
  the user straight to `POST /api/v1/auth/totp/enrol` before the deadline.
- **has an active local TOTP** → the normal TOTP challenge (`totp` field on
  `/auth/login`). A local factor satisfies the requirement on *any* provider, so
  an OIDC/LDAP user who also enrolled locally is fine.

### The grace period is the only enrolment window

Enrolment (`/auth/totp/enrol`) needs an authenticated session. A user with no
factor can only get one **during** the grace period. Operationally:

1. Create the policy with a grace period long enough to communicate it
   (`grace_period_days`, default 7).
2. Tell affected users to enrol before the deadline (the login response tells the
   client, but out-of-band notice matters).
3. After the deadline, a user who still has no factor is locked out — remediate
   by raising `grace_period_days` (resets nothing — the deadline is recomputed
   from the role grant time, so also re-grant the role if needed) or removing the
   policy row.

Settings: `mfa_policy_enforce_external` (default `true`; `false` limits
enforcement to local logins — external IdPs may enforce their own MFA).

## Step-up

`require_stepup(permission)` composes `require(permission)` and, **if** the
permission is in `mfa_stepup_permissions` (default `["permissions.manage"]`),
also checks that this session verified MFA within `mfa_stepup_max_age_seconds`
(default 300). `sessions.mfa_verified_at` is stamped by:

- a login that itself passed a TOTP / recovery challenge, and
- `POST /api/v1/auth/mfa-policies/step-up` `{ "totp": "..." }` → 204.

A stale session gets `401 { "code": "step_up_required" }` plus an
`MFA_STEPUP_REQUIRED` audit row. Currently wired onto
`PUT /api/v1/roles/{id}/permissions` and the MFA-policy writes; add more by
listing their permission keys in `mfa_stepup_permissions`.

## Admin API (`permissions.manage`, itself step-up gated)

| | |
|---|---|
| `GET /api/v1/auth/mfa-policies` | list |
| `PUT /api/v1/auth/mfa-policies/{role_key}` `{grace_period_days}` | create / update |
| `DELETE /api/v1/auth/mfa-policies/{role_key}` | remove |

Every write is an `MFA_POLICY_CHANGED` audit row (a critical action). Unknown
role → 422.

## Not built

Scope-based policies (only role-based), and verifying an *external* IdP's MFA
(WebAuthn for local accounts is E21-06).

---
Referenced from `.ai/SECURITY.md` and `.ai/CURRENT_STATE.md`.
