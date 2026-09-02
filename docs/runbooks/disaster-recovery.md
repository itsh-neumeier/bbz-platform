# Runbook: disaster recovery

Roadmap **E24-06**. For losses the automatic HA layer cannot absorb. Every
procedure here has been walked on staging; record the measured RTO each time.

Scope ladder — do the **smallest** procedure that covers your loss:

| lost | automatic? | procedure |
|---|---|---|
| one app node | yes — LB keeps serving | § A (rebuild the node) |
| DB primary | yes — Patroni promotes within RTO (ADR-0021) | nothing; verify § E |
| the witness | yes — 2/3 quorum holds | § B (rebuild the witness) |
| both app nodes, DB intact | no | § C |
| both DB nodes (data lost) | no | § D (restore from backup) |
| **everything** — both servers + witness | no | § D then § C then § B |

Prerequisites for a restore: the **offline** GPG private key for
`$GPG_RECIPIENT`, the etcd `client-admin` cert, `deploy/node/` + `deploy/quorum/`
checkouts, and the newest artefacts from `$BACKUP_DIR` (or the off-host copy).

---

## § A · Rebuild one app node

1. Provision the host, clone the repo to `/opt/bbz`, restore `deploy/node/.env`
   + `deploy/node/secrets/*` + `deploy/node/etcd/certs/*` for **this** node id.
2. `cd /opt/bbz/deploy/node && sh preflight.sh` — must pass.
3. `docker compose up -d`. Patroni joins as a standby and catches up;
   the app node re-registers for leader election.
4. Verify § E. Expected RTO: minutes (bounded by the base-backup / WAL replay if
   the standby had to re-clone).

## § B · Rebuild the witness

1. Provision the host, clone the repo, restore `deploy/quorum/.env` +
   `deploy/quorum/etcd/certs/*`.
2. On a surviving node, drop the dead member and add the new one:
   ```sh
   etcdctl member remove <old-witness-id>
   etcdctl member add BBZ-QUORUM01 --peer-urls=https://bbz-quorum01:2380
   ```
3. Start the witness with the printed `ETCD_INITIAL_CLUSTER` and
   `ETCD_INITIAL_CLUSTER_STATE=existing`. It is **etcd only** — no BBZ services.
4. `etcdctl endpoint status --write-out=table` → three healthy voters.

## § C · Both app nodes lost, database intact

1. Rebuild both hosts per § A steps 1–2 (config + secrets + certs + preflight).
2. Bring up the node that will hold the primary first, then the second.
3. Patroni finds the intact `$PGDATA` (or re-clones from the survivor) and
   forms `leader + standby`; app leader elections re-settle.
4. Run migrations only if the image moved forward:
   `docker compose run --rm api alembic upgrade head`.
5. Verify § E. Nothing is lost — this is a compute-only rebuild.

## § D · Database lost — restore from backup

**RPO**: ≤ `archive_timeout` (60 s) with an intact WAL archive; otherwise ≤ the
age of the newest base backup.

### etcd

```sh
newest=$(ls -1t "$BACKUP_DIR/etcd"/etcd-*.db.gpg | head -1)
GPG_RECIPIENT=<key> deploy/backup/etcd-restore.sh \
  "$newest" BBZ-SRV01 https://bbz-srv01:2380 /var/lib/etcd-restore
```
Start that single-member etcd on the restored dir with
`--initial-cluster-state=existing`, then re-add the other members (§ B step 2–3).
Patroni re-reads `/patroni` from the restored etcd.

### PostgreSQL

```sh
newest=$(ls -1t "$BACKUP_DIR/postgres"/base-*.tar.gz.gpg | head -1)
GPG_RECIPIENT=<key> deploy/backup/pg-restore.sh "$newest" /var/lib/postgresql/restore
```
For PITR, edit `restore/postgresql.auto.conf.restore` → set
`restore_command` at the WAL archive and a `recovery_target_time`, then start
PostgreSQL pointing at the restored data dir. Promote once recovery reaches the
target. Patroni takes over the restored primary; bring up the standby (§ A).

The **weekly `bbz-restore-test.timer` proves this path works** against the real
backups — check its last `RESTORE_TEST_COMPLETED` audit row before you rely on it.

## § E · Post-recovery verification

- [ ] `curl -fsS https://<node>/health/ready` on **both** app nodes → 200.
- [ ] `GET /cluster/status` — `stub:false`, `dcs_healthy:true`, `quorum:true`,
      exactly one control leader, one DB primary, lag < 1 MiB.
- [ ] `assert_single_primary` — never two Patroni leaders.
- [ ] All six cluster singletons show a leader (`/cluster/status.leaders`).
- [ ] `event_seq` did not regress — compare `GET /api/v1/events/stream/head`
      against the last value the clients had.
- [ ] `GET /api/v1/audit/chain` — `verified: true` (the hash chain is intact
      through the restore).
- [ ] A streaming client reconnects with its last `event_seq` and gets a
      gap-free continuation.
- [ ] Post a `RESTORE_PERFORMED` audit marker:
      `POST /api/v1/system/backup {"phase":"restored","kind":"postgres"}`.
- [ ] Record the wall-clock RTO in the incident report.

## RTO targets (verify on staging per release train)

| scenario | target |
|---|---|
| § A / § C — compute rebuild | ≤ 30 min per node |
| § B — witness | ≤ 15 min |
| § D — DB restore (base only, Leitstelle-sized) | ≤ 1 h |
| § D + § C + § B — full site loss | ≤ 3 h to a serving cluster |

These are targets, not guarantees — the DR drill measures the real number and
this table is updated from it.
