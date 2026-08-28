# Technical Endpoints & Trigger Engine

## Goal

External signals can originate from people/contacts, telephony-connected technical devices, video-management alarms, building/security systems, or future integrations.

Technical systems are not normal phonebook contacts.

Examples:

- Siedle door station via CUCM
- Brandmeldeanlage (BMA) via dedicated phone number
- Coda Video panic/duress button alarm
- Coda Video intrusion or technical alarm
- future technical alarm dialers or APIs

## Domain separation

`contacts` = human/organizational telephone-book entries.

`technical_endpoints` = configured technical sources with trigger behavior.

A technical endpoint may contain:

- id
- name
- site/station
- type (`door_station`, `bma`, `panic_button`, `video_alarm`, `alarm_dialer`, custom)
- provider/integration id
- external source identifiers
- calling/called number patterns where telephony-based
- default priority
- popup profile
- associated camera mappings
- workflow template + version selection policy
- escalation profile
- enabled
- active configuration version

## Provider-neutral inbound signal

All integrations normalize their input to a common structure before business-rule evaluation.

Examples:

- `CALL_RINGING`
- `TECHNICAL_ALARM_RAISED`
- `PANIC_ALARM_RAISED`
- `DOORBELL_RINGING`
- `BMA_ALARM_CALL`

The Core does not inspect raw Cisco/Coda/Siedle vendor payloads.

## Trigger Rule

Rules are admin-configurable and versioned.

Conditions may use allowlisted normalized fields such as:

- provider
- normalized signal type
- calling number / ANI
- called number / DNIS
- CTI route point
- technical endpoint ID
- external source mapping
- workplace/site/station
- alarm subtype
- severity mapping
- call direction/state
- time window where justified

Actions are typed, not arbitrary scripts:

- `create_event`
- `attach_workflow`
- `show_client_popup`
- `integration_action`
- `open_camera`
- `open_camera_group`
- `answer_call`
- `send_dtmf_profile`
- `hangup_call`
- `notify`
- `launch_catalog_app` (policy-controlled)

## Panic/duress alarm rule

The admin UI must support a rule such as:

`Coda source XYZ -> CRITICAL event -> workflow UEBERFALL -> cameras A/B -> popup`

This is configuration, not hard-coded business logic.

## Active/Active exactly-once protection

Both BBZ app nodes may receive/observe the same external event. Therefore:

- inbound provider events require stable `provider_event_id` where available
- durable provider inbox/deduplication table
- rule execution key = `provider_event_id + rule_version + action_index`
- durable outbox for external side effects
- unique constraints / command idempotency

Door unlock, BMA creation or panic-event creation must never happen twice after retry/failover.

## Admin UI

Admin area provides:

1. Technical endpoints
2. Provider/source matching
3. Number/route matching where relevant
4. Trigger profiles
5. Action sequence
6. Event type/priority
7. Workflow template/version selection
8. Integration mapping (e.g. Coda cameras)
9. Test/simulation mode without real side effects
10. Draft -> Validate -> Publish -> Retire lifecycle
11. Unmapped-source queue for diagnostics/admin mapping

Published versions are immutable. New changes create a new version.
