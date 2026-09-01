"""user_roles validity window, permission_delegations

Revision ID: 0049_advanced_rbac
Revises: 0048_webauthn
Create Date: 2026-09-01

Roadmap E21-07. Time-bound role grants (``user_roles.valid_from`` / ``valid_to``)
and temporary permission delegation (``permission_delegations`` — always
expires, revocable). Conditions on ``role_permissions`` already exist (E02-07);
E21-07 only makes them evaluate (no schema change for that). All times
``timestamptz`` (ADR-0017). Additive / expand-only, reversible.

expand-contract: safe
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0049_advanced_rbac"
down_revision: str | None = "0048_webauthn"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TS = sa.DateTime(timezone=True)
_NOW = sa.text("now()")


def upgrade() -> None:
    op.add_column("user_roles", sa.Column("valid_from", _TS, nullable=True))
    op.add_column("user_roles", sa.Column("valid_to", _TS, nullable=True))

    op.create_table(
        "permission_delegations",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("from_user_id", sa.Uuid(), nullable=False),
        sa.Column("to_user_id", sa.Uuid(), nullable=False),
        sa.Column("permission_key", sa.String(length=100), nullable=False),
        sa.Column(
            "scope", sa.String(length=32), server_default=sa.text("'global'"), nullable=False
        ),
        sa.Column("granted_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("expires_at", _TS, nullable=False),
        sa.Column("revoked_at", _TS, nullable=True),
        sa.ForeignKeyConstraint(
            ["from_user_id"],
            ["users.id"],
            name=op.f("fk_permission_delegations_from_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["to_user_id"],
            ["users.id"],
            name=op.f("fk_permission_delegations_to_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_permission_delegations")),
    )
    op.create_index(
        op.f("ix_permission_delegations_to_user_id"),
        "permission_delegations",
        ["to_user_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_permission_delegations_to_user_id"), table_name="permission_delegations")
    op.drop_table("permission_delegations")
    op.drop_column("user_roles", "valid_to")
    op.drop_column("user_roles", "valid_from")
