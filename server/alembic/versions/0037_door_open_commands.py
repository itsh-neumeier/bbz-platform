"""door_open_commands — the door-open flow state machine

Revision ID: 0037_door_open_commands
Revises: 0036_door_action_profiles
Create Date: 2026-08-31

Roadmap E17-05 / ADR-0025. One row per ``door.open`` request (keyed by the client
``X-Command-Id``): answer the doorbell call if needed, await media, send the DTMF
sequence exactly once, post-DTMF delay, hang up, audited outcome. The DTMF code is
**never** stored here — only the ``door_action_profiles`` id. Additive, reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037_door_open_commands"
down_revision: str | None = "0036_door_action_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "door_open_commands",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("command_id", sa.Uuid(), nullable=False),
        sa.Column("endpoint_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=True),
        sa.Column("call_id", sa.String(length=128), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.Uuid(), nullable=True),
        sa.Column("dtmf_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["endpoint_id"],
            ["technical_endpoints.id"],
            name=op.f("fk_door_open_commands_endpoint_id_technical_endpoints"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["door_action_profiles.id"],
            name=op.f("fk_door_open_commands_profile_id_door_action_profiles"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name=op.f("fk_door_open_commands_requested_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_door_open_commands")),
        sa.UniqueConstraint("command_id", name=op.f("uq_door_open_commands_command_id")),
    )
    op.create_index(
        op.f("ix_door_open_commands_endpoint_id"),
        "door_open_commands",
        ["endpoint_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_door_open_commands_endpoint_id"), table_name="door_open_commands")
    op.drop_table("door_open_commands")
