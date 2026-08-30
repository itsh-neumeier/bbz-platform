"""external_action_outbox: transactional outbox for external side effects

Revision ID: 0014_external_action_outbox
Revises: 0013_audit_event_seq_ref
Create Date: 2026-08-30

Roadmap E04-06 (#62). ADR-0011 transactional outbox. ``dedupe_key`` UNIQUE makes
a double-enqueue impossible. Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_external_action_outbox"
down_revision: str | None = "0013_audit_event_seq_ref"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "external_action_outbox",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("dedupe_key", sa.String(length=200), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'dispatched', 'failed')",
            name=op.f("ck_external_action_outbox_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_action_outbox")),
        sa.UniqueConstraint("dedupe_key", name=op.f("uq_external_action_outbox_dedupe_key")),
    )
    for col in ("action_type", "correlation_id", "next_attempt_at", "status"):
        op.create_index(
            op.f(f"ix_external_action_outbox_{col}"),
            "external_action_outbox",
            [col],
            unique=False,
        )


def downgrade() -> None:
    for col in ("status", "next_attempt_at", "correlation_id", "action_type"):
        op.drop_index(op.f(f"ix_external_action_outbox_{col}"), table_name="external_action_outbox")
    op.drop_table("external_action_outbox")
