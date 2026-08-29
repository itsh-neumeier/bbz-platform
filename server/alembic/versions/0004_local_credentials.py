"""local_credentials: password material + lockout state for local identities

Revision ID: 0004_local_credentials
Revises: 0003_rbac
Create Date: 2026-08-29

Roadmap E02-03 (#29). One row per ``provider='local'`` auth identity. Lockout
counters live here so both application nodes share the same state. Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_local_credentials"
down_revision: str | None = "0003_rbac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)
NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "local_credentials",
        sa.Column("auth_identity_id", sa.Uuid(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("must_change", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("locked_until", TZ, nullable=True),
        sa.Column("password_changed_at", TZ, server_default=NOW, nullable=False),
        sa.Column("created_at", TZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["auth_identity_id"],
            ["auth_identities.id"],
            name=op.f("fk_local_credentials_auth_identity_id_auth_identities"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("auth_identity_id", name=op.f("pk_local_credentials")),
    )


def downgrade() -> None:
    op.drop_table("local_credentials")
