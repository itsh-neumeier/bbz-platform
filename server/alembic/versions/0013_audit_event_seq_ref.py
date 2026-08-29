"""audit_events.event_seq_ref: link an audit row to its domain event

Revision ID: 0013_audit_event_seq_ref
Revises: 0012_events_description
Create Date: 2026-08-29

Roadmap E04-01 (#57). Nullable BIGINT, no FK (``domain_events`` is append-only
and may be pruned per retention independently). Pure expand, reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_audit_event_seq_ref"
down_revision: str | None = "0012_events_description"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audit_events", sa.Column("event_seq_ref", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("audit_events", "event_seq_ref")
