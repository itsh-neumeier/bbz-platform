"""commands: durable command dedupe / replay protection

Revision ID: 0011_commands
Revises: 0010_domain_events
Create Date: 2026-08-29

Roadmap E03-03 (#43). One row per ``X-Command-Id`` (ADR-0012). A duplicate
command replays its stored result instead of re-running. Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_commands"
down_revision: str | None = "0010_domain_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "commands",
        sa.Column("command_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("endpoint", sa.String(length=200), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("result_status", sa.Integer(), nullable=True),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_commands_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("command_id", name=op.f("pk_commands")),
    )
    # purge_stale() scans pending rows by age.
    op.create_index(
        "ix_commands_pending_created_at",
        "commands",
        ["created_at"],
        unique=False,
        postgresql_where=sa.text("result_status IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_commands_pending_created_at",
        table_name="commands",
        postgresql_where=sa.text("result_status IS NULL"),
    )
    op.drop_table("commands")
