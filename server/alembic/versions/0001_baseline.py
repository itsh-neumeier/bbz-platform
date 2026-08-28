"""baseline: extensions only, no domain tables

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-28

Foundation phase. Establishes required PostgreSQL extensions and nothing else.
Domain tables (events, audit_events, domain_events, commands, ...) arrive in
Phase 1 following the expand / migrate / contract strategy (MASTER_PROMPT §21).

Fully reversible: downgrade drops the extensions it created.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # pgcrypto -> gen_random_uuid(); citext -> case-insensitive lookups later.
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "citext"')


def downgrade() -> None:
    op.execute('DROP EXTENSION IF EXISTS "citext"')
    op.execute('DROP EXTENSION IF EXISTS "pgcrypto"')
