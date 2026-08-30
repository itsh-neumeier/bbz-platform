# Runbook: restore from backup

For a total loss of a state store. Backups + scripts: `deploy/backup/`.
RPO figures: `deploy/backup/README.md`.

Prerequisites: the **offline** GPG private key for `$GPG_RECIPIENT`, the etcd
`client-admin` cert, and an empty target host / directory.

## PostgreSQL

1. Pick the newest good base backup:
   ```sh
   ls -1t /var/backups/bbz/postgres/base-*.tar.gz.gpg
   ```
2. Restore it into a fresh data dir:
   ```sh
   GPG_RECIPIENT=<key> deploy/backup/pg-restore.sh \
     /var/backups/bbz/postgres/base-<stamp>.tar.gz.gpg  /var/lib/postgresql/restore
   ```
3. **PITR** (optional): edit `restore/postgresql.auto.conf.restore` →
   `restore_command` pointing at the encrypted WAL archive, plus
   `recovery_target_time`. Rename it to `postgresql.auto.conf`.
4. Start PostgreSQL against `/var/lib/postgresql/restore` **read-only** and
   verify integrity:
   ```sql
   SELECT count(*) FROM audit_events;
   SELECT max(event_seq) FROM domain_events;
   ```
   Compare `max(event_seq)` to what clients last acked and to the surviving
   node if there is one.
5. Promote it (`pg_ctl promote` or hand it to Patroni as the new bootstrap
   member), then re-add the standby (`pg_basebackup` from the new primary or
   let Patroni clone it).
6. Post an audit marker: `POST /api/v1/system/backup {"phase":"restored",
   "kind":"postgres"}`.

## etcd

1. Stop etcd on all members.
2. On one host, restore the newest snapshot:
   ```sh
   deploy/backup/etcd-restore.sh /var/backups/bbz/etcd/etcd-<stamp>.db.gpg \
     BBZ-SRV01  https://bbz-srv01:2380  /var/lib/etcd-restore
   ```
3. Start that etcd with `--initial-cluster-state=existing` pointing at the
   restored data dir.
4. Wipe the other members' data dirs and re-add them:
   ```sh
   etcdctl member add BBZ-SRV02 --peer-urls=https://bbz-srv02:2380
   # then start SRV02 with the printed ETCD_INITIAL_CLUSTER
   ```
5. `etcdctl endpoint status --write-out=table` → three healthy voters.
6. Patroni re-reads `/patroni` from the restored etcd; confirm one leader and
   that the app leader elections re-settle (`/cluster/status`).
7. Audit marker: `POST /api/v1/system/backup {"phase":"restored","kind":"etcd"}`.

## The tested part

`deploy/backup/*` + the weekly CI job (`.github/workflows/backup-nightly.yml`)
prove the *mechanism* — backup, encrypt, decrypt, restore, count match. This
runbook is the operator procedure for the real cluster; walk it on the
staging environment at least once per release train.
