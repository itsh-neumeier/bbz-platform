"""auth_group_mappings, external_role_assignments

Revision ID: 0045_auth_group_mappings
Revises: 0044_oidc_login_flows
Create Date: 2026-09-01

Roadmap E21-02. IdP group -> BBZ role mapping (``auth_group_mappings``) plus a
provenance table (``external_role_assignments``) so a login-time reconcile can
drop a role the user lost without touching a manually-assigned one. All times
``timestamptz`` (ADR-0017). Additive / expand-only, reversible.

expand-contract: safe
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0045_auth_group_mappings"
down_revision: str | None = "0044_oidc_login_flows"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TS = sa.DateTime(timezone=True)
_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "auth_group_mappings",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("external_group", sa.String(length=300), nullable=False),
        sa.Column("role_key", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("updated_at", _TS, server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_auth_group_mappings_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_group_mappings")),
        sa.UniqueConstraint(
            "provider", "external_group", "role_key", name="uq_auth_group_mappings_rule"
        ),
    )
    op.create_index(op.f("ix_auth_group_mappings_provider"), "auth_group_mappings", ["provider"])

    op.create_table(
        "external_role_assignments",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("assigned_at", _TS, server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_external_role_assignments_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name=op.f("fk_external_role_assignments_role_id_roles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "user_id", "role_id", "provider", name=op.f("pk_external_role_assignments")
        ),
    )


def downgrade() -> None:
    op.drop_table("external_role_assignments")
    op.drop_index(op.f("ix_auth_group_mappings_provider"), table_name="auth_group_mappings")
    op.drop_table("auth_group_mappings")
