# Developer setup

## Prerequisites

- Python 3.12+
- Node.js **22** (only for `apps/web` — the version CI pins)
- Docker + Docker Compose
- `just` (optional — every recipe is a plain command below)

## Backend + shared packages

```bash
python -m venv .venv
# Windows
.venv/Scripts/pip install -r requirements-dev.txt
# Linux/macOS
.venv/bin/pip install -r requirements-dev.txt
```

Checks (what CI runs):

```bash
ruff check .            # lint
ruff format --check .   # formatting
mypy server/bbz_core packages/integration-sdk/bbz_integration_sdk \
     packages/rule-dsl/bbz_rule_dsl packages/event-schemas/bbz_event_schemas
lint-imports             # architecture boundaries
pytest                   # unit/API/contract tests (no DB needed)
```

> On Windows, run `lint-imports` with `PYTHONUTF8=1` to avoid a console encoding
> error in its banner rendering.

## Database migrations

Needs a running PostgreSQL and `BBZ_DATABASE_URL`:

```bash
docker compose --profile core up -d postgres
cd server && ../.venv/Scripts/alembic upgrade head
```

## Full dev stack

```bash
cp .env.example .env
docker compose --profile core up --build
# api  -> http://localhost:8000  (/docs, /health/ready, /cluster/status)
# web  -> http://localhost:5173
```

## Frontend

```bash
cd apps/web
npm ci             # reproducible install from package-lock.json (CI uses this)
npm run dev        # http://localhost:5173 (proxies /api,/health,/cluster -> :8000)
npm run lint && npm run typecheck && npm run test
```

The `frontend (lint · type · unit)` CI job is **blocking** (E01-06). After a
dependency change, run `npm install` to refresh `package-lock.json` and commit
it.

## What exists today (Phase 0)

Skeleton only: health/cluster/meta endpoints, integration manifest discovery,
app shell. No domain logic, no productive vendor integrations. See
`.ai/CURRENT_STATE.md`.
