# cucm-cti-gateway (PLACEHOLDER — no code)

Separate **Java** service that encapsulates Cisco **JTAPI / CTI Manager** and
translates Cisco-specific objects into the BBZ **normalized telephony event
model** (`packages/event-schemas/.../telephony_event.v1.json`). See **ADR-0002**
and `.ai/INTEGRATIONS_CUCM.md`.

**Not implemented in Phase 0.** No productive CUCM integration exists yet.

## Planned layout

```
src/  tests/  api/  jtapi/  state/  health/  Dockerfile
```

## Hard rules

- Java 8-compatible OpenJDK, chosen to match the **productive CUCM SU / JTAPI
  compatibility matrix** (captured during onboarding).
- The rest of the BBZ system never sees Cisco/JTAPI classes.
- Cisco proprietary `jtapi.jar` is **never committed**. It is supplied at deploy
  time from an authorized internal artifact store or as a secret/volume mount.
  See `libs/README.md`.
- Both BBZ servers run a gateway container; exactly one holds the
  `CONTROL_LEADER` lease (etcd/Consul) and may issue mutating CTI commands.
- Mock mode first: the gateway must run without a real CUCM for CI/dev.
