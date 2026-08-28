# Repository settings checklist (manual)

These cannot be set from repo files; a maintainer configures them in GitHub.

## Branch protection — `main`

- [ ] Require a pull request before merging (≥ 1 approval)
- [ ] Require review from Code Owners
- [ ] Require status checks: `backend`, `frontend`, `commitlint`, `compose`,
      `gitleaks`, `pip-audit`, `trivy fs`
- [ ] Require branches to be up to date before merging
- [ ] Require linear history
- [ ] Block force pushes; block deletions
- [ ] Do not allow bypassing the above

## General

- [ ] Default branch: `main`
- [ ] Auto-delete head branches after merge
- [ ] Private repository (contains architecture for a critical-infrastructure system)
- [ ] Security: enable Dependabot alerts + security updates, secret scanning,
      push protection

## Open decisions

- **LICENSE**: not chosen yet. Corporate/OSS policy for DB InfraGO must be
  confirmed. Tracked in `.ai/CURRENT_STATE.md`.
- **Container registry**: GHCR per ADR-0014; confirm whether an internal mirror
  is required for production pull.
