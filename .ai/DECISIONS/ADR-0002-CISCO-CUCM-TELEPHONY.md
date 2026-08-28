# ADR-0002: Cisco CUCM Telephony Integration via JTAPI Gateway

## Status
Accepted for architecture baseline

## Context

The BBZ requires enterprise-grade Cisco telephony integration while preserving an open provider model.

Cisco Unified Communications Manager provides multiple interfaces with different purposes:
JTAPI/TAPI for CTI call control, AXL for provisioning/configuration, Serviceability/RisPort
for registration/health, and UDS for user/device directory functions.

The BBZ core is Python/FastAPI, while Cisco JTAPI is Java-based.

## Decision

1. Cisco Unified Communications Manager is represented by provider `telephony_cucm`.
2. Real-time call control uses Cisco JTAPI through a dedicated Java service `cucm-cti-gateway`.
3. AXL is used only for configuration/provisioning and inventory.
4. RisPort70 is used for device/application registration health.
5. UDS is optional for directory/user/device enrichment.
6. CDR is optional for post-call reconciliation, not live control.
7. Both BBZ servers run a gateway container.
8. A distributed lease elects one logical `CONTROL_LEADER` for mutating CTI commands.
9. JTAPI's own redundant CTI Manager support is configured with multiple CUCM subscriber nodes.
10. The first production mode is third-party control of existing Cisco endpoints; media stays on Cisco endpoints.
11. Generic SIP remains a separate provider and fallback/alternative architecture.
12. Cisco proprietary JTAPI binaries are not committed to public source control.

## Consequences

Benefits:
- enterprise-standard CUCM CTI integration
- fast CTI events and full call-control semantics
- clear provider isolation
- redundant CTI Manager connectivity
- no Cisco classes in BBZ core
- continued vendor-neutral SIP option

Costs:
- Java 8 gateway component
- CUCM version/JTAPI compatibility management
- additional secrets/certificates
- dedicated HA leadership for control commands
