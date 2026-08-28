# Contributing

This repository is multi-AI and human friendly. `AGENTS.md` and `.ai/**` are the
vendor-neutral source of truth and **override** convenience.

## Before any task

1. Read `AGENTS.md`, `.ai/WORKSPACE.md`, `.ai/ARCHITECTURE.md`, `.ai/RULES.md`,
   `.ai/CURRENT_STATE.md`, `.ai/TASK_PROTOCOL.md`, and the relevant ADRs.
2. If the task changes an architecture decision → open/adjust an ADR first. No
   silent architecture changes.

## Workflow (never bypass)

```
GitHub Issue → feature|fix|refactor|docs/<issue>-<short-name> → commits → tests → PR → review → merge
```

- Never commit directly to `main`. No force-push to `main`.
- Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`,
  `ci:`, `build:`, `perf:`, `revert:`).
- The PR template sections are mandatory (`.github/PULL_REQUEST_TEMPLATE.md`).
- Update `.ai/CURRENT_STATE.md` in the same PR.

## Local checks

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt   # or .venv/bin/pip
ruff check . && ruff format --check .
mypy server/bbz_core packages/*/bbz_*
lint-imports
pytest
```

Frontend (`apps/web`, needs Node ≥ 20):

```bash
cd apps/web && npm install && npm run lint && npm run typecheck && npm run test
```

## Non-negotiables (`.ai/RULES.md`)

- Permissions enforced server-side; never frontend-only.
- Every state-changing API is idempotent; every critical change writes audit.
- Archived events are never hard-deleted; reactivation needs explicit confirmation.
- Calls require a documentation category.
- Integration code stays out of the core domain (enforced by `import-linter`).
- Never invent an external vendor API. Accessibility is a functional requirement.
