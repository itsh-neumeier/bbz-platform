# ADR-0014: CI/CD and Supply Chain

## Status
Accepted (2026-08-29, review E01-01 / #20)

## Context
MASTER_PROMPT §19 requires lint/type/test, security scan, container build, SBOM,
image signing and GHCR push, with versioned images and no unverified `latest` in
production.

## Decision
- GitHub Actions. `ci.yml`: backend (ruff, ruff-format, mypy, import-linter,
  pytest+coverage, Alembic up/down/up against real PostgreSQL), frontend (eslint,
  vue-tsc, vitest), commitlint, `docker compose config`.
- `security.yml`: gitleaks, `pip-audit --strict`, Trivy FS (CRITICAL/HIGH),
  scheduled weekly + on PR.
- `release.yml` (built out end of Phase 0/Phase 2): build images tagged by git
  SHA **and** semver, generate SBOM (Syft), sign with cosign (keyless OIDC),
  push to GHCR. Deployments consume immutable digests.
- Dependabot for pip, npm, github-actions, docker.
- Branch protection on `main`: PR required, CI required, no force-push, linear
  history, CODEOWNERS review. (Configured in repo settings — see
  `docs/repo-settings.md`.)

## Consequences
- Provenance and vulnerability posture from the first release.
- Slightly longer PR feedback loop (parallel jobs mitigate).

## Alternatives considered
Self-hosted runners / other CI (rejected for now: GHCR + Actions + OIDC signing
is the least-friction path for a GitHub-hosted repo).
