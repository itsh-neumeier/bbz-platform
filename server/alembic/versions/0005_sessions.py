"""sessions: server-side session registry for refresh-token revocation

Revision ID: 0005_sessions
Revises: 0004_local_credentials
Create Date: 2026-08-29

Roadmap E02-05 (#31). Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_sessions"
down_revision: str | None = "0004_local_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("refresh_token_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("client_id", sa.String(length=64), nullable=True),
        sa.Column("workplace_id", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=400), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_sessions_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.UniqueConstraint("refresh_token_hash", name=op.f("uq_sessions_refresh_token_hash")),
    )
    op.create_index(op.f("ix_sessions_revoked_at"), "sessions", ["revoked_at"], unique=False)
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_revoked_at"), table_name="sessions")
    op.drop_table("sessions")
