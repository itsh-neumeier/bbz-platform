"""integration_camera_mappings: endpoint / alarm source -> camera(s)

Revision ID: 0034_camera_mappings
Revises: 0033_unmapped_signals
Create Date: 2026-08-31

Roadmap E16-05. MASTER_PROMPT §34 / .ai/INTEGRATIONS_CODA_VIDEO.md "Admin
mapping". A mapping is anchored on a technical endpoint OR on an external alarm
source id (CHECK ``anchor``). Reversible, expand-only.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034_camera_mappings"
down_revision: str | None = "0033_unmapped_signals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "integration_camera_mappings",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("endpoint_id", sa.Uuid(), nullable=True),
        sa.Column("alarm_source_external_id", sa.String(length=200), nullable=True),
        sa.Column("camera_external_ref", sa.String(length=200), nullable=False),
        sa.Column("ordinal", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("provider_instance_id", sa.String(length=64), nullable=True),
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
            "endpoint_id IS NOT NULL OR alarm_source_external_id IS NOT NULL",
            name="anchor",
        ),
        sa.ForeignKeyConstraint(
            ["endpoint_id"],
            ["technical_endpoints.id"],
            name=op.f("fk_integration_camera_mappings_endpoint_id_technical_endpoints"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integration_camera_mappings")),
    )
    op.create_index(
        op.f("ix_integration_camera_mappings_endpoint_id"),
        "integration_camera_mappings",
        ["endpoint_id"],
    )
    op.create_index(
        op.f("ix_integration_camera_mappings_alarm_source_external_id"),
        "integration_camera_mappings",
        ["alarm_source_external_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_integration_camera_mappings_alarm_source_external_id"),
        table_name="integration_camera_mappings",
    )
    op.drop_index(
        op.f("ix_integration_camera_mappings_endpoint_id"),
        table_name="integration_camera_mappings",
    )
    op.drop_table("integration_camera_mappings")
