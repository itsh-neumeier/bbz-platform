"""domain_events: append-only event log with a BIGINT event_seq

Revision ID: 0010_domain_events
Revises: 0009_events
Create Date: 2026-08-29

Roadmap E03-02 (#42). Append-only (MASTER_PROMPT §3, ADR-0011). Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_domain_events"
down_revision: str | None = "0009_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "domain_events",
        sa.Column("event_seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "event_uuid", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column(
            "occurred_at_utc",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("occurred_at_local", sa.String(length=40), nullable=True),
        sa.Column("node_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("client_id", sa.String(length=64), nullable=True),
        sa.Column("command_id", sa.Uuid(), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("schema_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("event_seq", name=op.f("pk_domain_events")),
        sa.UniqueConstraint("event_uuid", name=op.f("uq_domain_events_event_uuid")),
    )
    op.create_index(
        op.f("ix_domain_events_aggregate_id"), "domain_events", ["aggregate_id"], unique=False
    )
    op.create_index(
        op.f("ix_domain_events_aggregate_type"), "domain_events", ["aggregate_type"], unique=False
    )
    op.create_index(
        op.f("ix_domain_events_command_id"), "domain_events", ["command_id"], unique=False
    )
    op.create_index(
        op.f("ix_domain_events_correlation_id"), "domain_events", ["correlation_id"], unique=False
    )
    op.create_index(
        op.f("ix_domain_events_event_type"), "domain_events", ["event_type"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_domain_events_event_type"), table_name="domain_events")
    op.drop_index(op.f("ix_domain_events_correlation_id"), table_name="domain_events")
    op.drop_index(op.f("ix_domain_events_command_id"), table_name="domain_events")
    op.drop_index(op.f("ix_domain_events_aggregate_type"), table_name="domain_events")
    op.drop_index(op.f("ix_domain_events_aggregate_id"), table_name="domain_events")
    op.drop_table("domain_events")
