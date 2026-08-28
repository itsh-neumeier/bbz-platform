# Runbook: rolling update

> Stub — completed in Phase 2 when the HA stack exists (ADR-0001). Documented now
> so the deploy shape is fixed.

MASTER_PROMPT §21 order:

1. Verify cluster healthy: `/cluster/status` on both nodes, etcd quorum, no
   replication lag alarm.
2. Verify DB migration is expand/migrate/contract and **N-1 backward compatible**
   (the currently-running version must keep working with the new schema).
3. Update **SRV02**: deploy new image digest.
4. Health-gate: `/health/ready` green on SRV02, smoke checks pass.
5. Update **SRV01**.
6. Re-check cluster health.

**Abort criteria:** any health-gate fails, replication lag grows, or error rate
rises → stop, redeploy the previous digest on the updated node, see
`rollback.md`.
