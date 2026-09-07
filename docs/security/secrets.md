# Runtime secrets

Roadmap **E23-01**, decision **ADR-0019**. `bbz_core.secrets`.

## How a secret is read

Every secret goes through a `SecretProvider`. The default,
`EnvFileSecretProvider`, is the ADR-0015 mechanism:

1. `BBZ_<NAME>` environment variable, else
2. `$BBZ_SECRETS_DIR/<name>` file (Docker/Compose secret mounted at
   `/run/secrets`), else
3. `None` — the setting keeps its default (a feature that needs the secret is
   disabled, or startup fails — see below).

Values are cached for 30 s, so a **rotated mounted file is picked up without a
restart** (an env-sourced secret cannot change in a running process — it needs a
restart, by design).

`BBZ_SECRET_PROVIDER` selects the provider (`env`, default). `vault` is the
ADR-0019 target and is **not wired yet** — selecting it fails fast with a
pointer to the ADR. It is read straight from the environment, not from
`Settings`, to avoid a bootstrap cycle.

## Fail-closed startup

`verify_required_secrets()` runs in the app lifespan. In `staging` /
`production` the process **refuses to start** (listing every problem at once)
when:

- `jwt_secret` is unset or still the insecure dev default, or
- `database_url` carries no password.

`local` / `ci` are exempt.

## Rotation

1. Rotate the secret in the store — update the mounted file (or, later, the
   Vault KV entry).
2. `POST /api/v1/system/secrets/reload` (`system.cluster.manage`) — re-reads the
   tracked secrets, and for each whose value now differs from the running
   config clears the settings cache and audits `SECRET_ROTATED` (the field
   name, **never the value**). Response: `{"reloaded": ["jwt_secret", …]}`.
   Safe to call on a schedule — a no-op when nothing changed.

Tracked: `jwt_secret`, `totp_encryption_key`, `door_dtmf_encryption_key`,
`sip_encryption_key`, `ldap_bind_password`, `oidc_entra_client_secret`.

`sip_encryption_key` (`BBZ_SIP_ENCRYPTION_KEY`, a Fernet key) encrypts the
`telephony_sip` gateway's ARI password at rest (**ADR-0033**) — the gateway
config is DB-backed and UI-managed, but the password never lands in
`app_settings`, a log, or an audit row. Required only when `telephony_sip` is
the active telephony provider; unset, the SIP admin API returns 503 and the
provider stays inert (fail-closed, exactly like `door_dtmf_encryption_key`).
Rotating it means re-entering the ARI password in the admin UI.

## The Vault target (not yet)

ADR-0019 chooses HashiCorp Vault (Raft HA on the 2 BBZ nodes + witness, AppRole
auth). Its rollout — a Vault service in `deploy/`, the unseal runbook,
`VaultSecretProvider`, and routing `Settings` through the provider — is a
separate later issue. The `SecretProvider` seam here means that lands without
touching any call site.
