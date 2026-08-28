# ADR-0008: Backend Stack and Module Boundaries

## Status
Proposed

## Context
MASTER_PROMPT §6 recommends Python/FastAPI for a Home-Assistant-like integration
model. The foundation needs the stack pinned and the internal layering made
enforceable before domain code is written.

## Decision
- Stack: Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2.x async, Alembic,
  PostgreSQL, structlog, pytest. OpenTelemetry prepared (no-op seam).
- Layering inside `bbz_core`:
  - `domain/` — pure: entities, value objects, domain services, domain events,
    policy. Depends on nothing else in `bbz_core`.
  - `infra/` — DB, repositories, event store, outbox/inbox.
  - `integrations_host/` — the only place allowed to import `bbz_integration_sdk`.
  - `api/` — HTTP; may use `domain` and `infra`, not the SDK directly.
  - `workflow_engine/` — EPK runtime (ADR-0005).
- Enforced by `import-linter` contracts in the root `pyproject.toml`.
- Test coverage gate rises to ≥ 90% line/branch on `domain`, `authorization`,
  rule DSL and the workflow engine when Phase 1 starts; foundation floor is 70%.

## Consequences
- Dependency-inversion discipline from day one; integrations cannot leak into
  domain logic.
- Slightly more boilerplate (interfaces defined by the domain).

## Alternatives considered
Django (rejected: heavier, ORM-centric, less natural for the integration/event
model); Node/Nest for a single language with the frontend (rejected: Python is
the better fit for adapters and the CTI/AXL ecosystem tooling).
