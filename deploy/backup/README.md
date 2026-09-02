# deploy/backup — encrypted backup + restore

Roadmap E06-14, MASTER_PROMPT §20/§24. Both state stores are backed up,
encrypted, and the restore is tested.

```
deploy/backup/
  common.sh            gpg encrypt/decrypt, retention prune, config
  pg-backup.sh         PostgreSQL base backup (stand-in for pgBackRest)
  pg-restore.sh        restore a base backup into a fresh PGDATA
  etcd-backup.sh       etcd snapshot (wraps deploy/etcd/snapshot.sh)
  etcd-restore.sh      rebuild a 1-member cluster from a snapshot
  restore-test.sh      weekly: restore the newest REAL backups + integrity-check (E24-05)
  systemd/             bbz-{pg,etcd}-backup + bbz-restore-test {service,timer},
                       bbz-backup-failed@ (OnFailure alert)
```

Runbook: `docs/runbooks/restore.md`.

## What is backed up, and the RPO

| store | contents | schedule | RPO |
|---|---|---|---|
| PostgreSQL | all BBZ domain data **and** the audit log | daily base + continuous WAL archive | **≤ `archive_timeout`** (60 s) with an intact WAL archive; ≤ 24 h without |
| etcd | Patroni state, app leader leases (no BBZ data) | every 6 h | ≤ 6 h — the snapshot is only needed for a full-cluster rebuild |

The intended PostgreSQL tool is **pgBackRest** (incremental, parallel,
retention, PITR). `pg-backup.sh` is the dependency-light reference: it is what a
backup must *produce* and is what CI's restore test exercises.

## Encryption & access

- Every artefact is `gpg --encrypt --recipient $GPG_RECIPIENT`, mode `0600`.
  **Asymmetric** — the private key lives offline (an HSM / an offline operator
  key), never on the BBZ servers.
- Backups run as a dedicated `bbz-backup` user; `$BACKUP_DIR` is `0700`.
- Off-host / DR-site replication of `$BACKUP_DIR` is Epic 24.

## Retention

`common.sh`: keep `KEEP_FULL` (7) newest fulls and drop anything older than
`KEEP_DAYS` (14). Tune per the legal retention requirement for the audit data.

## Schedule

Install the systemd units (`systemctl enable --now bbz-pg-backup.timer
bbz-etcd-backup.timer`). The PG unit has `ExecCondition` on Patroni
`/primary`, so only the current primary node backs up.

## Restore test

Two layers:

- **CI** — `.github/workflows/backup-nightly.yml` weekly proves the backup +
  restore *mechanism* against throwaway data.
- **Production** (E24-05) — `bbz-restore-test.timer` on the backup host, weekly,
  runs `restore-test.sh` against the **real** newest backups: decrypt + extract
  the PG base backup, start a throwaway `postgres` on it, check `alembic_version`
  and run `pg_amcheck --heapallindexed --parent-check`; `etcdutl snapshot status`
  on the etcd snapshot. It then `POST`s the outcome to
  `POST /api/v1/system/restore-test` — which writes a `RESTORE_TEST_COMPLETED`
  audit row and drives `bbz_restore_test_age_seconds` / `bbz_restore_test_ok`.

## Alerting

- A failed backup/restore-test unit triggers `OnFailure=bbz-backup-failed@%n`:
  a `daemon.err` journal line (`backup_job_failed`) the log shipper alerts on,
  plus a best-effort POST to `$ALERT_WEBHOOK`.
- Prometheus (`deploy/monitoring/alerts/bbz.rules.yml`): **`BbzRestoreTestStale`**
  (no successful test in >8 days, or never) and **`BbzRestoreTestFailing`** (the
  last one failed) — both `critical`.

## RPO / RTO

| store | RPO (data loss) | RTO (time to restore) |
|---|---|---|
| PostgreSQL | ≤ `archive_timeout` (60 s) with an intact WAL archive; ≤ 24 h to the last base without | base restore ≈ minutes for a Leitstelle-sized DB; the weekly test records the measured `rto_seconds` in the audit row |
| etcd | ≤ 6 h | minutes — `etcd-restore.sh` rebuilds a 1-member cluster, Patroni re-forms |

A promoted standby (Patroni, ADR-0021) is the *first* line and loses nothing —
these figures are for a **total** loss of a store, where a backup is the only
option. The DR-site procedure (both nodes + witness lost) is E24-06.
