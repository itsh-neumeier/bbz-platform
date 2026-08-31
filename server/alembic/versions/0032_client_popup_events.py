"""client_popup_events

Revision ID: 0032_client_popup_events
Revises: 0031_trigger_rules
Create Date: 2026-08-31

Roadmap E15-03. Bottom-right, time-limited operator popups (MASTER_PROMPT §34).
Each row is bound to one ``workplace_id`` and carries a hard ``expires_at``.
The outbox ``action_type`` vocabulary is extended in code
(``bbz_core.domain.triggers``), not at the DB level (``action_type`` is a free
string). Reversible, expand-only.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032_client_popup_events"
down_revision: str | None = "0031_trigger_rules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "client_popup_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workplace_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_client_popup_events")),
    )
    op.create_index(
        op.f("ix_client_popup_events_workplace_id"), "client_popup_events", ["workplace_id"]
    )
    op.create_index(op.f("ix_client_popup_events_kind"), "client_popup_events", ["kind"])


def downgrade() -> None:
    op.drop_index(op.f("ix_client_popup_events_kind"), table_name="client_popup_events")
    op.drop_index(op.f("ix_client_popup_events_workplace_id"), table_name="client_popup_events")
    op.drop_table("client_popup_events")
