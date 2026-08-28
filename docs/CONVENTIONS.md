# Coding conventions

Binding. `.ai/RULES.md` and the ADRs win over anything here.

## Module boundaries (enforced by `import-linter`)

- `bbz_core.domain` imports nothing else in `bbz_core` and never
  `bbz_integration_sdk`. It defines its own interfaces (dependency inversion).
- Only `bbz_core.integrations_host` imports `bbz_integration_sdk`.
- `bbz_core` never imports anything under `integrations/`.
- Concrete integrations never import each other; `telephony_sip` must not depend
  on Cisco/JTAPI or `telephony_cucm`.

## API / commands

- Base path `/api/v1`. See ADR-0012 for the command envelope, error body,
  409-on-conflict and idempotency rules.
- Every write is idempotent on `command_id`. Every critical state change writes
  an audit event in the same transaction (ADR-0011).
- Permissions checked server-side, always. Never frontend-only.

## Events & time

- Ordering / catch-up / conflict resolution use `event_seq`, never timestamps.
- All instants are UTC in storage and payloads (ADR-0017).
- Event envelope shape: `packages/event-schemas` — bump `schema_version` on
  changes; additive within a major.

## Naming

- Python: `snake_case`; packages `bbz_*`. Vue components `PascalCase`; stores
  `useXStore`. Integration ids `lower_snake` (`telephony_cucm`, `coda_video`).
- Branches: `feature|fix|refactor|docs/<issue>-<short-name>`.
- Commits: Conventional Commits.

## Vendor integrations

- Never invent an external API. If docs are missing, the integration stays a
  placeholder + mock and the gap is listed in `.ai/CURRENT_STATE.md`.
- Vendor payloads are normalized at the integration edge; the core only sees
  BBZ-defined normalized events.

## Accessibility

- Functional requirement. Keyboard path for every operable control; respect
  `prefers-reduced-motion`; a11y lint at error level.

## Secrets

- Nothing sensitive in the repo. Config via `BBZ_`-prefixed env; secrets via the
  orchestrator/secret store. Never log DTMF codes or key material (ADR-0015).
