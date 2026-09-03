# ADR-0031: Runtime settings store (DB-backed app config for the admin area)

## Status
Accepted (2026-09-03, roadmap E23 follow-up / #720, part of #718)

## Context
ADR-0015 established **all app config via environment variables** (`BBZ_`
prefix, `pydantic-settings`), rotated as an ops action, never a code change.
That holds for deployment identity, secrets, DSNs, HA wiring and feature
toggles.

The Administration build-out (#718) needs a small set of values an operator
changes **at runtime, from the UI**, without a redeploy:

- the BBZ instance name shown across the operator UI ("BBZ Nürnberg")
- which integration provider serves each domain (weather / monitor / telephony
  / video)
- the non-secret half of the directory (LDAP) connection

`Settings` is a frozen `lru_cache` singleton built from the environment at
process start — there is no path for any of this today. ADR-0015's "config is
env only" is the documented decision this contradicts, so per
`AGENTS.md` ("Architekturänderungen nur per ADR") it gets its own ADR rather
than a silent change.

## Decision
Introduce a **DB-backed settings store** that overlays — never replaces — the
environment configuration.

1. **`app_settings` table** — `key` (text PK), `value` (JSONB), `updated_by`
   (FK `users`, `SET NULL`), `updated_at`. One row per overridden key; absence
   means "not overridden".

2. **Precedence: DB value → environment → code default.** A key with no
   `app_settings` row resolves exactly as it does today. Existing deployments
   are unchanged until an operator sets a value. `SettingsStore.effective(key)`
   is the single read path; it keeps a short (10 s) process-wide TTL cache, so a
   change propagates cluster-wide within the TTL without a bus.

3. **Explicit whitelist.** `settings_catalog.py` names every overridable key,
   its group, type, validation and (for env-backed keys) the `Settings` field
   it falls back to. A key not in the catalog cannot be read or written through
   the store — the blast radius is fixed in code, like the permission catalog
   (ADR — `authorization/keys.py`).

4. **Admin API.** `GET /api/v1/admin/settings` (grouped, with the effective
   value and its source), `PUT /api/v1/admin/settings/{group}`. Gated on the
   existing `system.settings.manage` permission. Every write emits one
   `SETTING_CHANGED` audit row with a redacted before/after diff
   (`SETTING_CHANGED` is a `CRITICAL_ACTION`).

5. **Secrets stay out.** Secret-valued keys (LDAP bind password, OIDC client
   secret, integration API keys) are marked `secret` in the catalog. The store
   **never** persists them: `GET` reports only `configured: true|false`
   (computed from the `SecretProvider`, ADR-0019), `PUT` rejects them with 422
   pointing at the secret store. Runtime secret *management* is deferred to the
   ADR-0019 Vault rollout.

## Consequences
- A clear, auditable seam for operator-managed config; the 12-factor default
  still applies to everything not in the catalog.
- Consumers opt in one at a time (`instance.name` → `/meta` + UI in #721; the
  LDAP fields in #723; provider selection in #724) by reading through
  `SettingsStore` instead of `get_settings()`. Until then nothing changes.
- Two config sources means "why is this value X" has two places to look; the
  `GET` response always states the source (`database` / `environment` /
  `default`) to keep that debuggable.
- A DB outage falls back to the last cached value for up to the TTL, then to
  env/default — never to a hard failure.

## Alternatives considered
- **etcd (ADR-0018).** Already a dependency and cluster-native, but it is the
  *distributed coordination* store (leader lease, DCS). Operator-facing config
  wants the same transaction, audit chain and backup story as the rest of the
  domain data — that is Postgres.
- **Full move of `Settings` into the DB.** Far larger blast radius, and
  deployment identity / secrets / DSNs must stay env by ADR-0015. The overlay
  keeps the change proportional.
- **A generic key/value with no whitelist.** Rejected — an unbounded runtime
  override surface over security-relevant config is a footgun; the catalog
  makes every overridable key a reviewed code change.
