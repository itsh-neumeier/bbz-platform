"""contacts.deleted_at + phone-book search indexes

Revision ID: 0028_contacts_search
Revises: 0027_contacts_schema
Create Date: 2026-08-31

Roadmap E14-02. Soft-delete tombstone on ``contacts`` and the indexes that keep
the phone-book search (name / org substring, number lookup) index-backed:
``pg_trgm`` GIN indexes on ``contacts.name`` / ``contacts.org`` and a plain
btree on ``contact_numbers.e164``. Reversible, expand-only (only adds a nullable
column and indexes).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_contacts_search"
down_revision: str | None = "0027_contacts_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("contacts", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')
    op.create_index(
        "ix_contacts_name_trgm",
        "contacts",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_contacts_org_trgm",
        "contacts",
        ["org"],
        postgresql_using="gin",
        postgresql_ops={"org": "gin_trgm_ops"},
    )
    op.create_index(op.f("ix_contact_numbers_e164"), "contact_numbers", ["e164"])


def downgrade() -> None:
    op.drop_index(op.f("ix_contact_numbers_e164"), table_name="contact_numbers")
    op.drop_index("ix_contacts_org_trgm", table_name="contacts")
    op.drop_index("ix_contacts_name_trgm", table_name="contacts")
    op.drop_column("contacts", "deleted_at")
    # pg_trgm is left installed — cheap, and other tables may adopt it.
