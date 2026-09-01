"""webauthn_credentials, webauthn_challenges

Revision ID: 0048_webauthn
Revises: 0047_mfa_policy
Create Date: 2026-09-01

Roadmap E21-06. FIDO2 credentials for local accounts + the short-lived,
single-use server challenge for each registration / authentication ceremony
(DB-backed for HA). All times ``timestamptz`` (ADR-0017). Additive /
expand-only, reversible.

expand-contract: safe
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0048_webauthn"
down_revision: str | None = "0047_mfa_policy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TS = sa.DateTime(timezone=True)
_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "webauthn_credentials",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("auth_identity_id", sa.Uuid(), nullable=False),
        sa.Column("credential_id", sa.LargeBinary(), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "transports", sa.String(length=120), server_default=sa.text("''"), nullable=False
        ),
        sa.Column("aaguid", sa.String(length=36), server_default=sa.text("''"), nullable=False),
        sa.Column("name", sa.String(length=80), server_default=sa.text("''"), nullable=False),
        sa.Column("last_used_at", _TS, nullable=True),
        sa.Column("created_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("updated_at", _TS, server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["auth_identity_id"],
            ["auth_identities.id"],
            name=op.f("fk_webauthn_credentials_auth_identity_id_auth_identities"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webauthn_credentials")),
        sa.UniqueConstraint("credential_id", name=op.f("uq_webauthn_credentials_credential_id")),
    )
    op.create_index(
        op.f("ix_webauthn_credentials_auth_identity_id"),
        "webauthn_credentials",
        ["auth_identity_id"],
    )

    op.create_table(
        "webauthn_challenges",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("auth_identity_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("challenge", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("expires_at", _TS, nullable=False),
        sa.ForeignKeyConstraint(
            ["auth_identity_id"],
            ["auth_identities.id"],
            name=op.f("fk_webauthn_challenges_auth_identity_id_auth_identities"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_webauthn_challenges_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webauthn_challenges")),
    )
    op.create_index(op.f("ix_webauthn_challenges_user_id"), "webauthn_challenges", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_webauthn_challenges_user_id"), table_name="webauthn_challenges")
    op.drop_table("webauthn_challenges")
    op.drop_index(
        op.f("ix_webauthn_credentials_auth_identity_id"), table_name="webauthn_credentials"
    )
    op.drop_table("webauthn_credentials")
