"""sip_gateway + sip_lines — DB-backed, UI-managed SIP config (ADR-0033)

Revision ID: 0056_sip_gateway
Revises: 0055_app_settings
Create Date: 2026-09-07

Roadmap E13-07. The ``telephony_sip`` provider's Asterisk/ARI connection lives
in the DB and is managed from the admin UI. The ARI password is stored only as
``ari_password_ciphertext`` (Fernet, ``BBZ_SIP_ENCRYPTION_KEY``) — never in
plaintext, a log, or an audit row. ``sip_lines`` maps BBZ line ids to Asterisk
endpoints. Reversible; expand-contract: safe.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0056_sip_gateway"
down_revision: str | None = "0055_app_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    now = sa.text("now()")
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
    ]


def _col(name: str, type_: sa.types.TypeEngine, default: str) -> sa.Column:
    return sa.Column(name, type_, server_default=sa.text(default), nullable=False)


def upgrade() -> None:
    op.create_table(
        "sip_gateway",
        _col("instance_id", sa.String(64), "'sip'"),
        _col("kind", sa.String(32), "'asterisk_ari'"),
        _col("host", sa.String(255), "''"),
        _col("port", sa.Integer(), "8088"),
        _col("tls", sa.Boolean(), "true"),
        _col("app_name", sa.String(80), "'bbz-sip'"),
        _col("dtmf_transport", sa.String(16), "'rfc2833'"),
        _col("ari_username", sa.String(120), "''"),
        _col("ari_password_ciphertext", sa.Text(), "''"),
        _col("enabled", sa.Boolean(), "false"),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_sip_gateway_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("instance_id", name=op.f("pk_sip_gateway")),
    )
    # the single "sip" gateway row always exists (disabled until configured in
    # the admin UI) — every other column carries a server_default.
    op.execute("INSERT INTO sip_gateway (instance_id) VALUES ('sip')")
    op.create_table(
        "sip_lines",
        sa.Column("bbz_line_id", sa.String(64), nullable=False),
        _col("gateway_instance_id", sa.String(64), "'sip'"),
        sa.Column("asterisk_endpoint", sa.String(255), nullable=False),
        _col("label", sa.String(120), "''"),
        _col("enabled", sa.Boolean(), "true"),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["gateway_instance_id"],
            ["sip_gateway.instance_id"],
            name=op.f("fk_sip_lines_gateway_instance_id_sip_gateway"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("bbz_line_id", name=op.f("pk_sip_lines")),
    )


def downgrade() -> None:
    op.drop_table("sip_lines")
    op.drop_table("sip_gateway")
