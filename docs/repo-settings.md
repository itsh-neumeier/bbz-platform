# Repository settings (roadmap E01-05, ADR-0014)

These live in GitHub, not in the repo. A maintainer applies them once and
re-checks them when a **required** CI job is renamed. The `gh api` calls below
are the reproducible form; the checkboxes are the manual-UI equivalent.

## Branch protection — `main`

- [ ] Require a pull request before merging, **≥ 1 approval**
- [ ] Dismiss stale approvals on new commits
- [ ] Require review from **Code Owners** (`.github/CODEOWNERS`)
- [ ] Require **status checks** (exact names — see the list below)
- [ ] Require branches to be **up to date** before merging
- [ ] Require **linear history** (matches the squash-merge workflow)
- [ ] Require **conversation resolution** before merging
- [ ] Block **force pushes**; block **deletions**
- [ ] **Do not allow bypassing** the above (applies to admins)

### Required status checks

The exact check-run names as they appear on a commit. Keep this list and the
`contexts` array below in sync with `.github/workflows/{ci,security}.yml` job
`name:` values:

| check | workflow | notes |
|---|---|---|
| `backend (lint · type · imports · test)` | ci | ruff, mypy, import-linter, pytest+cov, Alembic up/down/up |
| `migration compat (N-1 app × N schema)` | ci | previous app version must read the new schema |
| `frontend (lint · type · unit)` | ci | **not yet required** — `continue-on-error` until E01-06 wires `npm ci` |
| `conventional commits` | ci | commitlint over the PR range |
| `docker compose config` | ci | every compose stack + Caddyfile + promtool + otelcol validate |
| `workflow lint (actionlint)` | ci | added with E01-04 — gates `release.yml`, which has no other PR run |
| `gitleaks` | security | secret scan |
| `scan-exception policy` | security | every scanner exception has a reason + a ≤ 90-day expiry (E23-07) |
| `pip-audit` | security | third-party Python deps, `--strict` |
| `trivy fs` | security | filesystem vuln + secret + misconfig |
| `non-root images` | security | every self-built image runs non-root (E23-08) |
| `npm audit (apps/web)` | security | **not yet required** — advisory until #14 |

### `gh api` — apply the rule

```sh
OWNER=itsh-neumeier REPO=bbz-platform
gh api -X PUT "repos/$OWNER/$REPO/branches/main/protection" \
  --input - <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "backend (lint · type · imports · test)",
      "migration compat (N-1 app × N schema)",
      "conventional commits",
      "docker compose config",
      "workflow lint (actionlint)",
      "gitleaks",
      "scan-exception policy",
      "pip-audit",
      "trivy fs",
      "non-root images"
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "require_code_owner_reviews": true,
    "dismiss_stale_reviews": true
  },
  "required_linear_history": true,
  "required_conversation_resolution": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "restrictions": null
}
JSON
```

Add `"frontend (lint · type · unit)"` to `contexts` when E01-06 lands, and
`"npm audit (apps/web)"` when #14 closes.

Read the current rule back with:

```sh
gh api "repos/$OWNER/$REPO/branches/main/protection" \
  --jq '{checks: .required_status_checks.contexts, admins: .enforce_admins.enabled, reviews: .required_pull_request_reviews}'
```

## Tag protection

Releases are cut by pushing `vX.Y.Z` (E01-04). Protect the pattern so only
maintainers can tag:

```sh
gh api -X POST "repos/$OWNER/$REPO/tags/protection" -f pattern='v*'
```

## General

- [ ] Default branch: `main`
- [ ] Merge button: **squash only**; auto-delete head branches after merge
- [ ] Private repository (architecture for a critical-infrastructure system)
- [ ] Actions: allow `GITHUB_TOKEN` **read** by default; `release.yml` requests
      `packages: write` + `id-token: write` per-job
- [ ] Security: Dependabot alerts + security updates, secret scanning, **push
      protection**
- [ ] Environments: none required yet (a `release` environment with required
      reviewers is an option once GHCR publishing goes live)

## Open decisions

- **LICENSE**: not chosen. Corporate/OSS policy for DB InfraGO must be
  confirmed. Tracked in `.ai/CURRENT_STATE.md`.
- **Container registry**: GHCR per ADR-0014; confirm whether an internal mirror
  is required for the production pull path.
