# Advanced RBAC — conditions, time-bound grants, delegation (E21-07)

## Conditions on a role's permissions

A `role_permissions` row can carry a `condition` — a Rule-DSL expression
(ADR-0010) that must be true for the grant to apply. A condition can only
**narrow** a grant; it never widens one.

- **Off by default.** Set `BBZ_RBAC_CONDITIONS_ENABLED=true` to activate. While
  off, a grant that has a condition simply does not apply.
- **Fields** (ADR-0027 — clock only): `now.hour` (0–23, UTC), `now.weekday`
  (0=Mon…6=Sun), `now.iso`, `scope` (the grant's scope key).
- Validated when you save it (`PUT /api/v1/roles/{id}/permissions`) — a bad
  expression is a 422, not a stored-but-broken grant.
- Any evaluation failure (flag off, parse error, exception) is a **deny**.

Example — "events.takeover only during the 07:00–19:00 shift, Mon–Fri":

```json
{ "op": "and", "args": [
  { "op": "gte", "args": [{ "field": "now.hour" }, 7] },
  { "op": "lt",  "args": [{ "field": "now.hour" }, 19] },
  { "op": "in",  "args": [{ "field": "now.weekday" }, [0, 1, 2, 3, 4]] }
]}
```

## Time-bound role assignments

`POST /api/v1/users/{user_id}/roles` accepts optional `valid_from` / `valid_to`
(timestamptz). Outside the window the grant is not returned by the permission
check — no scheduled cleanup needed, it just stops being effective. `valid_to`
before `valid_from` → 422.

## Permission delegation

`permissions.manage` holders can lend one of **their own** permissions to another
user for a bounded time.

| | |
|---|---|
| `POST /api/v1/permissions/delegations` `{to_user_id, permission_key, expires_at, scope?}` | create — you must currently hold `permission_key` |
| `GET /api/v1/permissions/delegations?active_only=` | delegations you gave or received |
| `DELETE /api/v1/permissions/delegations/{id}` | revoke |

- `expires_at` is required — a delegation always expires.
- A revoke or expiry takes effect on the delegatee's **next request** (the
  permission service reads the DB per request; there is no cross-request cache).
- Both actions audit — `PERMISSION_DELEGATED` / `PERMISSION_DELEGATION_REVOKED`
  (critical actions).

Not built: approval workflows for delegations.

---
Referenced from `.ai/SECURITY.md`, `.ai/CURRENT_STATE.md`, and ADR-0027.
