"""Telephony core objects: lines, calls, participants, call documentation (E11-01).

MASTER_PROMPT §14, §8.4, §13.8/§13.10. Vendor-neutral — no Cisco/JTAPI types
here; a provider translates its events into the normalised shape
(``packages/event-schemas/telephony_event.v1.json``) and the call aggregate
(E11-04) drives the state.

Notes:

* every call has a BBZ-owned ``bbz_call_id`` that is **independent** of the
  provider's ``source_call_id`` (which may be null early, and is not globally
  unique);
* ``call_participants.number`` and ``call_documentation.free_text`` are
  personally identifiable — scope/retention applies (see
  ``docs/domain/retention-policy.md``);
* ``category`` is a closed CHECK set (§13.10), nullable until the operator sets
  it (the hangup guard, E11-10, keys off ``mandatory_done``).
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


class LineState(enum.StrEnum):
    IN_SERVICE = "in_service"
    OUT_OF_SERVICE = "out_of_service"
    UNKNOWN = "unknown"


class CallDirection(enum.StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class CallState(enum.StrEnum):
    OFFERED = "offered"
    RINGING = "ringing"
    CONNECTED = "connected"
    HELD = "held"
    TRANSFERRING = "transferring"
    DISCONNECTED = "disconnected"
    FAILED = "failed"
    #: hung up but not yet documented — stays "open" until a category is set
    #: (the mandatory-documentation guard, E11-10)
    ENDED_PENDING_DOCUMENTATION = "ended_pending_documentation"


class ParticipantRole(enum.StrEnum):
    CALLER = "caller"
    CALLEE = "callee"
    OPERATOR = "operator"
    TRANSFER_TARGET = "transfer_target"
    CONFERENCE = "conference"


class CallCategory(enum.StrEnum):
    #: §13.10: Auskunftsersuchen / Technische Störung / Reinigungsmeldung Kunde /
    #: EVU & EVI Mitteilung / Anderes
    INFORMATION_REQUEST = "information_request"
    TECHNICAL_FAULT = "technical_fault"
    CLEANING_REPORT_CUSTOMER = "cleaning_report_customer"
    EVU_EVI_NOTICE = "evu_evi_notice"
    OTHER = "other"


def _in(column: str, values: type[enum.StrEnum], name: str) -> CheckConstraint:
    allowed = ", ".join(f"'{v.value}'" for v in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=name)


class Line(Base, TimestampMixin):
    __tablename__ = "lines"
    __table_args__ = (
        _in("state", LineState, "line_state"),
        UniqueConstraint("provider", "external_id", name="uq_lines_provider_external"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    provider: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str] = mapped_column(String(128))
    label: Mapped[str | None] = mapped_column(String(200))
    state: Mapped[str] = mapped_column(String(20), server_default=LineState.UNKNOWN.value)
    workplace_id: Mapped[uuid.UUID | None] = mapped_column(index=True)


class Call(Base, TimestampMixin):
    __tablename__ = "calls"
    __table_args__ = (
        _in("direction", CallDirection, "call_direction"),
        _in("state", CallState, "call_state"),
        CheckConstraint(
            "caller_priority IS NULL OR caller_priority IN ('low', 'medium', 'high')",
            name="call_caller_priority",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    #: BBZ-owned, stable, human-scannable id — never the provider's
    bbz_call_id: Mapped[str] = mapped_column(String(32), unique=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    #: the provider's call id — null until assigned, not globally unique
    source_call_id: Mapped[str | None] = mapped_column(String(128), index=True)
    direction: Mapped[str] = mapped_column(String(16))
    state: Mapped[str] = mapped_column(
        String(32), server_default=CallState.OFFERED.value, index=True
    )
    line_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lines.id", ondelete="SET NULL"), index=True
    )
    workplace_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    started_at: Mapped[_dt.datetime | None] = mapped_column()
    ended_at: Mapped[_dt.datetime | None] = mapped_column()
    #: caller resolution (E11-08) — snapshotted at call time. NULL contact = the
    #: number did not resolve to a single contact ("unknown").
    caller_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), index=True
    )
    caller_priority: Mapped[str | None] = mapped_column(String(16))


class CallParticipant(Base):
    __tablename__ = "call_participants"
    __table_args__ = (_in("role", ParticipantRole, "call_participant_role"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    call_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("calls.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[str | None] = mapped_column(String(64))
    display_name: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))


class CallDocumentation(Base):
    """One row per call (``call_id`` is the PK) — re-saving overwrites (E11-09)."""

    __tablename__ = "call_documentation"
    __table_args__ = (
        CheckConstraint(
            "category IS NULL OR category IN ("
            + ", ".join(f"'{c.value}'" for c in CallCategory)
            + ")",
            name="call_documentation_category",
        ),
    )

    call_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("calls.id", ondelete="CASCADE"), primary_key=True
    )
    category: Mapped[str | None] = mapped_column(String(32))
    free_text: Mapped[str | None] = mapped_column(Text)
    documented_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    documented_at: Mapped[_dt.datetime | None] = mapped_column()
    #: true once a category is set — the hangup guard (E11-10) blocks final
    #: ``CALL_ENDED`` until this is true
    mandatory_done: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    updated_at: Mapped[_dt.datetime] = mapped_column(
        server_default=text("now()"), onupdate=text("now()")
    )
