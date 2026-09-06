# ADR-0033: SIP gateway configuration is DB-backed and UI-managed (credentials encrypted at rest)

## Status
Accepted (2026-09-06, roadmap E13-03 ff. / #273)

## Context

Epic 13 adds the `telephony_sip` provider (Asterisk via ARI, ADR-0023). It needs
connection configuration: gateway `host` / `port` / `tls`, the ARI API user +
password, the Stasis application name, `dtmf_transport`, and the set of SIP
lines / endpoints the instance owns.

The product intent (MASTER_PROMPT §6 / integration-first): a BBZ site running
SIP must be able to point BBZ at **their** Asterisk — host, credentials, lines —
from the admin UI, without a redeploy or a shell on the box.

Two existing decisions frame how config + secrets are handled:

- **ADR-0031 (runtime settings store)** — app config is a DB overlay over env,
  but *secrets stay out*: secret-valued keys are marked `secret`, `GET` reports
  only `configured: true|false`, `PUT` rejects them with 422; runtime secret
  *management* is deferred to the ADR-0019 Vault rollout.
- **ADR-0019 (secret store)** — a `SecretProvider` abstraction;
  `EnvFileSecretProvider` now, `VaultSecretProvider` later. The `telephony_sip`
  `config_schema.json` already has `credentials_secret_ref` — a reference into
  the secret store, never inline.

But there is a **working precedent for an at-rest encrypted secret in a domain
table, set write-only through an admin API**: `door_action_profiles` (E17-02)
stores the door-open DTMF code Fernet-encrypted (`bbz_core.infra.door_secrets`,
key `BBZ_DOOR_DTMF_ENCRYPTION_KEY`), entered only in a `POST`/`PATCH` body over
TLS, **never** returned, logged or audited, gated `door.configure`. TOTP secrets
(`bbz_core.auth.totp`) do the same. Neither goes through the settings store.

## Decision

**`telephony_sip` connection configuration lives in the DB and is managed
through the admin UI. The ARI password is encrypted at rest.**

1. **New domain tables (not settings keys).**
   - `sip_gateway` — one active row: `kind` (`asterisk_ari`), `host`, `port`,
     `tls`, `app_name`, `dtmf_transport`, `ari_username`,
     `ari_password_ciphertext`, `enabled`, `updated_by`, timestamps.
   - `sip_lines` — `bbz_line_id` (unique) → `asterisk_endpoint`, `label`,
     `enabled`.

2. **The ARI password is Fernet-encrypted at rest** via a new
   `bbz_core.infra.sip_secrets` (mirrors `door_secrets`), key
   `BBZ_SIP_ENCRYPTION_KEY`. It enters only in a `PUT` body over TLS, is
   encrypted immediately, and is **never** returned by `GET`, logged, or written
   to an audit row — `GET` reports `ari_password_configured: true|false`.

3. **Admin API** under `/api/v1/admin/telephony/sip` (+ `.../sip/lines` CRUD,
   `POST .../sip/test` for a live connection check), gated **`integrations.configure`**.
   Every write emits one `SIP_GATEWAY_CONFIGURED` audit row (critical) carrying
   the id and a redacted non-secret before/after diff — never the password.

4. **`active_telephony_provider()` builds the ARI client from this DB config**
   for `telephony_sip` (decrypting the password in-process only), instead of the
   `build(config_dict)` env path. A missing `BBZ_SIP_ENCRYPTION_KEY` while
   `telephony_sip` is active → the admin API returns 503 and the provider stays
   inert (fail-closed, like `door_secrets`).

5. **The `config_schema.json` stays** as the documented shape for a
   file/env-provisioned instance (dev, CI, a deployment that prefers the secret
   store via `credentials_secret_ref`). The DB config is the production path.

### Why this is a scoped exception to ADR-0031

It covers exactly one integration's connection credential, reuses the
`door_action_profiles` encryption + write-only-API pattern verbatim, and does
**not** touch `app_settings` — it is a domain table, not a settings key. ADR-0031
kept general secret management out of the settings store; it did not rule out
the `door_action_profiles`-style pattern, which predates it and is unchanged
here. When the ADR-0019 Vault rollout lands, `sip_gateway.ari_password_ciphertext`
moves behind the `SecretProvider` together with the other at-rest secrets.

## Consequences

- A site admin configures SIP end to end from the UI — connection, credentials,
  lines, "test connection", health — with no redeploy.
- `BBZ_SIP_ENCRYPTION_KEY` joins `BBZ_DOOR_DTMF_ENCRYPTION_KEY` /
  `BBZ_TOTP_ENCRYPTION_KEY` as a required secret when `telephony_sip` is the
  active provider. Documented in `docs/security/secrets.md`.
- One more at-rest encrypted secret to rotate.
- A provider instance is cached for the `bbz-api` process lifetime (integration
  host) — a config change takes effect on the next restart, the same as today's
  env-based provider selection. A live reload is a later refinement.
- The `telephony_sip` ARI adapter needs a WebSocket client for the ARI event
  stream; `websockets` (pure-Python, maintained by the CPython telemetry team,
  no transitive deps) joins the server dependencies — targeted per epic, like
  `ldap3` (E21-03) and `webauthn` (E21-06). REST is `httpx` (already a dep).

## Alternatives considered

- **Hybrid — non-secret config in the DB/UI, the ARI password only in the
  secret store (env/file/Vault), UI shows read-only "configured".** Rejected per
  the product ask ("alles UI-driven") and because it splits one integration's
  config across two stores with different change procedures.
- **A new "encrypted secret value" capability in the settings store.** Larger
  blast radius — it would turn `app_settings` into a general encrypted-secret
  store, exactly what ADR-0031 avoided. A SIP-scoped domain table is
  proportional.
- **Wait for the ADR-0019 Vault rollout.** Vault is not deployed and has no
  timeline; waiting blocks Epic 13's UI story for no security gain over the
  Fernet-at-rest pattern already in production for door + TOTP secrets.
