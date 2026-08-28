# Siedle Door Station Integration Baseline

## Architecture decision

Initial Siedle control is implemented through the telephony provider, not through an invented Siedle HTTP API.

Siedle Access Professional supports door-opener control using configurable DTMF/MFV codes during telephone/SIP calls. The exact code is configuration, never hardcoded into BBZ business logic.

Cisco Unified JTAPI supports DTMF generation on a MediaTerminalConnection, so the CUCM telephony provider can expose a normalized `send_dtmf()` capability when the controlled call/media connection supports it.

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
5. call telephony provider `send_dtmf(dtmf_profile_id)`
6. wait configured post-DTMF delay
7. automatically hang up
8. record audited result

The raw DTMF code must not be included in ordinary audit/event payloads.

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
