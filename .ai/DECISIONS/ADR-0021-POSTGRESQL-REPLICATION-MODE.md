# ADR-0021: PostgreSQL replication mode — synchronous with automatic fallback

## Status
Accepted

## Context
ADR-0001 fixes the topology: two active application nodes, one PostgreSQL
primary with a standby, Patroni-managed failover, an etcd cluster of three
voting members (SRV01, SRV02, QUORUM01). `.ai/CURRENT_STATE.md` carries the open
question "synchronous vs asynchronous PostgreSQL replication mode".

The BBZ platform runs a **Leitstelle** (3‑S emergency dispatch centre). Two
properties are in tension:

* **No acknowledged data may be lost on failover.** A promoted standby that is
  missing the last few transactions could drop an accepted alarm, an audit
  entry, or a workflow decision. For a dispatch centre that is a safety issue,
  not just an inconvenience.
* **The database must stay writable through a single fault.** With only one
  standby, that standby failing is a realistic single fault. Fully strict
  synchronous replication makes the primary *block every write* until a sync
  standby returns — the Leitstelle could not take calls. That is also
  unacceptable.

Patroni offers a middle setting: `synchronous_mode: true` with
`synchronous_mode_strict: false`.

## Decision
Run **synchronous replication with automatic fallback**:

* `synchronous_mode: true`, `synchronous_node_count: 1` — the primary waits for
  one standby to persist each commit (`synchronous_commit = on`). While a
  standby is caught up, **RPO = 0**.
* `synchronous_mode_strict: false` — if the sole synchronous standby is lost,
  Patroni removes it from `synchronous_standby_names` and the primary keeps
  accepting writes in asynchronous mode. The transition is logged loudly and is
  visible in `patronictl list` / `/cluster/status`.
* `maximum_lag_on_failover: 1048576` (1 MiB) — Patroni never promotes a standby
  that is further behind than this, so an automatic failover during the
  degraded (async) window still bounds data loss.
* The brief async window is reconciled by **WAL / `event_seq` catch-up**
  (ADR-0001): a rejoining node fast-forwards from the shared consensus and
  clients replay in-flight commands idempotently (ADR-0012), so a client that
  did not get an ack simply retries with the same `command_id`.
* Timing: `ttl: 30`, `loop_wait: 10`, `retry_timeout: 10`. A dead primary is
  detected and a standby promoted in **≈ 30–45 s**; the **target RTO is
  ≤ 60 s** including application reconnect. `master_start_timeout: 300` lets a
  crashed primary attempt local recovery before Patroni forces a failover.

The full configuration lives in `deploy/node/patroni/patroni.node.yml`;
`docs/runbooks/db-failover.md` is the operator procedure. `pg_rewind` and
replication slots are enabled so a demoted primary rejoins without a manual
base backup.

Replication and superuser credentials are **separate** and delivered as
mounted secret files (`deploy/node/secrets/postgres_*_password`), never as
plaintext in compose or `.env`.

## Consequences
* Zero data loss in the normal case (both DB nodes healthy).
* A standby outage degrades to async automatically instead of freezing writes;
  the loss of durability is explicit, observable and time-bounded.
* Write latency carries one network round-trip to the standby while synchronous
  — acceptable on a LAN between two co-located servers.
* Losing the primary **and** the standby (or primary + witness) still stops the
  cluster: it goes read-only rather than risk split brain. Restoring a third
  voter is a manual runbook step.
* A `DB_FAILOVER` audit event is emitted by the cluster observer (E06‑04 /
  E06‑07) whenever the leader key changes, so failovers are on the audit trail.

## Alternatives considered
* **Fully asynchronous** — best write latency and availability, but a failover
  can silently lose acknowledged dispatch data. Rejected for a Leitstelle.
* **Strict synchronous (`synchronous_mode_strict: true`)** — zero RPO always,
  but a single standby outage blocks all writes. Rejected: unacceptable
  availability for emergency operations with only one standby.
* **Synchronous with two standbys / a quorum commit** — removes the block
  without giving up strictness, but needs a third PostgreSQL node. Out of scope
  for the 2‑server topology (ADR-0001); revisit if a third app server is added.
