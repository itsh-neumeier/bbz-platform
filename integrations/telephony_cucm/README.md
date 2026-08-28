# telephony_cucm (PLACEHOLDER — no code)

Cisco Unified Communications Manager provider. **Not implemented in Phase 0.**

Design is fixed by **ADR-0002** and `.ai/INTEGRATIONS_CUCM.md`:

- Real-time call control uses Cisco **JTAPI** via a **separate Java service**
  `services/cucm-cti-gateway`. This Python adapter will speak the gateway's
  normalized HTTP/stream API only — **no JTAPI classes in Python**.
- AXL (provisioning/inventory), RisPort70 (registration health), UDS (optional
  directory), CDR (optional reconciliation) are separate concerns.
- Exactly one `CONTROL_LEADER` per CUCM cluster (etcd/Consul lease) issues
  mutating commands; the standby stays warm.

## Blocked on external input (see `.ai/CURRENT_STATE.md`)

Exact CUCM version/SU, cluster topology, CTI Manager nodes, BBZ DNs, numbering
plan, CSS/partitions, security mode, Application-User approval, certificate
chain. No Cisco API details are invented before this is supplied.

## Not committed here

Cisco proprietary `jtapi.jar` is never checked into source control — see
`services/cucm-cti-gateway/libs/`.
