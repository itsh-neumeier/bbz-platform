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
