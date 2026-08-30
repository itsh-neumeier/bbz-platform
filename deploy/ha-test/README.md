# deploy/ha-test — HA failure-scenario harness

Roadmap E06-11, MASTER_PROMPT §24. A **single-host mini HA cluster** (two app
nodes, a Patroni primary/standby behind HAProxy, a 3-member etcd, a Caddy load
balancer) plus repeatable fault-injection scenarios.

> **Status: scaffold.** The compose + scenarios are written to the shape the
> HA guarantees require, but they have **not been executed end-to-end in this
> environment** — bringing up Patroni + fault injection needs a real Docker
> host with enough memory and time. Run `./run.sh` on such a host, fix the
> inevitable timing/wiring nits, then flip the nightly workflow from
> `continue-on-error` to gating.

```
deploy/ha-test/
  compose.yml        2× api, pg1/pg2 (Spilo), pgha (HAProxy), 3× etcd, lb (Caddy)
  Caddyfile          LB: round-robin + /health/ready active checks
  haproxy.cfg        DB router: :5432 -> current primary (GET /primary == 200)
  seed.py            one probe user (mounted into the api containers)
  setup.sh           up --build, wait, seed, log in -> .ha-token
  run.sh             setup + every scenario + teardown
  lib.sh             shared shell helpers (write_event, head_seq, assert_single_primary, rto_…)
  scenarios/
    srv01-down.sh        SRV01 gone -> LB serves from SRV02, writes ok, catch-up on return
    srv02-down.sh        symmetric
    db-primary-loss.sh   kill the PG primary -> promote standby, RTO ≤ 60s, no seq regression
    net-isolation.sh     isolate one server -> other keeps quorum, NO second primary
    witness-down.sh      etcd witness gone -> quorum 2/3 holds, still writable
    client-reconnect.sh  stream client's node dies -> reconnect with after_seq, gap-free (E06-07)
    recovery.sh          full restart -> converges to one primary, no events lost
```

## The seven guarantees under test

| scenario | asserts |
|---|---|
| srv01-down / srv02-down | either app server can be lost without a client outage; the returning node catches up |
| db-primary-loss | automatic Patroni failover **within the RTO** (ADR-0021); `event_seq` never regresses (no acknowledged data lost) |
| net-isolation | **no split brain** — the isolated side never promotes a second primary |
| witness-down | 2-of-3 quorum keeps the cluster fully writable |
| client-reconnect | the catch-up protocol (E06-07) delivers exactly the missed events on failover |
| recovery | a full restart converges and loses nothing |

`assert_single_primary` runs after every fault — **two Patroni leaders is
always a failure.**

## CI

`.github/workflows/ha-nightly.yml` runs `run.sh` on a schedule (and on
`workflow_dispatch`). It is **not** a PR gate and starts `continue-on-error`
until the scenarios have been shaken out on real hardware.
