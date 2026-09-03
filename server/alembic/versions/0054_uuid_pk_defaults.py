"""uuid_pk_defaults

Revision ID: 0054_uuid_pk_defaults
Revises: 0053_audit_hash_chain
Create Date: 2026-09-03

Several early migrations (0024, 0025, 0026, 0027, 0030, 0031, 0032, 0033) created
their ``id uuid`` primary keys without the ``gen_random_uuid()`` server default
that ``models.base.uuid_pk()`` declares. ``Base.metadata.create_all`` (tests /
dev) applies the default, so the gap only surfaces on a migration-provisioned
database: ``INSERT`` without an explicit id -> ``NotNullViolationError`` on
``id``. This breaks contact creation (E14-02), call ingestion (E11-04), the
trigger engine (E15-09), BKU enrolment (E10-03) and the client-popup writer
(E15-06) in a real deployment.

This backfills ``ALTER COLUMN id SET DEFAULT gen_random_uuid()`` for every
affected table. ``pgcrypto`` is already present (0001). Additive, reversible.

expand-contract: safe
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0054_uuid_pk_defaults"
down_revision: str | None = "0053_audit_hash_chain"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# tables whose `id uuid` PK was created without a server default
_TABLES = (
    "application_catalog_scopes",
    "bku_agent_enrollments",
    "call_participants",
    "calls",
    "client_popup_events",
    "contact_numbers",
    "contacts",
    "lines",
    "technical_endpoint_numbers",
    "technical_endpoints",
    "trigger_executions",
    "trigger_rule_versions",
    "trigger_rules",
    "unmapped_signals",
)


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f'ALTER TABLE "{table}" ALTER COLUMN id SET DEFAULT gen_random_uuid()')


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f'ALTER TABLE "{table}" ALTER COLUMN id DROP DEFAULT')
