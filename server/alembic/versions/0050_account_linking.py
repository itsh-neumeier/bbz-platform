"""auth_provider_config, oidc_login_flows.link_user_id

Revision ID: 0050_account_linking
Revises: 0049_advanced_rbac
Create Date: 2026-09-01

Roadmap E21-08. Account linking: an OIDC flow started for *linking* carries the
target user (``oidc_login_flows.link_user_id``); ``auth_provider_config`` is the
admin-facing per-provider display / offered toggle (it never enables auth the
env does not back). All times ``timestamptz`` (ADR-0017). Additive /
expand-only, reversible.

expand-contract: safe
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0050_account_linking"
down_revision: str | None = "0049_advanced_rbac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TS = sa.DateTime(timezone=True)
_NOW = sa.text("now()")


def upgrade() -> None:
    op.add_column("oidc_login_flows", sa.Column("link_user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_oidc_login_flows_link_user_id_users"),
        "oidc_login_flows",
        "users",
        ["link_user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_table(
        "auth_provider_config",
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "display_name", sa.String(length=80), server_default=sa.text("''"), nullable=False
        ),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("updated_at", _TS, server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_auth_provider_config_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("provider", name=op.f("pk_auth_provider_config")),
    )


def downgrade() -> None:
    op.drop_table("auth_provider_config")
    op.drop_constraint(
        op.f("fk_oidc_login_flows_link_user_id_users"), "oidc_login_flows", type_="foreignkey"
    )
    op.drop_column("oidc_login_flows", "link_user_id")
