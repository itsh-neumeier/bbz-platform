# deploy/etcd — the BBZ consensus store

etcd v3.5.x is the single DCS (ADR-0018). Three voting members — one per BBZ
server + one on the witness — so the cluster keeps a majority (2 of 3) when any
one host is down. It backs both the Patroni-managed PostgreSQL failover
(`/patroni/` prefix) and the application leader election (`/bbz/` prefix).

```
deploy/etcd/
  gen-certs.sh        CA + per-member (peer/server) + per-client certificates
  bootstrap-auth.sh   enable auth, create prefix-scoped roles (patroni / bbz)
  snapshot.sh         consistent snapshot hook (retention is E06-15)
  openssl.cnf         (not needed — gen-certs.sh is self-contained)
  certs/              generated material — GITIGNORED, never committed
```

## Bring the cluster up

1. **Certificates** (once, on a trusted host):
   ```sh
   MEMBERS="BBZ-SRV01=bbz-srv01,10.0.0.11 BBZ-SRV02=bbz-srv02,10.0.0.12 BBZ-QUORUM01=bbz-quorum01,10.0.0.13" \
     ./gen-certs.sh
   ```
   Distribute `ca.crt` everywhere; give each member only its own
   `*-peer.*` / `*-server.*`; give the DB nodes `client-patroni.*`, the app
   nodes `client-bbz-app.*`, the operator `client-admin.*`. Copy the right
   files into each host's `deploy/node/etcd/certs/` (or `deploy/quorum/etcd/certs/`).

2. **First boot** — set `ETCD_INITIAL_CLUSTER` to all three members and
   `ETCD_INITIAL_CLUSTER_STATE=new` on every host, then `docker compose up -d`
   on each. Members speak mTLS over `:2380` (peer) and serve clients over
   TLS + client-cert-auth on `:2379`.

3. **Authentication** (once, after the cluster is healthy):
   ```sh
   ENDPOINTS=https://bbz-srv01:2379,https://bbz-srv02:2379 ./bootstrap-auth.sh
   ```
   This enables auth and grants:
   | user | role | scope |
   |------|------|-------|
   | `patroni` | `patroni` | readwrite `/patroni/` |
   | `bbz-app` | `bbz` | readwrite `/bbz/` |
   | `admin` | `observer` | read-only everywhere |

   Members map a client certificate's **CN** to the etcd username, so Patroni
   authenticates as `patroni` with `client-patroni.crt` (CN=`patroni`) and can
   never touch `/bbz/`; the app authenticates as `bbz-app` and can never touch
   `/patroni/`.

4. After the first boot, change `ETCD_INITIAL_CLUSTER_STATE` to `existing` in
   every `.env` so a restart re-joins instead of trying to bootstrap.

## Losing a member

- **One BBZ server down** — quorum is 2/3 (the surviving server + the witness).
  Patroni still elects a PostgreSQL primary; the app still elects its leader.
- **Witness down** — quorum is 2/3 (both BBZ servers). Same.
- **Two members down** — no majority: etcd is read-only, Patroni holds the
  current primary read-only rather than risk split brain. See
  `docs/runbooks/db-failover.md`.

## Backup

`snapshot.sh` produces a restore-checked `.db`. Scheduling, off-host copies and
the restore drill are E06-15 (#95).
