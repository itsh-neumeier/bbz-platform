"""unmapped_signals

Revision ID: 0033_unmapped_signals
Revises: 0032_client_popup_events
Create Date: 2026-08-31

Roadmap E15-12. A normalized inbound signal the engine matched to no published
trigger rule lands here for admin diagnosis / mapping (never an error). Rows are
deduplicated on ``dedupe_key``; ``occurrences`` counts repeats. Reversible,
expand-only.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0033_unmapped_signals"
down_revision: str | None = "0032_client_popup_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "unmapped_signals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=200), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("signal_type", sa.String(length=64), nullable=False),
        sa.Column(
            "source",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "sample",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("occurrences", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.Uuid(), nullable=True),
        sa.Column("resolved_endpoint_id", sa.Uuid(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["resolved_by"],
            ["users.id"],
            name=op.f("fk_unmapped_signals_resolved_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_endpoint_id"],
            ["technical_endpoints.id"],
            name=op.f("fk_unmapped_signals_resolved_endpoint_id_technical_endpoints"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_unmapped_signals")),
        sa.UniqueConstraint("dedupe_key", name=op.f("uq_unmapped_signals_dedupe_key")),
    )
    op.create_index(op.f("ix_unmapped_signals_provider"), "unmapped_signals", ["provider"])
    op.create_index(op.f("ix_unmapped_signals_signal_type"), "unmapped_signals", ["signal_type"])


def downgrade() -> None:
    op.drop_index(op.f("ix_unmapped_signals_signal_type"), table_name="unmapped_signals")
    op.drop_index(op.f("ix_unmapped_signals_provider"), table_name="unmapped_signals")
    op.drop_table("unmapped_signals")
