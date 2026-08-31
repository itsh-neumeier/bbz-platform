# Coda Video (HxGN dC3 Video) Integration Baseline

## Product identity

The former planning name `Cayuga` refers to **Coda Video (formerly HxGN dC3 Video / Qognify VMS lineage)** in this project.

Use the canonical integration id:

`coda_video`

Legacy labels such as `Cayuga` may be retained only as migration/display aliases where required by an existing environment.

## Architecture rule

Coda Video is both:

1. a video/camera integration, and
2. an inbound alarm/event source for the BBZ technical-trigger engine.

Do not model it only as a camera launcher.

## Publicly known integration surfaces

Public product material indicates integration capabilities such as SDK, Event Interface, OPC interface, advanced alarm scenarios, intercom events and display-agent/video-wall functions depending on edition/licensing.

The detailed API/SDK contract is considered an external dependency and may require the vendor/partner portal.

Do NOT invent:

- endpoint URLs
- authentication schemes
- event payloads
- alarm acknowledgement methods
- camera object IDs
- display-agent commands
- SDK class names
- licensing assumptions

Implement only after official project documentation is supplied.

**Referenceable blocker (E16-13):**
[`docs/integrations/coda-video-pending.md`](../docs/integrations/coda-video-pending.md).
The `coda_video` manifest carries `"pending_vendor_documentation": [...]` for as
long as this stands.

## Normalized BBZ capabilities

The provider contract must support capability discovery. Possible normalized capabilities include:

### Video

- `video.health`
- `video.resolve_camera`
- `video.open_camera`
- `video.focus_camera`
- `video.open_camera_group`
- `video.open_alarm_context`
- `video.list_cameras` (admin/mapping only)

### Alarm ingress

- `alarm.subscribe`
- `alarm.resolve_source`
- `alarm.get_context`
- `alarm.get_associated_cameras`

Optional and only if official interface supports it:

- `alarm.acknowledge_external`
- `alarm.close_external`

BBZ event acknowledgement and external Coda alarm acknowledgement must remain separate domain actions.

## Alarm normalization

Every received Coda alarm must be normalized into an immutable provider event before trigger evaluation.

Minimum normalized fields:

- `provider = coda_video`
- `provider_event_id`
- `provider_alarm_id` if different
- `alarm_type`
- `alarm_subtype`
- `source_external_id`
- `source_name`
- `site_external_id`
- `occurred_at`
- `received_at`
- `severity_external`
- `state_external`
- associated camera references
- raw payload reference/hash for diagnostics
- provider instance id

The raw provider payload must not leak directly into core business rules.

## Überfallmeldeknopf / Duress / Panic alarm

A panic/duress alarm originating in Coda Video is a first-class technical trigger source.

Example normalized subtype:

`panic_button`

Alternative vendor-specific names are mapped in provider configuration and do not change the BBZ domain model.

Admin mapping must allow:

- external alarm/source ID -> BBZ technical endpoint
- station/site
- human-readable location, e.g. `ServicePoint Nürnberg Hbf`
- default BBZ priority, normally `CRITICAL`
- one or more associated cameras
- popup profile
- EPK workflow template + published version
- optional notification/escalation profile
- enabled/disabled

### Runtime flow

1. Coda provider receives alarm.
2. Persist/deduplicate provider event.
3. Resolve technical endpoint mapping.
4. Create exactly one BBZ event.
5. Assign configured priority.
6. Attach published EPK workflow version.
7. Push global critical/high warning.
8. Open/focus associated camera(s), if capability is available.
9. Show operator alarm popup with location/source.
10. Put event into Ereignisspeicher.
11. User accepts and acknowledges the BBZ event.
12. Workflow is executed and fully audited.

Camera-open failure must never suppress event creation or the operator alarm popup.

## Example technical endpoint

```yaml
name: Ueberfalltaster ServicePoint Nuernberg Hbf
provider: coda_video
source_external_id: CODA-ALARM-4711
type: panic_button
station: Nuernberg Hbf
default_priority: critical
workflow: UEBERFALL_SERVICEPOINT
camera_mappings:
  - CAM-SP-NBG-01
  - CAM-SP-NBG-02
enabled: true
```

This is a domain example only. It does not define the vendor API payload.

## Siedle / camera use case

A Siedle technical endpoint may map to one or more Coda cameras. On doorbell ring the trigger engine independently:

- creates/shows the doorbell popup
- requests the camera view

A Coda outage must not block the door-opening call workflow.

## HA and exactly-once behavior

Both active BBZ application nodes may observe/retry an external alarm. Therefore:

- require stable provider-event identity or construct a deterministic dedupe key from documented stable fields
- persist provider inbox before side effects
- unique trigger execution key
- durable outbox for BBZ side effects and optional external acknowledgement
- never create duplicate panic/BMA events after failover/retry

## Diagnostics

Admin diagnostics should show:

- provider health
- connectivity
- last event received
- last successful camera action
- configured alarm source count
- unmapped alarm count
- duplicate event count
- event processing latency
- capability list
- licensing/capability warnings if known from provider

## Testing

Provider mock must support simulation of:

- panic button alarm
- intrusion alarm
- generic technical alarm
- alarm with one associated camera
- alarm with multiple associated cameras
- unknown/unmapped source
- duplicate provider event
- provider reconnect and replay
- camera action failure while event creation succeeds
