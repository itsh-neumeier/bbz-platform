# ADR-0006: Coda Video as Video and Alarm Source

## Status
Accepted

## Context
The BBZ platform uses Coda Video (formerly HxGN dC3 Video) for video operations. Alarm sources such as physical panic/duress buttons may also arrive through Coda and must start BBZ workflows.

## Decision
- Canonical provider id is `coda_video`.
- Coda is modeled as both video provider and alarm-event provider.
- Raw provider events are persisted/deduplicated before trigger execution.
- Panic/duress alarms may automatically create configured BBZ events and bind a published EPK workflow version.
- Associated cameras may be opened as a separate side effect.
- Camera/display failures never suppress the BBZ alarm event.
- External Coda acknowledgement, if later supported, remains separate from BBZ acknowledgement.
- Exact API/SDK calls are implemented only from official project/vendor documentation.

## Consequences
- Physical alarm buttons can be integrated without hard-coded special cases.
- HA replay/reconnect is safe against duplicate BBZ events.
- Vendor changes stay inside the integration adapter.
