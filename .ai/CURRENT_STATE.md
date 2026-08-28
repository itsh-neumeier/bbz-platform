# .ai/CURRENT_STATE.md

## Current phase
Planning / Bootstrap

## Existing reference
A functional HTML mockup exists and defines important UX/feature behavior.

## Implemented in production code
None yet.

## Next target
Phase 0 Repository Foundation.

## Open external dependencies
- genaue Cisco CUCM-Version/SU und produktive Cluster-/CTI-Konfiguration
- Weytec API documentation
- Coda Video (HxGN dC3 Video) partner/API/SDK documentation for alarm ingress and camera/display control

CUCM wird auf dokumentierten JTAPI/AXL/RisPort/UDS-Schnittstellen aufgebaut. Keine kundenspezifische CUCM-Konfiguration oder Weytec-API erfinden.

## Newly accepted planning requirements
- BKU Agent architecture
- centrally managed operational app/link catalog
- technical telephony endpoints/triggers
- Siedle DTMF door-opening process
- Cayuga camera trigger integration
- BMA call-to-event automation
- graphical EPK workflow engine with AND/OR/XOR

- Coda Video panic/duress alarm ingestion mapped to BBZ event + EPK workflow
