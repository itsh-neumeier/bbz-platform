"""sip_moh_files + per-line ring/hold music (E13-12 / #817)

Revision ID: 0059_sip_moh
Revises: 0058_sip_webrtc
Create Date: 2026-09-08

Roadmap E13-12. Uploadable hold / queue music per SIP line. File **metadata**
lives here; the WAV bytes live in ``$BBZ_MOH_DIR`` on disk, keyed by the row id
— never in the DB. Two nullable FKs on ``sip_lines``: ``ring_moh_file_id`` (plays
while a call waits for an operator) and ``hold_moh_file_id`` (plays while an
established call is on hold). Reversible; expand-contract safe.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0059_sip_moh"
down_revision: str | None = "0058_sip_webrtc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    now = sa.text("now()")
    op.create_table(
        "sip_moh_files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column(
            "original_filename", sa.String(255), nullable=False, server_default=sa.text("''")
        ),
        sa.Column("mime", sa.String(64), nullable=False, server_default=sa.text("''")),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("sha256", sa.String(64), nullable=False, server_default=sa.text("''")),
        sa.Column("uploaded_by", sa.Uuid(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name=op.f("fk_sip_moh_files_uploaded_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sip_moh_files")),
    )
    for col in ("ring_moh_file_id", "hold_moh_file_id"):
        op.add_column("sip_lines", sa.Column(col, sa.Uuid(), nullable=True))
        op.create_foreign_key(
            op.f(f"fk_sip_lines_{col}_sip_moh_files"),
            "sip_lines",
            "sip_moh_files",
            [col],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    for col in ("hold_moh_file_id", "ring_moh_file_id"):
        op.drop_constraint(
            op.f(f"fk_sip_lines_{col}_sip_moh_files"), "sip_lines", type_="foreignkey"
        )
        op.drop_column("sip_lines", col)
    op.drop_table("sip_moh_files")
