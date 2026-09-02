# ADR-0019: Runtime secret store

## Status
Accepted (2026-09-02, review E01-03 / #22)

## Context
ADR-0015 pins config to `BBZ_`-prefixed env vars parsed by `pydantic-settings`
and injects secrets as files/env via the orchestrator (Docker/Compose secrets),
leaving "the concrete runtime secret-store product … decided before staging" —
an open point that also blocks E23-01 (wire the store) and E23-13 (rotation).

Constraints:
- **Deployment**: two on-prem BBZ application servers + one quorum/witness,
  Docker, no cloud. A Leitstelle — the platform must keep taking calls even
  while the secret store is unreachable.
- **E23-01 acceptance criteria**: no production secret in plaintext; **rotation
  without a redeploy**; **startup fails if a required secret is missing**.
- Multiple technical accounts (DB, CUCM CTI/AXL/serviceability, LDAP bind,
  agents) plus encryption keys (TOTP, door-DTMF Fernet, JWT) — see `.ai/SECURITY.md`.
- The store, if it is a service, "must itself be HA / reachable on both nodes".

Pure SOPS-age (encrypted secrets in git) was considered but does not meet
"rotation without a redeploy" — rotating a secret there is a re-encrypt + commit
+ redeploy. It stays the mechanism for GitOps *config* (ADR-0015), not runtime
secrets.

## Decision

**Target store: HashiCorp Vault**, self-hosted, KV v2, with **integrated Raft
storage co-located on the three cluster nodes** (2 BBZ servers + the witness) so
Vault's own quorum rides the same failure domains the platform already tolerates
(ADR-0001/0018). App nodes authenticate with **AppRole** (role id baked into the
image config, secret id delivered as a short-lived Compose/orchestrator secret
and renewed). Auto-unseal via transit or a documented manual unseal for the
first bring-up.

**Ship now — the abstraction, not the product** (E23-01):

- `bbz_core.secrets.SecretProvider` — a small interface (`get` / `version`) that
  every secret read goes through. Concrete providers:
  - `EnvFileSecretProvider` (**default**) — the ADR-0015 mechanism: a
    `$BBZ_SECRETS_DIR/<name>` file, else `$BBZ_<NAME>`. Short-TTL cached so a
    rotated file is picked up **without a restart** (the orchestrator updates the
    mounted secret; the app re-reads within the TTL).
  - `VaultSecretProvider` — interface + AppRole/KV-v2 sketch, **not wired to a
    live Vault in this issue**. Selecting `BBZ_SECRET_PROVIDER=vault` before the
    rollout issue lands fails fast with a pointer here.
- **Fail-closed startup**: `verify_required_secrets()` runs in the app lifespan
  and refuses to start (listing every missing name at once) when a secret that
  the current configuration requires does not resolve — e.g. a non-`local`
  environment with the placeholder `jwt_secret`, or a feature enabled without
  its Fernet key.
- **Rotation**: `SecretsRotationService.reload()` re-reads the tracked secrets,
  clears the settings cache, and audits `SECRET_ROTATED` (name only, never the
  value) for each changed secret. Exposed as
  `POST /api/v1/system/secrets/reload` (`system.cluster.manage`) and safe to
  call on a schedule.

**Migration path** (Compose secrets → Vault):
1. *now* — `EnvFileSecretProvider`; secrets are Docker/Compose file secrets;
   `deploy/node/secrets/*` (gitignored). Startup is already fail-closed.
2. *Vault rollout issue* — add the Vault service to `deploy/` (Raft, 3 members,
   unseal runbook), implement `VaultSecretProvider` (hvac or the HTTP API),
   flip `BBZ_SECRET_PROVIDER=vault`. No call-site changes — everything already
   goes through `SecretProvider`. Rotation becomes a Vault operation + the
   existing `reload` endpoint.
3. Dev stays on `EnvFileSecretProvider` forever.

Vault is **never a hard dependency of request handling** — providers cache, and
a provider error on a *non-required* secret degrades that feature, it does not
stop the node.

## Consequences
- E23-01 can land without standing up a Vault cluster; the seam is real and
  tested, so the Vault rollout is additive.
- One code path for every secret read; rotation is an ops action + one audited
  API call, not a code change (ADR-0015's promise, now concrete).
- Running Vault HA later is real operational weight (unseal, Raft, backup) —
  accepted, and its own runbook, when the rollout issue is scheduled.
- Until then, "rotation without a redeploy" is satisfied by re-reading mounted
  file secrets, not by a dynamic-secret engine.

## Alternatives considered
- **SOPS-age for runtime secrets** — fails "rotation without a redeploy";
  retained for GitOps config only.
- **Kubernetes Secrets / External Secrets Operator** — no Kubernetes in this
  deployment.
- **Cloud KMS / a SaaS secret manager (Doppler, Infisical)** — on-prem, air-gap-
  capable target; external dependency rejected for the core Leitstelle.
- **Commit to Vault now, wire it now** — larger blast radius in one issue and a
  Vault cluster to operate before it is needed; the abstraction lets the
  decision be real without the rollout.
