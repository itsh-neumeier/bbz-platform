# ADR-0010: Safe Restricted Rule DSL

## Status
Proposed

## Context
EPK OR/XOR branch conditions (ADR-0005) and technical trigger-rule conditions
(ADR-0004) need admin-authored logic. `.ai` rules forbid `eval`/`exec` or any
dynamic code execution.

## Decision
- One shared package `bbz_rule_dsl` used by both the workflow engine and the
  trigger engine.
- Expressions are **structured data** (`{"op": ..., "args": [...]}`), not source
  strings — there is no code path that compiles or executes text.
- Fixed operator allowlist: `eq ne in not_in lt lte gt gte and or not exists`.
- Field references resolve only against an allowlisted, typed context
  (`ALLOWED_FIELDS`); unknown fields raise, they never silently pass.
- The evaluator is pure and total over its inputs; it is delivered with a
  property/fuzz test suite in Phase 1.
- Foundation phase ships the parser/validator + allowlists; `evaluate()` raises
  `NotImplementedError` rather than shipping a possibly-unsafe default.

## Consequences
- Admin logic is expressible without any RCE surface.
- New fields/operators require an ADR touch + code change (intentional friction).

## Alternatives considered
CEL / JSONLogic (viable but external surface and semantics we would still have to
constrain and audit); Python sandbox (rejected outright — no `eval`).
