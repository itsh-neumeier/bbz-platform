# ADR-0015: Configuration and Secrets Management

## Status
Accepted (2026-08-29, review E01-01 / #20)

## Context
`.ai/SECURITY.md`: no credentials in the repo; use Docker secrets / a secret
store; least privilege. Multiple technical accounts exist (CUCM CTI/AXL/
serviceability, DB, agents), plus door DTMF profiles that must never be logged.

## Decision
- All app config via environment variables, `BBZ_` prefix, parsed by
  `pydantic-settings`. `.env.example` documents shape only; `.env` is git-ignored.
- Secrets are injected as files/env by the orchestrator (Docker/Compose secrets
  now; a real secret store — e.g. Vault/SOPS-age — decided before staging).
- Per-purpose credentials, never shared superusers (esp. CUCM, ADR-0002 §8.10).
- Sensitive values (DTMF codes, private keys) are stored encrypted and referenced
  by id; audit logs record the profile id, never the secret (ADR-0004).
- `alembic.ini` never contains a URL — `env.py` reads settings.
- CI: gitleaks (repo) + Trivy secret scan (filesystem/images).

## Consequences
- Clean 12-factor config; rotation is an ops action, not a code change.

## Alternatives considered
Committed encrypted secrets only (SOPS) — kept as an option for GitOps config,
but runtime secrets go through the orchestrator/secret store.

## Open points
- **The concrete runtime secret-store product** (e.g. HashiCorp Vault vs.
  SOPS-age) is deliberately out of scope here and is decided in a dedicated
  **ADR-0019** — roadmap issue E01-03 (#22), required before staging. Until then,
  runtime secrets are injected via Docker/Compose secrets as described above.
