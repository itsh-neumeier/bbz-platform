# deploy/

Deployment topology for the BBZ platform. ADR-0001 (two active app nodes +
quorum-governed DB failover), ADR-0018 (etcd), MASTER_PROMPT §20.

```
deploy/
  node/            per-node stack: bbz-api, bbz-web, PostgreSQL+Patroni, an
                   etcd member, Caddy reverse proxy   ← BBZ-SRV01 / BBZ-SRV02
    docker-compose.yml
    .env.example
    secrets/*.example      real files (no .example suffix) are gitignored
    patroni/patroni.node.yml
    reverse-proxy/Caddyfile
  quorum/          etcd member ONLY — no BBZ domain services   ← BBZ-QUORUM01
    docker-compose.yml
    .env.example
  reverse-proxy/   the shared edge stub used by the repo-root dev stack
```

The repo-root `docker-compose.yml` (`name: bbz-platform`) is the **developer
convenience stack** — one node, no Patroni, no HA. The production per-node
composition lives here (`bbz-node` / `bbz-quorum`).

## Bring a node up (single-host simulation)

```bash
cd deploy/node
cp .env.example .env                                  # edit for this host
for f in secrets/*.example; do cp "$f" "${f%.example}"; done   # then fill in
docker compose up -d
```

`deploy/quorum` is the same, minus every service but etcd.

## What each roadmap issue adds

| Issue | Adds |
|-------|------|
| **E06-01 (this)** | the compose topology, env/secret templates, `docker compose config` in CI |
| E06-02 (#82) | Patroni replication mode + tuning, ADR-0021, failover rules |
| E06-03 (#84) | the real 3-member etcd cluster join with mutual TLS |
| E06-13 (#93) | full Caddy hardening (HSTS, CSP, rate limits) |
| E06-15 (#95) | PostgreSQL + etcd backup / restore |

## Secrets

Non-secret configuration is env (`deploy/node/.env`, gitignored). Secret
*values* are mounted files under `deploy/node/secrets/` (gitignored; only the
`*.example` templates are tracked). The API reads file-based secrets when
`BBZ_SECRETS_DIR` is set (the compose sets it to `/run/secrets`), so e.g.
`/run/secrets/bbz_jwt_secret` supplies `BBZ_JWT_SECRET`. The DB DSN password is
still carried in `.env` for now — moving it to a composed secret is a follow-up.
