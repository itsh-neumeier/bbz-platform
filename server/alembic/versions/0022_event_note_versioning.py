"""event note versioning (postprocess notes)

Revision ID: 0022_event_note_versioning
Revises: 0021_workflow_token_resume_at
Create Date: 2026-08-30

Roadmap E20-04. A note is never mutated in place: an edit inserts a new
``event_notes`` row (``version`` + 1, same ``thread_id``) and points the old row
at it via ``superseded_by_id``. Old versions stay forever. ``thread_id`` is
``NULL`` for a v1 row (it is its own thread root); queries use
``COALESCE(thread_id, id)``. The edit path serialises on the superseded row with
``SELECT ... FOR UPDATE``.

expand-contract: safe (additive nullable/defaulted columns + FK/index only; no
backfill, no rewrite).
Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_event_note_versioning"
down_revision: str | None = "0021_workflow_token_resume_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "event_notes",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column("event_notes", sa.Column("thread_id", sa.Uuid(), nullable=True))
    op.add_column("event_notes", sa.Column("superseded_by_id", sa.Uuid(), nullable=True))
    op.add_column("event_notes", sa.Column("edited_by", sa.Uuid(), nullable=True))
    op.add_column("event_notes", sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_event_notes_thread",
        "event_notes",
        "event_notes",
        ["thread_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_event_notes_superseded_by",
        "event_notes",
        "event_notes",
        ["superseded_by_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_event_notes_edited_by",
        "event_notes",
        "users",
        ["edited_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_event_notes_thread_id"), "event_notes", ["thread_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_event_notes_thread_id"), table_name="event_notes")
    op.drop_constraint("fk_event_notes_edited_by", "event_notes", type_="foreignkey")
    op.drop_constraint("fk_event_notes_superseded_by", "event_notes", type_="foreignkey")
    op.drop_constraint("fk_event_notes_thread", "event_notes", type_="foreignkey")
    op.drop_column("event_notes", "edited_at")
    op.drop_column("event_notes", "edited_by")
    op.drop_column("event_notes", "superseded_by_id")
    op.drop_column("event_notes", "thread_id")
    op.drop_column("event_notes", "version")
