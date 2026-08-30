"""events / event history: BEFORE DELETE guard (retention policy)

Revision ID: 0023_events_delete_guard
Revises: 0022_event_note_versioning
Create Date: 2026-08-30

Roadmap E20-07. MASTER_PROMPT §26.7 ("keine archivierten Ereignisse hart
löschen") / §17. ``audit_events`` and ``domain_events`` already reject UPDATE and
DELETE (0016). This adds a **DELETE-only** guard to the event record —
``events`` and its append-only history (``event_status_history``,
``event_notes``) — so a stray ``DELETE`` (any client) raises instead of losing
history. UPDATE stays allowed (status, version, note supersede). DROP TABLE (DDL)
is unaffected. Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0023_events_delete_guard"
down_revision: str | None = "0022_event_note_versioning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("events", "event_status_history", "event_notes")
_FN = "bbz_forbid_row_delete"


def upgrade() -> None:
    op.execute(
        f"CREATE OR REPLACE FUNCTION {_FN}() RETURNS trigger "
        "LANGUAGE plpgsql AS $$ BEGIN "
        "RAISE EXCEPTION 'retention policy: DELETE is not allowed on %', TG_TABLE_NAME; "
        "END; $$"
    )
    for table in _TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION {_FN}()"
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_delete ON {table}")
    op.execute(f"DROP FUNCTION IF EXISTS {_FN}()")
