"""sip_trunks + sip_numbers — ITSP trunk config BBZ renders to Asterisk (ADR-0034)

Revision ID: 0057_sip_trunks
Revises: 0056_sip_gateway
Create Date: 2026-09-07

Roadmap E13-09. BBZ stores the SIP trunk (LEONET / Telekom / …) and the public
numbers on it; a pure service renders ``pjsip.conf`` + a dialplan from these
rows and a sync script delivers it to the Asterisk box. The trunk auth password
is stored only as ``auth_password_ciphertext`` (Fernet, ``BBZ_SIP_ENCRYPTION_KEY``)
— never plaintext, a log, or an audit row. Reversible; expand-contract: safe
(two new tables, nothing else touched).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0057_sip_trunks"
down_revision: str | None = "0056_sip_gateway"
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
        "sip_trunks",
        sa.Column("trunk_id", sa.String(64), nullable=False),
        _col("provider", sa.String(16), "'generic'"),
        _col("display_name", sa.String(120), "''"),
        _col("enabled", sa.Boolean(), "false"),
        _col("sip_server", sa.String(255), "''"),
        _col("sip_port", sa.Integer(), "5060"),
        _col("transport", sa.String(8), "'udp'"),
        _col("outbound_proxy", sa.String(255), "''"),
        _col("from_domain", sa.String(255), "''"),
        _col("registration", sa.Boolean(), "true"),
        _col("auth_username", sa.String(255), "''"),
        _col("auth_password_ciphertext", sa.Text(), "''"),
        _col("match_hosts", sa.Text(), "''"),
        _col("codecs", sa.String(255), "'alaw,ulaw'"),
        _col("dtmf_mode", sa.String(8), "'rfc4733'"),
        _col("caller_id_e164", sa.String(20), "''"),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_sip_trunks_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("trunk_id", name=op.f("pk_sip_trunks")),
        sa.CheckConstraint(
            "provider in ('leonet', 'telekom', 'generic')", name="ck_sip_trunk_provider"
        ),
        sa.CheckConstraint("transport in ('udp', 'tcp', 'tls')", name="ck_sip_trunk_transport"),
    )
    op.create_table(
        "sip_numbers",
        sa.Column("e164", sa.String(20), nullable=False),
        sa.Column("trunk_id", sa.String(64), nullable=False),
        _col("bbz_line_id", sa.String(64), "''"),
        _col("label", sa.String(120), "''"),
        _col("registration", sa.Boolean(), "false"),
        _col("auth_username", sa.String(255), "''"),
        _col("auth_password_ciphertext", sa.Text(), "''"),
        _col("enabled", sa.Boolean(), "true"),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["trunk_id"],
            ["sip_trunks.trunk_id"],
            name=op.f("fk_sip_numbers_trunk_id_sip_trunks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("e164", name=op.f("pk_sip_numbers")),
        sa.CheckConstraint(r"e164 ~ '^\+[1-9][0-9]{1,14}$'", name="ck_sip_number_e164"),
    )
    op.create_index(op.f("ix_sip_numbers_trunk_id"), "sip_numbers", ["trunk_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_sip_numbers_trunk_id"), table_name="sip_numbers")
    op.drop_table("sip_numbers")
    op.drop_table("sip_trunks")
