# Rate limiting

Roadmap **E23-04**, MASTER_PROMPT §22. `bbz_core.infra.rate_limit` +
`bbz_core.api.rate_limit`.

## How it works

A **cluster-wide fixed window**: `rate_limit_hits` (migration 0052) holds one
row per `(bucket, window_start)`; each hit is an indexed
`INSERT … ON CONFLICT DO UPDATE count = count + 1 RETURNING count`. Both app
nodes write the same rows, so a threshold is enforced across the cluster (an
E23-04 AC). The count resets when the window rolls over; a bucket's stale rows
are dropped on its first hit in a new window.

Over the limit ⇒ **`429`** with a `Retry-After` header (seconds to the end of the
window) and the uniform error body (`code: "rate_limited"`).

The limiter **fails open** — if it cannot reach its store it logs
`rate_limit_store_unavailable` and allows the request. A limiter that 500s the
endpoint is worse than one that occasionally under-limits.

## Rules

| rule | applied to | key | default (`limit/seconds`) |
|---|---|---|---|
| `login` | `POST /api/v1/auth/login` | client IP (`X-Forwarded-For`, else peer) | `10/60` |
| `mfa` | `POST /api/v1/auth/totp/activate`, `POST /api/v1/auth/mfa-policies/step-up` | `user:<id>` | `8/60` |
| `password_reset` | `POST /api/v1/users/{id}/password-reset` | `user:<id>` (the admin) | `5/300` |
| `webhook` | `POST /api/v1/telephony/events` | client IP | `240/60` |

Each is `BBZ_RATE_LIMIT_<RULE>` — set the limit to `0` to disable that rule.

`login`, `mfa` and `password_reset` also write a `RATE_LIMIT_TRIGGERED` audit
row when they trip — the rule name, the identifier and the count, **never the
attempted credential**. It is a critical action.

The per-user login **lockout** (5 failed passwords → 15 min, E02-03) is
separate and complementary — that is per account, this is per source.

## Not in scope

Network-layer DDoS / a WAF — that is the reverse proxy's / the edge's job
(`.ai/SECURITY.md`). A general per-request API bucket is deliberately not added
here; the abuse-prone endpoints are covered explicitly.
