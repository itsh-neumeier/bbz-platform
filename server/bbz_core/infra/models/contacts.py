"""Phone book: contacts, their numbers, and per-contact call priority (E14-01).

MASTER_PROMPT §14, §13.9 (Prioritäten niedrig/mittel/hoch). Vendor-neutral.

Notes:

* ``contacts.name`` / ``org`` / ``notes`` and every ``contact_numbers.e164`` are
  personally identifiable — scope (``bbz_id``) and retention apply
  (``docs/domain/retention-policy.md``);
* numbers are stored **normalized E.164** (``+`` and digits only, 2..15 digits) —
  a CHECK enforces the shape; turning a dialled or national number into E.164
  happens in the matching service (E14-04);
* ``contact_priorities`` is current-state, one row per contact (``contact_id`` is
  the PK) — the history of changes lives in ``domain_events``
  (``CONTACT_PRIORITY_CHANGED``, E14-03). No row = not prioritized.
"""

from __future__ import annotations

import datetime as _dt
import enum
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base, TimestampMixin, uuid_pk

#: E.164: a leading ``+`` then a non-zero digit then 1..14 more digits.
E164_CHECK = r"e164 ~ '^\+[1-9][0-9]{1,14}$'"


class ContactPriorityLevel(enum.StrEnum):
    #: §13.9 niedrig / mittel / hoch
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Contact(Base, TimestampMixin):
    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200))
    org: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    quick_dial: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    #: the BBZ this contact belongs to. No BBZ entity yet — plain UUID, like
    #: ``events.bbz_id`` (E02-07); scope filtering is wired in E23.
    bbz_id: Mapped[uuid.UUID | None] = mapped_column(index=True)


class ContactNumber(Base, TimestampMixin):
    __tablename__ = "contact_numbers"
    __table_args__ = (
        CheckConstraint(E164_CHECK, name="e164_normalized"),
        UniqueConstraint("contact_id", "e164", name="uq_contact_numbers_contact_id_e164"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    contact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"), index=True
    )
    e164: Mapped[str] = mapped_column(String(16))
    label: Mapped[str | None] = mapped_column(String(80))
    is_primary: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class ContactPriority(Base):
    """One row per contact (``contact_id`` is the PK) — last write wins (E14-03)."""

    __tablename__ = "contact_priorities"
    __table_args__ = (
        CheckConstraint(
            "priority IN (" + ", ".join(f"'{p.value}'" for p in ContactPriorityLevel) + ")",
            name="priority_level",
        ),
    )

    contact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"), primary_key=True
    )
    priority: Mapped[str] = mapped_column(String(16))
    set_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    set_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))
