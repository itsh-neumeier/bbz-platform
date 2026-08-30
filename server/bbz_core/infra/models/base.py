"""Declarative base and shared column helpers for all ORM models.

Every persistent model in ``bbz_core.infra.models`` inherits from :class:`Base`.
The metadata carries an explicit constraint-naming convention so Alembic
migrations get stable, predictable names (required for reversible
expand/migrate/contract migrations, MASTER_PROMPT §21).

All ``datetime`` columns are ``timestamptz`` (ADR-0017: store/transmit UTC).

Models live in ``infra`` only. ``bbz_core.domain`` must never import them
(enforced by import-linter).
"""

from __future__ import annotations

import datetime as _dt
import uuid
from typing import Any

from sqlalchemy import DDL, DateTime, MetaData, event, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {  # noqa: RUF012 - SQLAlchemy reads this exact attribute
        _dt.datetime: DateTime(timezone=True),
    }


def uuid_pk() -> Mapped[uuid.UUID]:
    """Primary key column: server-generated UUID (pgcrypto ``gen_random_uuid``)."""
    return mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))


class TimestampMixin:
    """``created_at`` / ``updated_at`` (both ``timestamptz``, server-defaulted)."""

    created_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[_dt.datetime] = mapped_column(
        server_default=text("now()"), onupdate=text("now()")
    )


#: Append-only enforcement (ADR-0020). The migration 0016_audit_immutability
#: creates the same objects for already-provisioned databases; this hook makes
#: ``create_all`` (tests / fresh dev DB) consistent with it.
APPEND_ONLY_FN = "bbz_forbid_row_mutation"

_APPEND_ONLY_FN_DDL = DDL(  # type: ignore[no-untyped-call]
    f"CREATE OR REPLACE FUNCTION {APPEND_ONLY_FN}() RETURNS trigger "
    "LANGUAGE plpgsql AS $$ BEGIN "
    "RAISE EXCEPTION 'append-only table: UPDATE and DELETE are not allowed'; "
    "END; $$"
)


def make_append_only(table: Any) -> None:
    """Attach a ``BEFORE UPDATE OR DELETE`` trigger that blocks all row mutation."""
    trigger = f"{table.name}_append_only"
    create_trigger = DDL(  # type: ignore[no-untyped-call]
        f"CREATE TRIGGER {trigger} BEFORE UPDATE OR DELETE ON {table.name} "
        f"FOR EACH ROW EXECUTE FUNCTION {APPEND_ONLY_FN}()"
    )
    event.listen(table, "after_create", _APPEND_ONLY_FN_DDL.execute_if(dialect="postgresql"))
    event.listen(table, "after_create", create_trigger.execute_if(dialect="postgresql"))
