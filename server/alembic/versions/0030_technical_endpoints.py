"""technical_endpoints, technical_endpoint_numbers

Revision ID: 0030_technical_endpoints
Revises: 0029_call_caller_resolution
Create Date: 2026-08-31

Roadmap E15-01. Configured technical signal sources (MASTER_PROMPT §29 /
.ai/TECHNICAL_TRIGGERS.md) — kept strictly separate from ``contacts``. ``type``
is a closed CHECK set incl. ``custom``; ``default_priority`` maps to an event
priority. Reversible, expand-only.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030_technical_endpoints"
down_revision: str | None = "0029_call_caller_resolution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TYPES = ("door_station", "bma", "panic_button", "video_alarm", "alarm_dialer", "custom")
_PRIORITIES = ("critical", "high", "medium", "low")


def _q(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _ts(name: str) -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "technical_endpoints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("site", sa.String(length=200), nullable=True),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("provider_id", sa.String(length=64), nullable=True),
        sa.Column(
            "external_source_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("default_priority", sa.String(length=16), nullable=True),
        sa.Column("popup_profile", sa.String(length=64), nullable=True),
        sa.Column("escalation_profile", sa.String(length=64), nullable=True),
        sa.Column(
            "workflow_selection_policy",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "active_config_version", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(f"type IN ({_q(_TYPES)})", name="type"),
        sa.CheckConstraint(
            f"default_priority IS NULL OR default_priority IN ({_q(_PRIORITIES)})",
            name="default_priority",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_technical_endpoints")),
    )
    op.create_index(
        op.f("ix_technical_endpoints_provider_id"), "technical_endpoints", ["provider_id"]
    )

    op.create_table(
        "technical_endpoint_numbers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("endpoint_id", sa.Uuid(), nullable=False),
        sa.Column("calling_pattern", sa.String(length=64), nullable=True),
        sa.Column("called_pattern", sa.String(length=64), nullable=True),
        sa.Column("cti_route_point", sa.String(length=64), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.ForeignKeyConstraint(
            ["endpoint_id"],
            ["technical_endpoints.id"],
            name=op.f("fk_technical_endpoint_numbers_endpoint_id_technical_endpoints"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_technical_endpoint_numbers")),
    )
    op.create_index(
        op.f("ix_technical_endpoint_numbers_endpoint_id"),
        "technical_endpoint_numbers",
        ["endpoint_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_technical_endpoint_numbers_endpoint_id"),
        table_name="technical_endpoint_numbers",
    )
    op.drop_table("technical_endpoint_numbers")
    op.drop_index(op.f("ix_technical_endpoints_provider_id"), table_name="technical_endpoints")
    op.drop_table("technical_endpoints")
