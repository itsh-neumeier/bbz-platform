"""mfa_policies, sessions.mfa_verified_at

Revision ID: 0047_mfa_policy
Revises: 0046_directory_sync_state
Create Date: 2026-09-01

Roadmap E21-05. ``mfa_policies`` — a role that must have MFA (with a grace
period for newly-assigned users); a user requires MFA if they hold any policy'd
role. ``sessions.mfa_verified_at`` records when a session's login satisfied a
TOTP/recovery challenge — read by the step-up dependency. All times
``timestamptz`` (ADR-0017). Additive / expand-only, reversible.

expand-contract: safe
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0047_mfa_policy"
down_revision: str | None = "0046_directory_sync_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TS = sa.DateTime(timezone=True)
_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "mfa_policies",
        sa.Column("role_key", sa.String(length=64), nullable=False),
        sa.Column("grace_period_days", sa.Integer(), server_default=sa.text("7"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("updated_at", _TS, server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_mfa_policies_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("role_key", name=op.f("pk_mfa_policies")),
    )
    op.add_column("sessions", sa.Column("mfa_verified_at", _TS, nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "mfa_verified_at")
    op.drop_table("mfa_policies")
