"""lines, calls, call_participants, call_documentation

Revision ID: 0026_telephony_core
Revises: 0025_application_catalog
Create Date: 2026-08-30

Roadmap E11-01. Telephony core objects (MASTER_PROMPT §14). Schema only —
vendor-neutral. ``bbz_call_id`` is BBZ-owned and independent of the provider's
``source_call_id``; ``category`` is a closed CHECK set, nullable until set.
Reversible, expand-only.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_telephony_core"
down_revision: str | None = "0025_application_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CALL_STATES = (
    "offered",
    "ringing",
    "connected",
    "held",
    "transferring",
    "disconnected",
    "failed",
    "ended_pending_documentation",
)
_CATEGORIES = (
    "information_request",
    "technical_fault",
    "cleaning_report_customer",
    "evu_evi_notice",
    "other",
)
_ROLES = ("caller", "callee", "operator", "transfer_target", "conference")


def _q(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _ts(name: str) -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=True),
        sa.Column("state", sa.String(length=20), server_default="unknown", nullable=False),
        sa.Column("workplace_id", sa.Uuid(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(
            "state IN ('in_service', 'out_of_service', 'unknown')", name="line_state"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lines")),
        sa.UniqueConstraint("provider", "external_id", name="uq_lines_provider_external"),
    )
    op.create_index(op.f("ix_lines_provider"), "lines", ["provider"])
    op.create_index(op.f("ix_lines_workplace_id"), "lines", ["workplace_id"])

    op.create_table(
        "calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("bbz_call_id", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("source_call_id", sa.String(length=128), nullable=True),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=32), server_default="offered", nullable=False),
        sa.Column("line_id", sa.Uuid(), nullable=True),
        sa.Column("workplace_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("direction IN ('inbound', 'outbound')", name="call_direction"),
        sa.CheckConstraint(f"state IN ({_q(_CALL_STATES)})", name="call_state"),
        sa.ForeignKeyConstraint(
            ["line_id"], ["lines.id"], name=op.f("fk_calls_line_id"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calls")),
        sa.UniqueConstraint("bbz_call_id", name=op.f("uq_calls_bbz_call_id")),
    )
    op.create_index(op.f("ix_calls_provider"), "calls", ["provider"])
    op.create_index(op.f("ix_calls_source_call_id"), "calls", ["source_call_id"])
    op.create_index(op.f("ix_calls_state"), "calls", ["state"])
    op.create_index(op.f("ix_calls_line_id"), "calls", ["line_id"])
    op.create_index(op.f("ix_calls_workplace_id"), "calls", ["workplace_id"])

    op.create_table(
        "call_participants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("call_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.String(length=64), nullable=True),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("role", sa.String(length=20), nullable=False),
        _ts("created_at"),
        sa.CheckConstraint(f"role IN ({_q(_ROLES)})", name="call_participant_role"),
        sa.ForeignKeyConstraint(
            ["call_id"],
            ["calls.id"],
            name=op.f("fk_call_participants_call_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_call_participants")),
    )
    op.create_index(op.f("ix_call_participants_call_id"), "call_participants", ["call_id"])

    op.create_table(
        "call_documentation",
        sa.Column("call_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=True),
        sa.Column("free_text", sa.Text(), nullable=True),
        sa.Column("documented_by", sa.Uuid(), nullable=True),
        sa.Column("documented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mandatory_done", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        _ts("updated_at"),
        sa.CheckConstraint(
            f"category IS NULL OR category IN ({_q(_CATEGORIES)})",
            name="call_documentation_category",
        ),
        sa.ForeignKeyConstraint(
            ["call_id"],
            ["calls.id"],
            name=op.f("fk_call_documentation_call_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["documented_by"],
            ["users.id"],
            name=op.f("fk_call_documentation_documented_by"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("call_id", name=op.f("pk_call_documentation")),
    )


def downgrade() -> None:
    op.drop_table("call_documentation")
    op.drop_index(op.f("ix_call_participants_call_id"), table_name="call_participants")
    op.drop_table("call_participants")
    for ix in ("workplace_id", "line_id", "state", "source_call_id", "provider"):
        op.drop_index(op.f(f"ix_calls_{ix}"), table_name="calls")
    op.drop_table("calls")
    op.drop_index(op.f("ix_lines_workplace_id"), table_name="lines")
    op.drop_index(op.f("ix_lines_provider"), table_name="lines")
    op.drop_table("lines")
