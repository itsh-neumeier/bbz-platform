# integrations/

Home-Assistant-style plugin tree (MASTER_PROMPT §7). Each integration is a
self-contained directory and is **never imported by `bbz_core`** — the core only
loads manifests and (Phase 1+) adapters through `bbz_core.integrations_host`.
`import-linter` enforces this boundary in CI.

## Layout per integration

```
<name>/
  manifest.json        # validated against bbz_integration_sdk manifest schema
  config_schema.json   # JSON Schema for the integration's configuration
  __init__.py
  adapter.py           # implements the relevant provider Protocol(s)
  events.py            # vendor -> normalized event translation
  diagnostics.py       # health/diagnostics
  README.md
  tests/
```

## Status (Phase 0)

| Integration        | State            | Notes |
|--------------------|------------------|-------|
| `telephony_mock`   | mock scaffold    | in-memory, deterministic; conformance target |
| `monitor_mock`     | mock scaffold    | in-memory routing model |
| `coda_video`       | **mock only**    | video + alarm ingress mock. NO vendor API (ADR-0006) |
| `telephony_sip`    | placeholder      | Phase 5. Generic SIP, must not depend on Cisco |
| `telephony_cucm`   | placeholder      | Phase 5. Talks to `services/cucm-cti-gateway`; no JTAPI in Python (ADR-0002) |
| `monitor_weytec`   | placeholder      | Interface-only until Weytec API docs exist |
| `siedle`           | placeholder      | Phase 5/6. Door control via telephony + DTMF profile (ADR-0004) |
| `dwd`              | placeholder      | Phase 7. DWD open data; concrete endpoints chosen by ADR |

**No productive CUCM / Coda Video / Siedle / Weytec integration code is present.**
Placeholders contain a README and (where useful) a manifest, nothing else.
