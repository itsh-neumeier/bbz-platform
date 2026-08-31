# Siedle Door Station Integration Baseline

## Architecture decision

Initial Siedle control is implemented through the telephony provider, not through an invented Siedle HTTP API.

Siedle Access Professional supports door-opener control using configurable DTMF/MFV codes during telephone/SIP calls. The exact code is configuration, never hardcoded into BBZ business logic.

Cisco Unified JTAPI supports DTMF generation on a MediaTerminalConnection, so the CUCM telephony provider can expose a normalized `send_dtmf()` capability when the controlled call/media connection supports it.

**ADR-0025** settles where the code lives: BBZ's `door_action_profiles` table (Fernet-encrypted at rest, E17-02) is the config store. The door-open flow decrypts it transiently and passes the **sequence** — not a BBZ reference — to `send_dtmf(dtmf=…)`, because an integration cannot resolve a BBZ id (import boundary). The sequence is never persisted, logged, or put in an audit / event payload.

## Technical endpoint model

Each door station is a `technical_endpoint`, not a normal telephone-book contact.

Configuration:
- display name, e.g. `Klingel XYZ`
- station/site
- calling number / route match
- associated Cayuga camera mapping
- door-open DTMF secret/profile reference
- popup text
- timeout
- priority
- enabled

## Ring flow

1. CUCM/JTAPI emits incoming/ringing call.
2. Technical trigger engine matches caller/route to Siedle endpoint.
3. Server emits `DOORBELL_RINGING`.
4. Cayuga integration receives camera-open request for mapped camera.
5. Paired BBZ client receives a time-limited bottom-right popup: `Klingeln: <XYZ>`.
6. User can choose allowed actions, at minimum `Öffnen` and `Schließen/Ablehnen`; optional later `Sprechen/Annehmen`.

## Door-open flow

When user presses `Öffnen`:

1. authorize `door.open`
2. create idempotent door-open command
3. answer call if still ringing and provider/profile requires an active call
4. wait for CONNECTED/media-ready state
5. resolve the `door_action_profiles` row → decrypt transiently → call `send_dtmf(dtmf=<sequence>)` **exactly once** (derived `command_id`)
6. wait configured post-DTMF delay
7. automatically hang up (if the profile says so)
8. record audited result — `DOOR_OPEN_REQUESTED` / `DOOR_OPEN_RESULT`, carrying `door_action_profile_id`

The raw DTMF code must not be included in ordinary audit/event payloads.

Implemented by `DoorOpenService` + `POST /api/v1/doors/{endpoint_id}/open` (E17-05), idempotent on `X-Command-Id`, with a `door_open_commands` state machine. The real JTAPI/SIP `send_dtmf` transport is E12-05 / E13-06.

## Failure states

- caller no longer ringing
- media not available
- DTMF capability unavailable
- Cayuga unavailable
- duplicate command
- authorization denied
- telephony provider failover

The UI must show a clear result and must never silently retry an unlock side-effect without the same idempotency key.

## Permissions

- `technical_endpoints.view`
- `technical_endpoints.manage`
- `door.view`
- `door.answer`
- `door.open`
- `door.configure`
