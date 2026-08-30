"""application_catalog + application_catalog_scopes

Revision ID: 0025_application_catalog
Revises: 0024_bku_agent_schema
Create Date: 2026-08-30

Roadmap E10-02. The centrally managed operational web-app / link catalog
(MASTER_PROMPT §28.2). Schema only — it is the allow-list the BKU agent launches
from. ``url`` is CHECK-constrained to ``http``/``https``; ``launch_mode`` to a
closed set. Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_application_catalog"
down_revision: str | None = "0024_bku_agent_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "application_catalog",
        sa.Column("app_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("icon", sa.String(length=300), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("browser_profile", sa.String(length=100), nullable=True),
        sa.Column("launch_mode", sa.String(length=16), server_default="window", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("target_monitor_hint", sa.String(length=64), nullable=True),
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
        sa.CheckConstraint("url ~* '^https?://'", name="application_catalog_url_scheme"),
        sa.CheckConstraint(
            "launch_mode IN ('window', 'app_window', 'tab')",
            name="application_catalog_launch_mode",
        ),
        sa.PrimaryKeyConstraint("app_id", name=op.f("pk_application_catalog")),
    )

    op.create_table(
        "application_catalog_scopes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("app_id", sa.Uuid(), nullable=False),
        sa.Column("role_key", sa.String(length=64), nullable=True),
        sa.Column("bbz_id", sa.Uuid(), nullable=True),
        sa.Column("workplace_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["app_id"],
            ["application_catalog.app_id"],
            name=op.f("fk_app_catalog_scopes_app_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_catalog_scopes")),
    )
    op.create_index(
        op.f("ix_application_catalog_scopes_app_id"), "application_catalog_scopes", ["app_id"]
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_application_catalog_scopes_app_id"), table_name="application_catalog_scopes"
    )
    op.drop_table("application_catalog_scopes")
    op.drop_table("application_catalog")
