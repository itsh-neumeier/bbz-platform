# Integration health

Roadmap **E22-05**, MASTER_PROMPT §23 / §8.14, §14 (`integration_health`).

`GET /api/v1/integrations/health` — one uniform row per **active** integration
(the one configured for its domain via `BBZ_<domain>_INTEGRATION_ID`). Needs
`integrations.diagnostics`. No secret is in the body.

```json
{
  "integrations": [
    {
      "integration_id": "coda_video", "domain": "video",
      "state": "ok",
      "summary": "mock",
      "checked_at": "2026-09-02T09:00:00Z",
      "last_ok_at": "2026-09-02T09:00:00Z",
      "last_error_at": null,
      "consecutive_errors": 0,
      "last_activity_at": "2026-09-02T08:57:11Z",
      "details": { "sources": 2, "pending_alarms": 0 }
    }
  ]
}
```

| field | meaning |
|---|---|
| `state` | normalised: `ok` \| `degraded` \| `down` \| `disabled`. Mapped from the provider's SDK `HealthState` (`healthy→ok`, `unavailable→down`, `unknown→down`). |
| `summary` | the provider's one-line note (or the probe error). |
| `checked_at` / `last_ok_at` / `last_error_at` | when the integration was last probed / last `ok` / last failing. |
| `consecutive_errors` | probes in a row that were not `ok`/`disabled` — the signal an alert rule watches (E22-06). Resets to `0` on the next good probe. |
| `last_activity_at` | best-effort: the newest `provider_event_inbox` row keyed by this integration id. `null` for an integration that only sends (weather / monitor). |
| `details` | the provider's own non-secret `health().details`, run through the redaction net. |

## How it stays current

- `GET /integrations/health` **live-probes** every active provider (`health()`,
  5 s-bounded, in parallel), upserts `integration_health`, then returns the
  table — so a fault shows immediately.
- The leader-elected **`integration-health`** singleton runs the same refresh
  every `BBZ_INTEGRATION_HEALTH_INTERVAL_SECONDS` (default 60) so the table is
  current for alert rules even with no operator watching.

## Related

- The E22-02 metric `bbz_integration_health{domain,integration}` is the same
  signal as a gauge (`docs/metrics.md`).
- The deep per-integration view is `…/integrations/coda_video/diagnostics`
  (E16-10) and, when Epic 12 lands, a CUCM-specific one (E12-15) — both feed
  their `state` into this table as another `(domain, id)` pair, no schema change.
