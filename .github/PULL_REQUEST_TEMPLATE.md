<!-- TASK_PROTOCOL.md: every PR must include all sections below. -->

Closes #

## Problem

## Solution

## Files / modules

## Tests
<!-- what was added/changed; how it was run; results -->

## Security impact
<!-- authz, secrets, audit, attack surface. "none" is a valid answer with a reason. -->

## HA impact
<!-- active/active, idempotency, event_seq/catch-up, failover. "none" is valid with a reason. -->

## Rollback
<!-- how to revert; migration reversibility; feature-flag if any -->

## ADR impact
<!-- none / new ADR #### / updates ADR #### -->

## Checklist
- [ ] No direct commit to `main`; branch follows `feature|fix|refactor|docs/<issue>-<name>`
- [ ] Conventional Commit messages
- [ ] `ruff check` · `ruff format --check` · `mypy` · `lint-imports` · `pytest` green
- [ ] Frontend `lint` · `typecheck` · `test` green (if `apps/web` touched)
- [ ] No invented external vendor API
- [ ] No silent removal of existing functional behavior
- [ ] `.ai/CURRENT_STATE.md` updated
- [ ] Docs updated
