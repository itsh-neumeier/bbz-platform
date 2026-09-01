"""oidc_login_flows

Revision ID: 0044_oidc_login_flows
Revises: 0043_monitor_profile_name_uq
Create Date: 2026-09-01

Roadmap E21-01. One short-lived row per in-flight OIDC login (state -> nonce +
Fernet-encrypted PKCE verifier). The callback consumes and deletes its row;
E22 housekeeping purges expired ones. DB-backed so a post-failover callback on
another node still resolves. All times ``timestamptz`` (ADR-0017). Additive /
expand-only, reversible.

expand-contract: safe
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0044_oidc_login_flows"
down_revision: str | None = "0043_monitor_profile_name_uq"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "oidc_login_flows",
        sa.Column("state", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("nonce", sa.String(length=128), nullable=False),
        sa.Column("code_verifier_enc", sa.Text(), nullable=False),
        sa.Column("redirect_uri", sa.String(length=500), nullable=False),
        sa.Column("created_at", _TS, nullable=False),
        sa.Column("expires_at", _TS, nullable=False),
        sa.PrimaryKeyConstraint("state", name=op.f("pk_oidc_login_flows")),
    )
    op.create_index(op.f("ix_oidc_login_flows_expires_at"), "oidc_login_flows", ["expires_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_oidc_login_flows_expires_at"), table_name="oidc_login_flows")
    op.drop_table("oidc_login_flows")
