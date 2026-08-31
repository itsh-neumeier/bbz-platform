"""calls.caller_contact_id + calls.caller_priority

Revision ID: 0029_call_caller_resolution
Revises: 0028_contacts_search
Create Date: 2026-08-31

Roadmap E11-08. Caller resolution snapshot on the call row: the resolved
contact and its priority at the time of the call. NULL contact = the number did
not resolve to a single contact ("unknown"). Reversible, expand-only.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_call_caller_resolution"
down_revision: str | None = "0028_contacts_search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("calls", sa.Column("caller_contact_id", sa.Uuid(), nullable=True))
    op.add_column("calls", sa.Column("caller_priority", sa.String(length=16), nullable=True))
    op.create_foreign_key(
        op.f("fk_calls_caller_contact_id_contacts"),
        "calls",
        "contacts",
        ["caller_contact_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_calls_caller_contact_id"), "calls", ["caller_contact_id"])
    op.create_check_constraint(
        "call_caller_priority",
        "calls",
        "caller_priority IS NULL OR caller_priority IN ('low', 'medium', 'high')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_calls_call_caller_priority", "calls", type_="check")
    op.drop_index(op.f("ix_calls_caller_contact_id"), table_name="calls")
    op.drop_constraint(op.f("fk_calls_caller_contact_id_contacts"), "calls", type_="foreignkey")
    op.drop_column("calls", "caller_priority")
    op.drop_column("calls", "caller_contact_id")
