# Task shortcuts. `just` is optional — every recipe is a plain command you can
# also run by hand (see docs/DEV_SETUP.md). Windows: use Git Bash or `just`.

set windows-shell := ["bash", "-uc"]

venv := if os_family() == "windows" { ".venv/Scripts" } else { ".venv/bin" }

# install the Python workspace + tooling
bootstrap:
    python -m venv .venv
    {{venv}}/pip install --upgrade pip
    {{venv}}/pip install -r requirements-dev.txt

lint:
    {{venv}}/ruff check .
    {{venv}}/ruff format --check .

types:
    {{venv}}/mypy server/bbz_core packages/integration-sdk/bbz_integration_sdk packages/rule-dsl/bbz_rule_dsl packages/event-schemas/bbz_event_schemas

imports:
    {{venv}}/lint-imports

test:
    {{venv}}/pytest

check: lint types imports test

# full dev stack (single node)
up:
    docker compose --profile core up --build

down:
    docker compose --profile core down -v

# database migrations (needs a running postgres + BBZ_DATABASE_URL)
migrate:
    cd server && ../{{venv}}/alembic upgrade head
