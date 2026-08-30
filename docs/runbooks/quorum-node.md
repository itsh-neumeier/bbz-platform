# Runbook: the quorum node (BBZ-QUORUM01)

`BBZ-QUORUM01` runs **one** etcd member and nothing else (ADR-0018,
`deploy/quorum/`). It is the third voter so the etcd cluster keeps a majority
(2 of 3) when either BBZ server is down. It stores cluster metadata only — no
BBZ data ever lives here.

## Bring it up

```sh
cd deploy/quorum
cp .env.example .env            # set BBZ_NODE_ID, the 3-member ETCD_INITIAL_CLUSTER, QUORUM_BIND
mkdir -p etcd/certs             # copy ca.crt + BBZ-QUORUM01-{peer,server}.{crt,key} here
docker compose up -d
docker compose exec etcd etcdctl endpoint health
```

After the whole cluster's first successful boot, set
`ETCD_INITIAL_CLUSTER_STATE=existing` in `.env` on every host.

## Verify it is voting

From a BBZ server:

```sh
etcdctl --endpoints=https://bbz-srv01:2379,https://bbz-srv02:2379,https://bbz-quorum01:2379 \
  --cacert=.../ca.crt --cert=.../client-admin.crt --key=.../client-admin.key \
  endpoint status --write-out=table
```

Three rows, one `IS LEADER=true`, all with the same `RAFT TERM` and a close
`RAFT INDEX`.

## Replace a failed witness

1. On a healthy member: `etcdctl member remove <old-quorum-member-id>`.
2. Provision the new host, copy fresh `BBZ-QUORUM01-*` certs (regenerate with
   `deploy/etcd/gen-certs.sh` if the host name/IP changed).
3. On a healthy member: `etcdctl member add BBZ-QUORUM01 --peer-urls=https://bbz-quorum01:2380`
   — note the printed `ETCD_INITIAL_CLUSTER` / `ETCD_INITIAL_CLUSTER_STATE=existing`.
4. Put those into `deploy/quorum/.env` on the new host and `docker compose up -d`.
5. `endpoint status` shows three voters again.

## If the witness is down

The cluster still has quorum (both BBZ servers). Patroni and the app leader
election keep working. **Do not** also take a BBZ server down for maintenance
until the witness is back — that would drop below majority and force the
database read-only (see `db-failover.md`).

## Hardening

`deploy/quorum/HARDENING.md` — container settings are enforced in the compose
file and checked by `test_deploy_topology.py`; the host items are the
operator's.
