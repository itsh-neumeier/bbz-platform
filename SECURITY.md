# Security Policy

## Reporting a vulnerability

Do **not** open a public issue. Use GitHub's private security advisory:
<https://github.com/itsh-neumeier/bbz-platform/security/advisories/new>.

## Scope notes

Detailed security requirements live in `.ai/SECURITY.md` and the relevant ADRs.
Highlights enforced from the foundation onward:

- No secrets in the repository. `.gitignore` blocks key material; `gitleaks` runs
  in CI and as a pre-commit hook.
- No arbitrary shell / URL execution endpoints (agents use a typed allowlist).
- Door-control DTMF codes and similar are secrets — audit stores the action
  profile id, never the code.
- Containers run as non-root.
- Server-side RBAC only; every critical action produces an immutable audit entry.
