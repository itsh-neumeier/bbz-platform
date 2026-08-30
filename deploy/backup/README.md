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
  systemd/             bbz-pg-backup.{service,timer}, bbz-etcd-backup.{service,timer}
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

## Restore test (CI)

`.github/workflows/backup-nightly.yml` runs weekly (+ on demand): it takes a
backup of a throwaway PostgreSQL and etcd, restores each into a fresh instance,
and asserts the row/key counts match. Not a PR gate.
