# BBZ-QUORUM01 hardening checklist

The witness exists only to be the third etcd voter. Its value is that it holds
**no data and no business logic** — keep it that way and keep its attack
surface minimal (MASTER_PROMPT §2/§20).

## Deployment (this compose — CI-checked)

- [x] Exactly one service: `etcd` (+ the built-in `/metrics` on `:2381`). No
      `bbz-api`, `bbz-web`, `postgres`, `patroni`. (`test_deploy_topology.py`)
- [x] mTLS enforced on the client **and** peer plane (`--client-cert-auth`,
      `--peer-client-cert-auth`); no plaintext etcd endpoint.
- [x] etcd auth enabled (`deploy/etcd/bootstrap-auth.sh`) — no anonymous access.
- [x] Container: `read_only` root FS, `cap_drop: [ALL]`, `no-new-privileges`,
      `mem_limit` / `cpus` / `pids_limit`, `tmpfs /tmp`.
- [x] Published ports bound to the internal management interface
      (`QUORUM_BIND`), not `0.0.0.0`.
- [x] `restart: unless-stopped`, healthcheck on `etcdctl endpoint health`.

## Host (operator responsibility)

- [ ] Minimal OS image; automatic security updates; no desktop, no extra
      daemons.
- [ ] Firewall: inbound only `2379/2380` from `BBZ-SRV01` + `BBZ-SRV02`, and
      `2381` from the monitoring host. Everything else denied.
- [ ] SSH: key-only, no root login, restricted source addresses.
- [ ] Docker/Podman rootless **or** userns-remap so the etcd process maps to an
      unprivileged host uid; the data dir owned accordingly.
- [ ] Disk encryption at rest (the snapshot still contains cluster metadata).
- [ ] `deploy/etcd/certs/` present with **only** `ca.crt` +
      `BBZ-QUORUM01-{peer,server}.{crt,key}` — no other member's key, no client
      keys.
- [ ] Time sync (chrony/ntp) — raft is sensitive to clock skew.
- [ ] Log + metric shipping to the central stack (Epic 22).
- [ ] `deploy/etcd/snapshot.sh` scheduled; snapshots copied off-host (E06-15).

## Explicitly NOT here

No PostgreSQL, no application, no reverse proxy, no user-facing port. If a
future need looks like it belongs on the witness, it does not — raise an ADR.
