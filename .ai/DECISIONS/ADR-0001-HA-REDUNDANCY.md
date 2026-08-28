# ADR-0001: Two Active Application Nodes with Quorum-Governed Database Failover

## Status
Accepted

## Context
The BBZ platform must run on two active servers and continue after failure of one server. A third lightweight quorum service is available. A raw two-node multi-master database would risk split brain.

## Decision
- Both BBZ application nodes are active.
- PostgreSQL uses primary/standby replication.
- Patroni manages failover.
- etcd/Consul uses three voting members including the witness.
- Clients may use either application server.
- Application state changes use idempotent commands and an event/audit log.

## Consequences
- Stronger consistency.
- Automatic failover.
- No uncontrolled dual-writer database.
- Catch-up uses WAL/event sequence, not timestamp-only replication.
