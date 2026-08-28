# ADR-0007: Monorepo Layout and Tooling

## Status
Accepted (2026-08-29, review E01-01 / #20)

## Context
The platform spans a Python backend, shared Python packages, pluggable
integrations, a Java CTI gateway, a Vue web app, an Electron client, and two
native agents. All must be versioned together with traceable history
(MASTER_PROMPT §0/§18) and reproducible builds.

## Decision
- One Git repository. Top-level trees: `server/`, `packages/`, `integrations/`,
  `services/`, `apps/`, `agents/`, `deploy/`, `docs/`, `tools/`, `.ai/`.
- Python: per-component `pyproject.toml` (setuptools); a root `pyproject.toml`
  centralizes ruff/mypy/pytest/import-linter; `requirements-dev.txt` wires
  editable installs. (Revisit `uv` workspaces once available in CI.)
- JavaScript: npm workspace rooted at `apps/web` for now; widen to a repo-level
  workspace when a second JS package appears.
- Task shortcuts in `justfile`; every recipe is also a plain documented command.
- Architecture boundaries (`core` ↛ `integrations`, `api`/`domain` ↛ SDK) are
  enforced in CI by `import-linter`.

## Consequences
- Atomic cross-cutting changes; single CI.
- Some polyglot friction in one pipeline (mitigated by per-language jobs).
- No Python-native workspace tool yet → editable installs are explicit.

## Alternatives considered
Polyrepo (rejected: cross-cutting changes and shared contracts become painful);
Nx/Turborepo (rejected for now: adds a heavy JS-centric layer before it pays off).
