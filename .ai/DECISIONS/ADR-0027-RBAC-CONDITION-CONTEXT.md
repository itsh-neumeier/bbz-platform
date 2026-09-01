# ADR-0027: RBAC condition context — which fields a `role_permissions.condition` may reference

## Status
Accepted (2026-09-01, review E21-07 / #443)

## Context
E02-07 added `role_permissions.condition` (a Rule-DSL expression, ADR-0010) but
left it inert: `authorization.resolver._condition_allows` evaluates it only when
`rbac_conditions_enabled` is set, and even then against an **empty context**, so
every non-trivial condition denied. E21-07 makes conditional grants functional.

ADR-0010 §Consequences: *"New fields/operators require an ADR touch + code change
(intentional friction)."* A condition on an authorization grant is evaluated on
the hot path of **every** permission check, so the field set must be small,
cheap to compute, and free of anything that could vary within a request or leak
data across the boundary.

## Decision
A new `bbz_rule_dsl.context.RBAC_CONTEXT` schema. A `role_permissions.condition`
may reference **only** these fields:

| field | type | value |
|---|---|---|
| `now.hour` | number | server hour of day, 0–23 (UTC — ADR-0017) |
| `now.weekday` | number | 0 = Monday … 6 = Sunday (UTC) |
| `now.iso` | string | `YYYY-MM-DDTHH:MM:SS+00:00` (for range compares) |
| `scope` | string | the scope key of the grant being checked |

- The context is built per check in `_condition_allows` from `datetime.now(UTC)`
  and the grant. It is **pure** and total — a missing input resolves to `""` /
  `0`, never raises.
- It has no request-derived fields (client/workplace) yet: the scope-agnostic
  `authorize()` has no request context, and the primary use case ("this
  permission only during business hours") needs only the clock. Adding a
  request field later is another ADR touch here.
- Both `authorize()` (scope-agnostic) and `authorize_scoped()` evaluate the
  condition — a conditional grant that fails its condition does not grant the
  permission on either path.
- The condition JSON is validated with `RBAC_CONTEXT.validate(...)` at **write
  time** (RBAC admin `PUT /roles/{id}/permissions`); an invalid expression is a
  422, never a stored-but-broken grant.
- Evaluation stays gated by `rbac_conditions_enabled` (default **off**): turning
  it on is a deliberate operator choice, and a grant with a condition still
  **denies** whenever the flag is off, the expression fails to parse, or
  evaluation raises. A condition can only ever *narrow* a grant.
- Time-bound grants (`user_roles.valid_from` / `valid_to`) and delegations
  (`permission_delegations`) are **not** DSL conditions — they are plain columns
  filtered in the grant store, so they work regardless of the flag.

## Consequences
- Conditional grants express "this permission only during business hours / only
  from this workplace" without any RCE surface (ADR-0010 holds).
- Adding a field later (e.g. a user attribute) needs another ADR touch here.
- The check path does one `datetime.now()` and a small dict build per grant with
  a condition — negligible, and only when the flag is on.

## Alternatives considered
- **Richer context (user attributes, group membership, request IP).** Deferred —
  each is a data-exposure / performance question of its own; start with the
  time/workplace fields the operational use cases actually need.
- **Always-on evaluation.** Rejected for now: flipping a security default
  silently is exactly what ADR-0010's friction clause guards against; an
  operator opts in when they author their first condition.
