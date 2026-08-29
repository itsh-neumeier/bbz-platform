"""events.description: optional free-text body

Revision ID: 0012_events_description
Revises: 0011_commands
Create Date: 2026-08-29

Roadmap E03-08 (#48). Nullable, no default — pure expand step, reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_events_description"
down_revision: str | None = "0011_commands"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("events", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "description")
