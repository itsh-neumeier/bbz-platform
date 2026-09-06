# telephony_sip

Vendor-neutral SIP telephony provider — simple SIP trunks, alternative PBX,
lab/test, migration/fallback, other vendors. The core only ever speaks the
normalized `TelephonyProvider` interface.

**Independent of Cisco.** Must not import `integrations.telephony_cucm` or any
Cisco-JTAPI binding (ADR-0002 §8.17) — enforced by the import-linter contract
*"telephony_sip is independent of Cisco CUCM / JTAPI"*.

## Status — ARI transport (E13-03)

| Issue | What | State |
|---|---|---|
| E13-02 | ADR-0023: Asterisk (ARI) vs. FreeSWITCH (ESL) | done |
| E13-03 | ARI transport (`ari.py`) — REST + WS, health probe | done |
| E13-04 | ARI events → normalized `CallEvent` (`events.py`) + the pump | done |
| E13-05 | call control (dial / answer / hangup / hold / resume / transfer / conference) | done |
| E13-06 | DTMF → `send_dtmf` (ARI `channels/{id}/dtmf`, never logged) | **done** |
| E13-07 | config schema + secrets | schema done; DB config = ADR-0033 (next) |
| E13-08 | integration tests against a `sip`-profile Asterisk container | **done** (nightly) |

`ari.py` is the transport: `AriClient` opens a `httpx` REST session + an ARI
event WebSocket (`Authorization: Basic` header, never credentials in a URL),
reconnects with backoff. `events.py` maps ARI channel events →
`telephony_event.v1` (`StasisStart`→`CALL_RINGING`, `ChannelStateChange(Up)`→
`CALL_ANSWERED`, `StasisEnd`/`ChannelHangupRequest`→`CALL_DISCONNECTED`,
`PeerStatusChange`→`DEVICE_REGISTERED/UNREGISTERED`); `source_call_id` is the SIP
Call-ID (`SIPCALLID` channel var) or the ARI channel id.

`initialize()` starts a pump task that buffers the mapped events; the new
`telephony-events` cluster singleton drains them each tick through
`ingest_telephony_event` (the pump E11-05 never wired — the mock provider is
skipped there, it stays endpoint-driven for E2E).

The control verbs (`answer` / `hangup` / `hold` / `resume` / `dial` / `transfer`
/ `conference`) drive ARI: the pump keeps a `source_call_id → ARI channel id`
map, each verb is **idempotent on `command_id`** (mirrors the mock's `_seen`
cache), an unreachable gateway or an untracked call returns
`CommandAccepted(accepted=False, detail=...)` rather than raising. `dial`
originates against `PJSIP/<line>` (or the explicit `line_endpoints` map).
`send_dtmf` emits the BBZ-resolved sequence (ADR-0025) via ARI's
`channels/{id}/dtmf` — never logged, echoed in the ack, or in an error
(ADR-0004); idempotent so a replay does not open the door twice.

## Integration tests (E13-08)

`deploy/sip/` is a throwaway lab Asterisk (`docker compose --profile sip up
--build`). `tests/test_sip_integration.py` exercises the whole adapter against
real ARI — an inbound Stasis call, answer/hold/resume/hangup with the matching
normalized events, `command_id` idempotency, redaction-safe DTMF, outbound
`dial`, blind transfer, and a reachability-loss health check. It is **skipped**
unless an ARI endpoint answers (`BBZ_TEST_ARI_HOST`, default `127.0.0.1:8088`),
so it never runs in the `backend` job. `.github/workflows/sip-nightly.yml` runs
it nightly (`continue-on-error` until shaken out on real hardware). See
`.ai/TESTING.md` and `deploy/sip/README.md`.

## Config

See `config_schema.json`. **Production** stores the gateway config — including
the ARI password, encrypted at rest — in the DB, managed from the admin UI
(**ADR-0033**). **Dev / CI / file-provisioned** instances may pass
`credentials` inline or a `credentials_secret_ref` into the secret store. The
raw DTMF code is a secret too; only the profile id is handled here (ADR-0004).
