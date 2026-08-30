"""bku_agents, bku_agent_enrollments, bku_agent_commands

Revision ID: 0024_bku_agent_schema
Revises: 0023_events_delete_guard
Create Date: 2026-08-30

Roadmap E10-01. Agent registration, enrollment and command history for the
``bku-agent`` (MASTER_PROMPT §34, ``.ai/BKU_AGENT.md``). Schema only. Reversible.

* one active agent per workplace (partial unique index)
* enrollment tokens stored hashed only, single-use, time-boxed
* the command ``type`` is a closed CHECK set — never arbitrary shell / URL / exec
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024_bku_agent_schema"
down_revision: str | None = "0023_events_delete_guard"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COMMAND_TYPES = (
    "get_status",
    "get_session_state",
    "ping",
    "launch_catalog_app",
    "focus_catalog_app",
    "close_catalog_app",
    "logout_interactive_user",
    "restart_workstation",
)
_COMMAND_STATUS = ("pending", "sent", "acked", "done", "failed", "expired")


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.create_table(
        "bku_agents",
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("workplace_id", sa.Uuid(), nullable=False),
        sa.Column("device_pubkey", sa.Text(), nullable=False),
        sa.Column("generation", sa.BigInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column(
            "enrolled_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(_in("status", ("active", "revoked")), name="bku_agent_status"),
        sa.PrimaryKeyConstraint("agent_id", name=op.f("pk_bku_agents")),
    )
    op.create_index(op.f("ix_bku_agents_workplace_id"), "bku_agents", ["workplace_id"])
    op.create_index(
        "uq_bku_agents_one_active_per_workplace",
        "bku_agents",
        ["workplace_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "bku_agent_enrollments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("workplace_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("agent_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_bku_enroll_created_by"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["bku_agents.agent_id"],
            name=op.f("fk_bku_enroll_agent_id"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bku_agent_enrollments")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_bku_agent_enrollments_token_hash")),
    )
    op.create_index(
        op.f("ix_bku_agent_enrollments_workplace_id"), "bku_agent_enrollments", ["workplace_id"]
    )

    op.create_table(
        "bku_agent_commands",
        sa.Column("command_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("workplace_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "issued_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=True),
        sa.Column("expected_generation", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(_in("type", _COMMAND_TYPES), name="bku_command_type"),
        sa.CheckConstraint(_in("status", _COMMAND_STATUS), name="bku_command_status"),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["bku_agents.agent_id"],
            name=op.f("fk_bku_command_agent_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name=op.f("fk_bku_command_requested_by"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("command_id", name=op.f("pk_bku_agent_commands")),
    )
    op.create_index(op.f("ix_bku_agent_commands_agent_id"), "bku_agent_commands", ["agent_id"])
    op.create_index(
        op.f("ix_bku_agent_commands_workplace_id"), "bku_agent_commands", ["workplace_id"]
    )


def downgrade() -> None:
    op.drop_table("bku_agent_commands")
    op.drop_table("bku_agent_enrollments")
    op.drop_index(
        "uq_bku_agents_one_active_per_workplace",
        table_name="bku_agents",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.drop_index(op.f("ix_bku_agents_workplace_id"), table_name="bku_agents")
    op.drop_table("bku_agents")
