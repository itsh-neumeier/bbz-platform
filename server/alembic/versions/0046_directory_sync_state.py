"""directory_sync_state

Revision ID: 0046_directory_sync_state
Revises: 0045_auth_group_mappings
Create Date: 2026-09-01

Roadmap E21-04. Bookkeeping for the directory sync singleton: one row per
directory source (``ldap_ad``) — when it last ran, whether it succeeded, the
last error, and a small JSON summary of the last run. All times ``timestamptz``
(ADR-0017). Additive / expand-only, reversible.

expand-contract: safe
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0046_directory_sync_state"
down_revision: str | None = "0045_auth_group_mappings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TS = sa.DateTime(timezone=True)
_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "directory_sync_state",
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("last_run_at", _TS, nullable=True),
        sa.Column("last_success_at", _TS, nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("updated_at", _TS, server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("source", name=op.f("pk_directory_sync_state")),
    )


def downgrade() -> None:
    op.drop_table("directory_sync_state")
