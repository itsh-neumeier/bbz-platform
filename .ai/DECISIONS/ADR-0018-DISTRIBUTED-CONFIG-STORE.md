# ADR-0018: Distributed Configuration Store (etcd)

## Status
Accepted (2026-08-29, review E01-01 / #20)

## Context
ADR-0001 requires a DCS with three voting members (SRV01, SRV02, QUORUM01) for
Patroni-managed PostgreSQL failover. ADR-0002 also needs a short-TTL lease to
elect the CUCM `CONTROL_LEADER`. MASTER_PROMPT allows "etcd or Consul".

## Decision
- Use **etcd** (v3.5.x) as the single DCS.
- Three members: one per BBZ server + one on `BBZ-QUORUM01` (witness).
- Patroni uses the `/patroni` key prefix. Application leader-election (CUCM
  `CONTROL_LEADER`, outbox dispatcher singleton, etc.) uses a separate `/bbz`
  prefix with short-lived leases + keepalive.
- The quorum node runs **only** the etcd member (+ optional monitoring) — no BBZ
  domain services (MASTER_PROMPT §20).
- TLS between members and clients; access scoped per role.

## Consequences
- One consensus system to operate, back up and monitor.
- App-level leader election reuses proven infrastructure instead of a bespoke
  mechanism.

## Alternatives considered
Consul (also fine; richer service-discovery/health features we do not currently
need — more moving parts). Two separate stores (rejected: needless operational
surface).
