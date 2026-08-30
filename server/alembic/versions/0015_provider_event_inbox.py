"""provider_event_inbox: persist + dedupe inbound external events

Revision ID: 0015_provider_event_inbox
Revises: 0014_external_action_outbox
Create Date: 2026-08-30

Roadmap E04-07 (#63). ADR-0011 provider-event inbox. ``dedupe_key`` UNIQUE ->
an event is processed at most once. Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_provider_event_inbox"
down_revision: str | None = "0014_external_action_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_event_inbox",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_event_id", sa.String(length=200), nullable=True),
        sa.Column("dedupe_key", sa.String(length=200), nullable=False),
        sa.Column("raw_ref", sa.String(length=200), nullable=True),
        sa.Column("raw_hash", sa.String(length=64), nullable=True),
        sa.Column("normalized", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_provider_event_inbox")),
        sa.UniqueConstraint("dedupe_key", name=op.f("uq_provider_event_inbox_dedupe_key")),
    )
    for col in ("correlation_id", "provider", "received_at"):
        op.create_index(
            op.f(f"ix_provider_event_inbox_{col}"),
            "provider_event_inbox",
            [col],
            unique=False,
        )


def downgrade() -> None:
    for col in ("received_at", "provider", "correlation_id"):
        op.drop_index(op.f(f"ix_provider_event_inbox_{col}"), table_name="provider_event_inbox")
    op.drop_table("provider_event_inbox")
