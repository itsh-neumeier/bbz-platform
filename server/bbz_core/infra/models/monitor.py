"""Monitor / KVM routing schema (roadmap E19-01, MASTER_PROMPT §9).

Monitor routing is its own integration domain: a small fixed catalog of logical
**inputs** (BBZ-OS, the four BKU workplaces, the two Cayuga video channels) and
**outputs** (six workplace monitors in a 3x2 grid + the large display), the
**current route** per output (exactly one input feeds each output), and named
**layout profiles** a user or a workplace can save and re-apply.

Schema only. The fixed input/output catalog and the standard layout (which input
feeds which output by default) are the E19-02 seed; the "lower-left output is
always BBZ-OS" invariant is enforced in the routing service (E19-03); the routing
API + ``MONITOR_ROUTE_CHANGED`` audit is E19-04; profiles CRUD is E19-05.

No ``workplaces`` table exists yet — ``workplace_id`` is a plain indexed UUID
(same convention as ``events.workplace_id`` / ``bku_agents.workplace_id``).
"""

from __future__ import annotations

import datetime as _dt
import enum
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, SmallInteger, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base, TimestampMixin, uuid_pk


class MonitorProfileScope(enum.StrEnum):
    USER = "user"
    WORKPLACE = "workplace"


_SCOPES = ", ".join(f"'{s.value}'" for s in MonitorProfileScope)

#: 3 columns x 2 rows — the workplace-monitor grid (MASTER_PROMPT §9)
GRID_COLS = 3
GRID_ROWS = 2


class MonitorInput(Base, TimestampMixin):
    """A logical video source that can be routed to an output."""

    __tablename__ = "monitor_inputs"

    id: Mapped[uuid.UUID] = uuid_pk()
    #: stable identifier, e.g. ``bbz-os`` / ``bku1`` / ``cayuga1``
    key: Mapped[str] = mapped_column(String(32), unique=True)
    label: Mapped[str] = mapped_column(String(80))
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")


class MonitorOutput(Base, TimestampMixin):
    """A physical monitor. The six workplace monitors each sit at a (row, col) in
    the 3x2 grid; the large display (``is_large_display``) has no grid slot."""

    __tablename__ = "monitor_outputs"
    __table_args__ = (
        CheckConstraint(
            "(is_large_display AND grid_row IS NULL AND grid_col IS NULL) OR "
            "(NOT is_large_display AND grid_row BETWEEN 0 AND 1 AND grid_col BETWEEN 0 AND 2)",
            name="monitor_outputs_grid",
        ),
        UniqueConstraint("grid_row", "grid_col", name="uq_monitor_outputs_grid_row_col"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    key: Mapped[str] = mapped_column(String(32), unique=True)
    label: Mapped[str] = mapped_column(String(80))
    #: 0 = top row, 1 = bottom row; ``NULL`` for the large display
    grid_row: Mapped[int | None] = mapped_column(SmallInteger)
    #: 0 = left column .. 2 = right column; ``NULL`` for the large display
    grid_col: Mapped[int | None] = mapped_column(SmallInteger)
    is_large_display: Mapped[bool] = mapped_column(server_default="false")
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")


class MonitorProfile(Base, TimestampMixin):
    """A named, re-applicable layout (``layout`` maps output key -> input key).
    ``user`` scope: private to ``owner_user_id``. ``workplace`` scope: shared for
    ``workplace_id``. Exactly one of the two is set (CHECK)."""

    __tablename__ = "monitor_profiles"
    __table_args__ = (
        CheckConstraint(f"scope IN ({_SCOPES})", name="monitor_profiles_scope"),
        CheckConstraint(
            "(scope = 'user' AND owner_user_id IS NOT NULL AND workplace_id IS NULL) OR "
            "(scope = 'workplace' AND workplace_id IS NOT NULL AND owner_user_id IS NULL)",
            name="monitor_profiles_scope_owner",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(120))
    scope: Mapped[str] = mapped_column(String(16))
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    #: plain UUID — no ``workplaces`` entity yet (cf. ``events.workplace_id``)
    workplace_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    #: ``{output_key: input_key}`` — validated against the catalog by the service
    layout: Mapped[dict[str, str]] = mapped_column(JSONB)


class MonitorRoute(Base, TimestampMixin):
    """The current input feeding one output — exactly one row per output
    (``output_id`` is the PK), upserted whenever a route changes. The change
    history lives in the audit log (``MONITOR_ROUTE_CHANGED``, E19-04)."""

    __tablename__ = "monitor_routes"

    output_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("monitor_outputs.id", ondelete="CASCADE"), primary_key=True
    )
    input_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("monitor_inputs.id", ondelete="RESTRICT"), index=True
    )
    #: who set it (``NULL`` after the actor is deleted, or for a system route)
    set_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    set_at: Mapped[_dt.datetime] = mapped_column()
    #: the profile this route was applied from, if any (E19-05)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("monitor_profiles.id", ondelete="SET NULL")
    )
