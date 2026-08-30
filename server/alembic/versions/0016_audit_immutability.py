"""audit_events / domain_events: append-only trigger (ADR-0020)

Revision ID: 0016_audit_immutability
Revises: 0015_provider_event_inbox
Create Date: 2026-08-30

Roadmap E04-10 (#66). A BEFORE UPDATE OR DELETE trigger blocks all row mutation
on the two append-only tables, from any client — not just the ORM guard from
E04-01. DROP TABLE (DDL) is unaffected. Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0016_audit_immutability"
down_revision: str | None = "0015_provider_event_inbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("audit_events", "domain_events")
_FN = "bbz_forbid_row_mutation"


def upgrade() -> None:
    op.execute(
        f"CREATE OR REPLACE FUNCTION {_FN}() RETURNS trigger "
        "LANGUAGE plpgsql AS $$ BEGIN "
        "RAISE EXCEPTION 'append-only table: UPDATE and DELETE are not allowed'; "
        "END; $$"
    )
    for table in _TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION {_FN}()"
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    op.execute(f"DROP FUNCTION IF EXISTS {_FN}()")
