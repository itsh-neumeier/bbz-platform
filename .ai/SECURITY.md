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

## Rate limiting (E23-04)
- Cluster-wide fixed-window counter (`rate_limit_hits`, migration 0052 — both
  nodes write the same rows). `429` + `Retry-After` over the limit.
- Rules (`BBZ_RATE_LIMIT_<RULE>`, `0` disables): `login` (per IP, 10/60),
  `mfa` (per user, 8/60 — TOTP activate + step-up), `password_reset` (per admin,
  5/300), `webhook` (per IP, 240/60 — inbound integration events).
- `login` / `mfa` / `password_reset` breaches audit `RATE_LIMIT_TRIGGERED`
  (rule + identifier + count, never the credential — critical action).
- Fails **open** if the store is unreachable. Complements the per-account login
  lockout (E02-03). WAF/DDoS is the edge's job. `docs/security/rate-limiting.md`.

## CSRF (E23-05)
- `bbz_core.api.csrf.CsrfMiddleware` guards **every** `POST/PUT/PATCH/DELETE`
  under `/api/v1` — enforcement is structural, not per-route
  (`test_csrf.py` walks the OpenAPI schema and fails on any gap).
- Acts when a session cookie is present and there is **no** `Authorization:
  Bearer` — bearer clients (agents, integrations) are immune to CSRF and exempt.
- Three layers: `SameSite=Lax` on all session cookies · a **session-bound**
  double-submit token (`bbz_csrf` cookie == `X-CSRF-Token` header, value =
  `b64(sid).b64(HMAC(jwt_secret, sid))`) · an `Origin`/`Referer` allow-list
  (`cors_allow_origins` + same-origin) checked when the header is present.
- Token-exempt (pre-auth, Origin still checked): `POST /auth/login`,
  `POST /auth/oidc/{provider}/callback`. Bearer-only: `POST /telephony/events`.
- `BBZ_CSRF_ENABLED=false` is the rollback. `docs/security/csrf.md`.

## Input validation & payload limits (E23-06)
- Every `/api/v1` write body is a Pydantic model with `extra="forbid"` — an
  unknown field is a `422`, closing over-posting. New models subclass
  `bbz_core.api.schema.StrictModel`. `test_input_validation.py` walks the route
  table and fails the build on any non-strict write body. The sole exception is
  `POST /telephony/events` (raw provider webhook dict, normalised downstream).
- `BodyLimitMiddleware` (outermost) rejects any write body over
  `BBZ_MAX_REQUEST_BODY_BYTES` (default 1 MiB) with `413` — checked before auth /
  CSRF / routing, declared `Content-Length` **and** streamed bytes. `0` disables.
- `docs/security/input-validation.md`.

## Dependency / container scanning (E23-07, ADR-0014)
- `security.yml` — all **blocking**, per-PR + weekly cron: `gitleaks` ·
  `pip-audit --strict` (any known vuln) · `trivy fs` (CRITICAL/HIGH, fixable) ·
  `scan-exception policy`. `npm audit` for `apps/web` runs non-blocking until #14.
- Exceptions live **only** in `deploy/security/scan-exceptions.toml`, enforced by
  `tools/security/check_scan_exceptions.py`: every entry needs a `reason` + a
  future `expires` (≤ 90 days). Expired ⇒ CI fails ⇒ the finding re-arms. The
  same script emits the scanner flags, so the list can't drift. Currently empty.
- `docs/security/vulnerability-scanning.md`.

## Audit-log integrity (E23-09, extends E04-10)
- `audit_events` is append-only already (ORM guard + `BEFORE UPDATE OR DELETE`
  trigger, ADR-0020). The hash chain adds tamper **detection** for the rest
  (a DBA with `session_replication_role=replica`, a doctored restore).
- `audit_events.seq` (BIGINT identity) + append-only `audit_chain_links`:
  `row_hash = sha256(prev_hash + sha256(canonical(row)))`, genesis `64×"0"`.
- The `audit-chain` leader-elected singleton **seals** new rows (deferred — zero
  latency on the audited action) and **verifies** the whole chain every
  `BBZ_AUDIT_CHAIN_INTERVAL_SECONDS` (300). A recomputed-hash mismatch, a
  `prev_hash` break, a `seq` gap, or a vanished row → `AUDIT_INTEGRITY_ALERT`
  (critical action, first bad `seq` + reason).
- `GET /api/v1/audit/chain` (`system.audit.view`) re-verifies + pages the links
  for offline re-check / WORM export. `BBZ_AUDIT_HASH_CHAIN_ENABLED=false` = off.
- `docs/security/audit-integrity.md`.

## Secret store (ADR-0019)
- Target: **HashiCorp Vault** (Raft HA co-located on the 2 BBZ nodes + witness,
  AppRole auth). Not yet rolled out — a later issue.
- Now: every secret is read through `bbz_core.secrets.SecretProvider`. The
  default `EnvFileSecretProvider` is the ADR-0015 mechanism (a
  `$BBZ_SECRETS_DIR/<name>` file, else `$BBZ_<NAME>`), short-TTL cached so a
  rotated mounted secret is picked up **without a restart**.
- **Fail-closed**: the app refuses to start if a secret the running config
  requires is missing (`verify_required_secrets`).
- **Rotation**: `POST /api/v1/system/secrets/reload` (`system.cluster.manage`)
  re-reads the tracked secrets and audits `SECRET_ROTATED` (name only) for each
  that changed.


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

## WebAuthn / FIDO2 (E21-06)
- A phishing-resistant second factor for **local** accounts (passwordless
  first-factor is out of scope). Credentials are isolated per user; the
  registration / assertion challenge is server-issued, single-use, DB-backed
  (HA), and TTL'd (`webauthn_challenge_ttl_seconds`).
- User verification (PIN / biometric) is required by default
  (`webauthn_require_user_verification`); the signature counter is checked and
  must move forward.
- The RP id and allowed origin(s) are explicit config
  (`webauthn_rp_id` / `webauthn_origins`); unset ⇒ enrolment returns 503.
- A WebAuthn credential satisfies the MFA policy (E21-05) and can be used for
  step-up. Register / remove audit `WEBAUTHN_REGISTERED` / `WEBAUTHN_REMOVED`.
- Config: `docs/auth/webauthn.md`.

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

## Account linking (E21-08)
- A user can hold several `auth_identities` (local + Entra + LDAP). Linking and
  unlinking act only on the caller's own account and require a **fresh
  second-factor confirmation** when the account has a factor.
- Unlink guards prevent lock-out: never the last identity, never a reduction of
  the last active admin's sign-in methods.
- Linking a verified external identity is refused if that `(provider, subject)`
  is already on another account. `IDENTITY_LINKED` / `IDENTITY_UNLINKED` /
  `AUTH_PROVIDER_CONFIGURED` audit (critical actions).
- `auth_provider_config` is display-only — it never enables auth that the
  deployment's env / secrets do not already back.

## Advanced RBAC (E21-07)
- A `role_permissions.condition` (Rule-DSL, ADR-0010) can only **narrow** a grant.
  It evaluates against a clock-only context (ADR-0027), is validated at write
  time, and is deny on any failure. Off by default (`rbac_conditions_enabled`).
- Role grants may carry a validity window (`user_roles.valid_from` / `valid_to`);
  an out-of-window grant is not returned by the grant store.
- Permission delegation (`permission_delegations`) always expires and is
  revocable; the delegator must actually hold the permission. A revoke / expiry
  is effective on the delegatee's next request. `PERMISSION_DELEGATED` /
  `PERMISSION_DELEGATION_REVOKED` audit (critical actions).

## Door control security
- Door-open actions require a dedicated permission and complete audit trail.
- DTMF door codes are secrets/configuration values and must not be written in plaintext audit logs.
- Store secret values encrypted / via secret store; audit the action profile ID, not the code.
- Duplicate/replayed telephony events must never cause duplicate door-open actions.

## Logging (E22-03)
- Two redaction layers run on every log line before it is rendered:
  **by key** (a value whose key contains `password` / `token` / `authorization`
  / `dtmf` / `secret` / `api_key` / `private_key` / `credential` / `otp` /
  `recovery_code` / `session_key` → `[redacted]`, recursively) and **by value**
  (transient `redacting()` secrets, E17-06). `test_logging.py` asserts no secret
  survives.
- `BBZ_LOG_FILE` is a plain append sink for a sidecar; the platform operates no
  log store. Log lines carry `user_id` / `correlation_id` / `trace_id` but never
  a token, password or DTMF code.

## Tracing (E22-01, ADR-0028)
- Span attributes carry HTTP method / route / status / peer, `db.system` /
  `db.operation` / `db.statement`, and our `bbz.correlation_id`. `db.statement`
  is the **parameterised** SQL — never bound values. Request/response headers
  and bodies are **not** captured.
- The span exporter runs `bbz_core.redaction.scrub` over every span and event
  attribute (E17-06 doctrine), so a transient `redacting(...)` secret cannot
  leave the process via a trace even if some instrumentation echoes it.
- The OTLP exporter is **off** by default (`otel_traces_exporter=none`) — until
  a collector is deployed (E22-07), spans never leave the process. Config is
  `BBZ_`-prefixed only; there is no `OTEL_*` passthrough.
