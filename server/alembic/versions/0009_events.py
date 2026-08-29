"""events core: events, status history, assignments, notes

Revision ID: 0009_events
Revises: 0008_seed_rbac
Create Date: 2026-08-29

Roadmap E03-01 (#41). Schema only. Expand-only; fully reversible.
One active assignment per event via a partial unique index.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_events"
down_revision: str | None = "0008_seed_rbac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="new", nullable=False),
        sa.Column("bbz_id", sa.Uuid(), nullable=True),
        sa.Column("workplace_id", sa.Uuid(), nullable=True),
        sa.Column("source", sa.String(length=32), server_default="manual", nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
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
        sa.CheckConstraint(
            "priority IN ('critical', 'high', 'medium', 'low')",
            name=op.f("ck_events_event_priority"),
        ),
        sa.CheckConstraint(
            "status IN ('new', 'accepted', 'acknowledged', 'opened', 'archived')",
            name=op.f("ck_events_event_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
    )
    op.create_index(op.f("ix_events_bbz_id"), "events", ["bbz_id"], unique=False)
    op.create_table(
        "event_assignments",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("assigned_by", sa.Uuid(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(
            ["assigned_by"],
            ["users.id"],
            name=op.f("fk_event_assignments_assigned_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_event_assignments_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_event_assignments_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_assignments")),
    )
    op.create_index(
        op.f("ix_event_assignments_event_id"), "event_assignments", ["event_id"], unique=False
    )
    op.create_index(
        "uq_event_assignments_one_active",
        "event_assignments",
        ["event_id"],
        unique=True,
        postgresql_where=sa.text("active"),
    )
    op.create_table(
        "event_notes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), server_default="work", nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('work', 'postprocess')", name=op.f("ck_event_notes_event_note_kind")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_event_notes_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_event_notes_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_notes")),
    )
    op.create_index(op.f("ix_event_notes_event_id"), "event_notes", ["event_id"], unique=False)
    op.create_table(
        "event_status_history",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.String(length=16), nullable=True),
        sa.Column("to_status", sa.String(length=16), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("changed_by", sa.Uuid(), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["changed_by"],
            ["users.id"],
            name=op.f("fk_event_status_history_changed_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_event_status_history_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_status_history")),
    )
    op.create_index(
        op.f("ix_event_status_history_event_id"), "event_status_history", ["event_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_event_status_history_event_id"), table_name="event_status_history")
    op.drop_table("event_status_history")
    op.drop_index(op.f("ix_event_notes_event_id"), table_name="event_notes")
    op.drop_table("event_notes")
    op.drop_index(
        "uq_event_assignments_one_active",
        table_name="event_assignments",
        postgresql_where=sa.text("active"),
    )
    op.drop_index(op.f("ix_event_assignments_event_id"), table_name="event_assignments")
    op.drop_table("event_assignments")
    op.drop_index(op.f("ix_events_bbz_id"), table_name="events")
    op.drop_table("events")
