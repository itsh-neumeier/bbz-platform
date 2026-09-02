# Environments & secret provisioning

Roadmap **E24-03**, ADR-0015, MASTER_PROMPT §22. Depends on E23-01
(`bbz_core.secrets`).

Every environment gets its **own** config set and its **own** secret values —
nothing is shared, ever. A half-provisioned node is stopped before it starts:
`deploy/node/preflight.sh` at deploy time, `verify_required_secrets()` at app
startup (E23-01).

## The matrix

| | **local** | **ci** | **staging** | **production** |
|---|---|---|---|---|
| `BBZ_ENVIRONMENT` | `local` | `ci` | `staging` | `production` |
| config source | `docker-compose.yml` env + `.env` | workflow env | `deploy/node/.env` | `deploy/node/.env` |
| secret source | dev defaults / plain env | dev defaults | `deploy/node/secrets/*` (compose secrets → `/run/secrets`) | same, **distinct values** |
| `jwt_secret` | insecure default | insecure default | **required**, ≥32 B, unique | **required**, ≥32 B, unique |
| `totp_encryption_key` | empty ⇒ TOTP enrol off | empty | **required** (Fernet key) | **required**, unique |
| `door_dtmf_encryption_key` | empty ⇒ door profiles off | empty | required once door control is used | required, unique |
| DB password | `bbz` | `bbz` | real, in the DSN | real, unique, in the DSN |
| `postgres_superuser` / `_replication` | n/a (single pg) | n/a | **required** files | **required**, unique |
| etcd client certs | plain HTTP | plain HTTP | `etcd/certs/*` (mTLS) | `etcd/certs/*` (mTLS) |
| image refs | `build:` | `build:` | tag or digest | **digest only** (no `:latest`) |
| `BBZ_CORS_ALLOW_ORIGINS` | `["http://localhost:5173"]` | `[]` | the staging web origin | the prod web origin |

`verify_required_secrets()` is a **no-op** for `local` / `ci` — the dev defaults
are deliberate there. It raises `SecretsIncompleteError` on `staging` /
`production` for a missing `jwt_secret` or a passwordless DSN.

## Isolation

- One `deploy/node/.env` + `deploy/node/secrets/` **per node**, never copied
  between environments. `.env` and `secrets/*` are gitignored; only `*.example`
  is committed.
- Staging and production secrets are generated **separately** (see below) — a
  staging leak never touches production.
- The two production app nodes (`BBZ-SRV01`, `BBZ-SRV02`) share the same secret
  *values* (they are one cluster) but each has its own `.env` (`BBZ_NODE_ID`,
  advertise hosts).

## Provisioning a node (staging / production)

```sh
cd /opt/bbz/deploy/node

# 1. config
cp .env.example .env
$EDITOR .env                       # node id, public name, image digests, DSN, origins

# 2. secrets — generate FRESH per environment, never reuse
mkdir -p secrets
openssl rand -base64 48            > secrets/bbz_jwt_secret
python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())" \
                                   > secrets/bbz_totp_encryption_key
openssl rand -base64 32            > secrets/postgres_superuser_password
openssl rand -base64 32            > secrets/postgres_replication_password
chmod 600 secrets/*

# 3. etcd mTLS certs (once per cluster, distributed to every node)
../etcd/gen-certs.sh               # -> etcd/certs/{ca,client-bbz-app}.{crt,key}

# 4. verify — this must pass before `docker compose up`
sh preflight.sh

# 5. first boot
docker compose up -d
docker compose run --rm api alembic upgrade head
```

`tools/rolling-update.sh` runs `sh preflight.sh` on each node before it swaps the
image, so a drifted / incomplete `.env` aborts the rollout with the node
untouched.

## What preflight checks

`.env` present, every required `BBZ_*` non-empty and free of `CHANGE_ME`,
`BBZ_ENVIRONMENT` valid for a node, the DSN carries a password, production images
pinned (not `:latest`); each `secrets/<name>` present, non-empty, not the
placeholder, not identical to its `.example`; `jwt_secret` ≥ 32 bytes; the three
etcd cert files present. It exits non-zero listing **everything** missing at once.
