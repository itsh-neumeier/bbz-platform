"""local_totp: optional TOTP second factor for local identities

Revision ID: 0007_local_totp
Revises: 0006_audit_events
Create Date: 2026-08-29

Roadmap E02-13 (#39). Secret stored encrypted (application-side Fernet).
Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_local_totp"
down_revision: str | None = "0006_audit_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FK_TOTP = "fk_local_totp_auth_identity_id_auth_identities"
_FK_RC = "fk_local_totp_recovery_codes_auth_identity_id_auth_identities"


def upgrade() -> None:
    op.create_table(
        "local_totp",
        sa.Column("auth_identity_id", sa.Uuid(), nullable=False),
        sa.Column("secret_ciphertext", sa.Text(), nullable=False),
        sa.Column("activated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("last_step", sa.BigInteger(), nullable=True),
        sa.Column(
            "enrolled_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["auth_identity_id"], ["auth_identities.id"], name=op.f(_FK_TOTP), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("auth_identity_id", name=op.f("pk_local_totp")),
    )
    op.create_table(
        "local_totp_recovery_codes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("auth_identity_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["auth_identity_id"], ["auth_identities.id"], name=op.f(_FK_RC), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_local_totp_recovery_codes")),
        sa.UniqueConstraint(
            "auth_identity_id",
            "code_hash",
            name=op.f("uq_local_totp_recovery_codes_auth_identity_id_code_hash"),
        ),
    )
    op.create_index(
        op.f("ix_local_totp_recovery_codes_auth_identity_id"),
        "local_totp_recovery_codes",
        ["auth_identity_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_local_totp_recovery_codes_auth_identity_id"),
        table_name="local_totp_recovery_codes",
    )
    op.drop_table("local_totp_recovery_codes")
    op.drop_table("local_totp")
