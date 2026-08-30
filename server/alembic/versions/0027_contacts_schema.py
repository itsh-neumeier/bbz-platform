"""contacts, contact_numbers, contact_priorities

Revision ID: 0027_contacts_schema
Revises: 0026_telephony_core
Create Date: 2026-08-31

Roadmap E14-01. The phone book data model (MASTER_PROMPT §14, §13.9). Schema
only. ``contact_numbers.e164`` is stored normalized (CHECK enforces the E.164
shape); ``unique(contact_id, e164)``. ``contact_priorities`` is current-state,
one row per contact. Reversible, expand-only.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_contacts_schema"
down_revision: str | None = "0026_telephony_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PRIORITIES = ("low", "medium", "high")
_E164 = r"e164 ~ '^\+[1-9][0-9]{1,14}$'"


def _ts(name: str) -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "contacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("org", sa.String(length=200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("quick_dial", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("bbz_id", sa.Uuid(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contacts")),
    )
    op.create_index(op.f("ix_contacts_bbz_id"), "contacts", ["bbz_id"])

    op.create_table(
        "contact_numbers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("e164", sa.String(length=16), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=True),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(_E164, name="e164_normalized"),
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["contacts.id"],
            name=op.f("fk_contact_numbers_contact_id_contacts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contact_numbers")),
        sa.UniqueConstraint("contact_id", "e164", name="uq_contact_numbers_contact_id_e164"),
    )
    op.create_index(op.f("ix_contact_numbers_contact_id"), "contact_numbers", ["contact_id"])

    op.create_table(
        "contact_priorities",
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("set_by", sa.Uuid(), nullable=True),
        sa.Column(
            "set_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "priority IN (" + ", ".join(f"'{p}'" for p in _PRIORITIES) + ")",
            name="priority_level",
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["contacts.id"],
            name=op.f("fk_contact_priorities_contact_id_contacts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["set_by"],
            ["users.id"],
            name=op.f("fk_contact_priorities_set_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("contact_id", name=op.f("pk_contact_priorities")),
    )


def downgrade() -> None:
    op.drop_table("contact_priorities")
    op.drop_index(op.f("ix_contact_numbers_contact_id"), table_name="contact_numbers")
    op.drop_table("contact_numbers")
    op.drop_index(op.f("ix_contacts_bbz_id"), table_name="contacts")
    op.drop_table("contacts")
