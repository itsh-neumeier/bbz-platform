"""identity: users, auth_identities, user_presence

Revision ID: 0002_identity
Revises: 0001_baseline
Create Date: 2026-08-29

Roadmap E02-01 (#27). Schema only - no data, no domain logic. Expand-only
(adds tables); fully reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_identity"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)
NOW = sa.text("now()")


def _ts(col: str) -> sa.Column:
    return sa.Column(col, TZ, server_default=NOW, nullable=False)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("external_ref", sa.String(length=255), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("status IN ('active', 'disabled')", name=op.f("ck_users_user_status")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_table(
        "auth_identities",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("credential_ref", sa.String(length=255), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(
            "provider IN ('local', 'entra_oidc', 'ldap_ad')",
            name=op.f("ck_auth_identities_auth_provider"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_auth_identities_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_identities")),
        sa.UniqueConstraint(
            "provider", "subject", name=op.f("uq_auth_identities_provider_subject")
        ),
    )
    op.create_index(
        op.f("ix_auth_identities_user_id"), "auth_identities", ["user_id"], unique=False
    )
    op.create_table(
        "user_presence",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=16), server_default="offline", nullable=False),
        _ts("changed_at"),
        sa.Column("changed_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "state IN ('available', 'pause', 'offline')",
            name=op.f("ck_user_presence_presence_state"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_presence_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["changed_by"],
            ["users.id"],
            name=op.f("fk_user_presence_changed_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_presence")),
    )


def downgrade() -> None:
    op.drop_table("user_presence")
    op.drop_index(op.f("ix_auth_identities_user_id"), table_name="auth_identities")
    op.drop_table("auth_identities")
    op.drop_table("users")
