# bbz-client-agent (PLACEHOLDER — no code)

Local service on the BBZ workplace PC. **Not implemented in Phase 0** (Phase 4).

Responsibilities (MASTER_PROMPT §6): server discovery, health checks
(`/health/live`, `/health/ready`, `/cluster/status`), failover SRV01↔SRV02
carrying the last `event_seq`, encrypted local cache, offline outbox, client
certificate, kiosk process supervision.

Implementation language (Go vs. Rust) is decided in **ADR-0009**. Nothing about
the agent's on-wire protocol is invented before that ADR and the Phase-1 command
envelope are settled.
