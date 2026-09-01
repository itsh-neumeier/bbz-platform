# LDAP / Active Directory login — configuration & open dependency

> **Code status: implemented (E21-03).** LDAP is a standardised protocol
> (RFC 4511); the client, the security rules and the tests are complete and run
> against a containerised OpenLDAP on every CI run.
>
> **Deployment status: BLOCKED on customer-supplied connection parameters.** The
> `ldap_ad` provider stays an inert stub until `BBZ_LDAP_URL` (and the rest of
> the block below) is set. Real directory hosts, the service-account DN, the
> search bases and the group filter are an **open external dependency** — see
> `.ai/CURRENT_STATE.md` → "Open external dependencies".

Source of truth: MASTER_PROMPT §11, roadmap E21-03, `.ai/SECURITY.md`
("Directory (LDAP/AD) authentication").

## What is implemented (vendor-neutral)

- **`bbz_core.auth.ldap`** — a blocking `ldap3` client (`LdapClient`):
  service-account bind → user search → **user bind (the actual authentication)**
  → optional group search. Raises a small typed taxonomy
  (`LdapAuthFailed` / `LdapInsecureError` / `LdapUnavailableError` /
  `LdapConfigError`, all under `LdapError`).
- **Encrypted transport is enforced.** An `ldaps://` URL, or a plain `ldap://`
  URL with StartTLS negotiated **before** the bind. A plain URL with
  `start_tls=False` is refused outright (`LdapInsecureError`) — a bind password
  never crosses the wire in the clear.
- **Failover pool.** `BBZ_LDAP_URL` is comma-separated; two or more URLs form an
  `ldap3.ServerPool` (first-active, exhaust-on-failure). Each node builds its own
  pool from the same config.
- **`LdapLoginService`** (`infra/repositories/ldap_login.py`) — runs the blocking
  client in a worker thread (`asyncio.to_thread`), resolves the directory
  principal to a BBZ user, reconciles group-mapped roles via the **shared**
  `GroupMappingService` (E21-02), and audits `LOGIN_SUCCEEDED` /
  `LOGIN_FAILED` (`provider=ldap_ad`).
- **`/api/v1/auth/login` fallback.** Local password auth is tried first; only a
  `BAD_CREDENTIALS` result *and* `ldap_ad` present in `BBZ_AUTH_PROVIDERS` trigger
  a directory bind. One generic `invalid credentials` on failure — no
  account-existence leak. `LOCKED` local accounts never reach LDAP.
- **JIT provisioning** is off by default (`BBZ_LDAP_JIT_PROVISIONING=false`): an
  unprovisioned directory user is rejected with `LdapAuthFailed`. When on, the
  first login creates the user + `AuthIdentity(provider="ldap_ad")` and grants
  `oidc_jit_default_role` (shared setting; empty ⇒ only mapped roles).

## Settings (all `BBZ_LDAP_*`)

| Setting | Required | Notes |
|---|---|---|
| `ldap_url` | yes | `ldaps://dc1:636,ldaps://dc2:636` — comma-separated failover pool |
| `ldap_bind_dn` | yes | service account DN (least privilege — read + search only) |
| `ldap_bind_password` | yes | **secret** — mount via `secrets_dir`, never a plain env var in prod |
| `ldap_user_search_base` | yes | e.g. `ou=people,dc=example,dc=org` |
| `ldap_user_filter` | no | default `(uid=%s)`; AD typically `(sAMAccountName=%s)` |
| `ldap_group_search_base` | no | empty ⇒ group resolution is skipped |
| `ldap_group_filter` | no | default `(&(objectClass=groupOfNames)(member=%s))`; `%s` = user DN |
| `ldap_uid_attr` | no | default `uid`; AD `sAMAccountName` |
| `ldap_name_attr` | no | default `cn`; AD `displayName` |
| `ldap_mail_attr` | no | default `mail` |
| `ldap_start_tls` | no | default `true`; ignored for `ldaps://` |
| `ldap_tls_verify` | no | default `true` — **keep true in production** |
| `ldap_tls_ca_file` | no | CA bundle for verification; empty ⇒ system store |
| `ldap_jit_provisioning` | no | default `false` |

## Unblocking checklist (when the customer supplies the directory)

1. Record the directory type (AD / OpenLDAP / other), version and the DC
   hostnames + port (636 preferred) in a new ADR or the deployment runbook.
2. Obtain the service-account DN + password (least privilege: bind + read +
   subtree search on the user and group bases). Store the password in the
   secrets store.
3. Confirm `user_filter` / `uid_attr` for the directory (`sAMAccountName` for AD).
4. Confirm the group model and `group_filter` (AD nested groups may need
   `LDAP_MATCHING_RULE_IN_CHAIN`); decide whether group→role mappings are
   configured now (E21-02 admin API) or after E21-04 sync.
5. Provide the CA certificate chain for `ldap_tls_verify=true`.
6. Set `BBZ_AUTH_PROVIDERS=["local","ldap_ad"]` and run one real login against
   the customer directory from a staging node; verify the `LOGIN_SUCCEEDED`
   audit row carries `provider=ldap_ad`.

## HA behaviour

The pool is per node. A total directory outage degrades to **local logins only**
— `/login` swallows every `LdapError` and reports generic invalid-credentials for
directory accounts; local accounts are unaffected. No directory dependency sits
on the readiness probe.

---
Referenced from `.ai/CURRENT_STATE.md` and `.ai/SECURITY.md`.
