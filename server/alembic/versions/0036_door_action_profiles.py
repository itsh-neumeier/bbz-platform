"""door_action_profiles + FK from technical_endpoints.dtmf_profile_id

Revision ID: 0036_door_action_profiles
Revises: 0035_door_station_fields
Create Date: 2026-08-31

Roadmap E17-02. ``door_action_profiles`` stores the door-open DTMF code
**encrypted** (MASTER_PROMPT §30, .ai/SECURITY.md — audit the profile id, never
the code). Also wires the FK from ``technical_endpoints.dtmf_profile_id`` (the
column was added in 0035) to this table, ``ON DELETE SET NULL``. Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036_door_action_profiles"
down_revision: str | None = "0035_door_station_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "door_action_profiles",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("dtmf_ciphertext", sa.Text(), nullable=False),
        sa.Column(
            "post_dtmf_delay_ms", sa.Integer(), server_default=sa.text("500"), nullable=False
        ),
        sa.Column("auto_hangup", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint("post_dtmf_delay_ms >= 0 AND post_dtmf_delay_ms <= 10000", name="delay"),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_door_action_profiles_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_door_action_profiles")),
        sa.UniqueConstraint("name", name=op.f("uq_door_action_profiles_name")),
    )
    op.create_foreign_key(
        op.f("fk_technical_endpoints_dtmf_profile_id_door_action_profiles"),
        "technical_endpoints",
        "door_action_profiles",
        ["dtmf_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_technical_endpoints_dtmf_profile_id_door_action_profiles"),
        "technical_endpoints",
        type_="foreignkey",
    )
    op.drop_table("door_action_profiles")
