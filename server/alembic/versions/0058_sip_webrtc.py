"""sip_webrtc_endpoints — per-operator WebRTC SIP endpoint (ADR-0035)

Revision ID: 0058_sip_webrtc
Revises: 0057_sip_trunks
Create Date: 2026-09-08

Roadmap E13-11. Each operator that may take calls in the browser gets a WebRTC
SIP endpoint on BBZ's Asterisk. The SIP password is stored only as
``auth_password_ciphertext`` (Fernet, ``BBZ_SIP_ENCRYPTION_KEY``) — never
plaintext, a log, or an audit row. Reversible; expand-contract: safe (one new
table, nothing else touched).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0058_sip_webrtc"
down_revision: str | None = "0057_sip_trunks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _col(name: str, type_: sa.types.TypeEngine, default: str) -> sa.Column:
    return sa.Column(name, type_, server_default=sa.text(default), nullable=False)


def upgrade() -> None:
    now = sa.text("now()")
    op.create_table(
        "sip_webrtc_endpoints",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        _col("auth_username", sa.String(64), "''"),
        _col("auth_password_ciphertext", sa.Text(), "''"),
        _col("enabled", sa.Boolean(), "true"),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_sip_webrtc_endpoints_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_sip_webrtc_endpoints_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_sip_webrtc_endpoints")),
        sa.UniqueConstraint("auth_username", name="uq_sip_webrtc_auth_username"),
    )


def downgrade() -> None:
    op.drop_table("sip_webrtc_endpoints")
