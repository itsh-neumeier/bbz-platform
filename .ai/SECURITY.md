# .ai/SECURITY.md

Target authentication:
- local users
- Entra ID OIDC
- LDAP/AD
- MFA

Security baseline:
- TLS
- Argon2id local passwords
- PKCE for OIDC
- secure cookies/tokens
- server-side RBAC
- audit
- secret management
- dependency/container scanning
- least privilege
- non-root containers where possible

No credentials in repo.


## MFA policy + step-up (E21-05)
- MFA is a **role-based** requirement (`mfa_policies`): holding any policy'd role
  (direct or via a group) makes a second factor mandatory. A grace period per
  policy lets a newly-assigned user enrol; after it elapses, login is refused
  (`401 mfa_required`) until they have a factor — the login response carries
  `mfa_enrolment_required` + `mfa_grace_until` during grace so the client can
  force enrolment. Enforced on **every** login path (local / OIDC / LDAP);
  external logins can be exempted with `mfa_policy_enforce_external=false`.
- **Step-up**: a small set of sensitive permissions (`mfa_stepup_permissions`,
  default `permissions.manage` — used on the RBAC role-permission write and the
  MFA-policy writes) additionally require a *fresh* MFA verification on the
  session (`mfa_stepup_max_age_seconds`, default 300). A stale session gets
  `401 step_up_required` and an `MFA_STEPUP_REQUIRED` audit row; the user clears
  it with `POST /api/v1/auth/mfa-policies/step-up`.
- Policy changes audit `MFA_POLICY_CHANGED` (a critical action).
- Config: `docs/auth/mfa-policy.md`.

## Agent / remote control security
- Agents enroll with short-lived token and receive a unique device identity/certificate.
- No arbitrary shell/PowerShell/cmd execution endpoint.
- No arbitrary URL launch from operator input; only centrally allowlisted catalog entries.
- Remote logout/restart requires dedicated permission, explicit confirmation and audit.
- Commands contain command_id, nonce/sequence, expiry and are replay protected.
- Agent commands are routed through BBZ server authorization, not browser-to-agent direct trust.

## Directory (LDAP/AD) authentication
- Encrypted transport only: `ldaps://`, or `ldap://` with StartTLS negotiated
  before the bind. A plaintext URL without StartTLS is refused (`LdapInsecureError`)
  — the bind password never crosses the wire in the clear.
- Server certificate verification on by default (`ldap_tls_verify`); keep it true
  in production.
- The service account binds with least privilege (search + read only); its
  password is a secret (secrets store, never the manifest or a plain env var).
- `/login` tries local auth first and only falls back to a directory bind on a
  bad-credentials result; one generic failure is reported (no account-existence
  or lockout-reason leak). A directory outage degrades to local logins only.
- Directory logins audit `LOGIN_SUCCEEDED` / `LOGIN_FAILED` with `provider=ldap_ad`.
- **Directory sync (E21-04)** — a leader-elected singleton reconciles BBZ against
  the directory: accounts that vanish are **soft-deactivated** (status + session
  revocation, never a hard delete) for reliable off-boarding, auditing
  `USER_DEACTIVATED`; every run audits `DIRECTORY_SYNC_COMPLETED`. Guards against
  a directory error mass-off-boarding: an empty enumeration, or more
  deactivations than `ldap_sync_max_deactivations`, aborts the run untouched. A
  dry run computes the diff and writes nothing.
- Config + open-dependency checklist: `docs/auth/ldap-directory.md`.

## Door control security
- Door-open actions require a dedicated permission and complete audit trail.
- DTMF door codes are secrets/configuration values and must not be written in plaintext audit logs.
- Store secret values encrypted / via secret store; audit the action profile ID, not the code.
- Duplicate/replayed telephony events must never cause duplicate door-open actions.
