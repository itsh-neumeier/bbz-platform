# .ai/TESTING.md

Required test levels:
- unit
- integration
- API
- authorization
- frontend
- E2E
- HA/failover
- recovery/catch-up
- migration/rollback

Critical flows:
- event ownership
- archive/reactivation
- call documentation
- contact priorities
- failover
- client reconnect


Additional critical tests:
- BKU Agent enrollment and workplace binding
- agent failover SRV01 -> SRV02
- allowlisted web-app launch
- arbitrary URL/shell command rejection
- remote logout/restart confirmation + authorization + audit
- duplicate command replay rejection
- Siedle ring -> technical endpoint match -> Cayuga action -> BBZ popup
- door-open -> call connect -> DTMF -> automatic hangup (exactly once)
- duplicate Cisco call event does not trigger a second unlock
- BMA technical number creates exactly one event and binds workflow version
- EPK AND split/join
- EPK XOR split/join
- EPK OR split/join
- workflow publish validation and version pinning


## HA failure-scenario harness (E06-11)

`deploy/ha-test/` brings up a single-host mini HA cluster (2 app nodes, a
Patroni primary/standby behind HAProxy, a 3-member etcd, a Caddy LB) and runs
seven repeatable scenarios via `deploy/ha-test/run.sh`:

- `srv01-down`, `srv02-down` — an app server is lost; the LB keeps serving,
  writes continue, the returning node catches up.
- `db-primary-loss` — the PostgreSQL primary is killed; Patroni promotes the
  standby within the RTO (ADR-0021); `event_seq` never regresses.
- `net-isolation` — one server is network-isolated; the other keeps quorum and
  serves; the isolated node never becomes a second primary.
- `witness-down` — the etcd witness is lost; 2/3 quorum keeps the cluster
  writable.
- `client-reconnect` — a streaming client's node dies; it reconnects to the
  other node with its last `event_seq` and gets a gap-free continuation
  (E06-07).
- `recovery` — a full cluster restart converges to one primary and loses
  nothing.

`assert_single_primary` runs after every fault — **two Patroni leaders is
always a failure** (split brain). CI: `.github/workflows/ha-nightly.yml`
(scheduled, non-gating until shaken out on real hardware).
