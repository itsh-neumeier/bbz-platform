"""Technical endpoints — configured technical signal sources (roadmap E15-01).

MASTER_PROMPT §29 / ``.ai/TECHNICAL_TRIGGERS.md``: **technical systems are not
normal phone-book contacts**. A door station, a Brandmeldeanlage (BMA), a
panic button, a video alarm or an alarm dialer is a ``technical_endpoint`` with
its own trigger behaviour (default priority, popup / escalation profile,
workflow-selection policy), kept strictly separate from ``contacts``.

``technical_endpoint_numbers`` holds the calling / called number patterns (and
CTI route point) for telephony-based endpoints; camera mappings are Epic 16,
door profiles are Epic 17.
"""

from __future__ import annotations

import enum
import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base, TimestampMixin, uuid_pk

#: event priorities a technical signal can map to (see ``EventPriority``)
_PRIORITIES = ("critical", "high", "medium", "low")


class TechnicalEndpointType(enum.StrEnum):
    DOOR_STATION = "door_station"
    BMA = "bma"
    PANIC_BUTTON = "panic_button"
    VIDEO_ALARM = "video_alarm"
    ALARM_DIALER = "alarm_dialer"
    CUSTOM = "custom"


class TechnicalEndpoint(Base, TimestampMixin):
    __tablename__ = "technical_endpoints"
    __table_args__ = (
        CheckConstraint(
            "type IN (" + ", ".join(f"'{t.value}'" for t in TechnicalEndpointType) + ")",
            name="type",
        ),
        CheckConstraint(
            "default_priority IS NULL OR default_priority IN ("
            + ", ".join(f"'{p}'" for p in _PRIORITIES)
            + ")",
            name="default_priority",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200))
    #: site / station this endpoint belongs to (free text — no sites table yet)
    site: Mapped[str | None] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(32))
    #: the integration id this endpoint is served by (``telephony_cucm``,
    #: ``coda_video`` …). Free text — there is no integrations table.
    provider_id: Mapped[str | None] = mapped_column(String(64), index=True)
    #: provider-native identifiers that resolve to this endpoint (device names,
    #: alarm source ids). Matched by the trigger engine (E15-05).
    external_source_ids: Mapped[list[str]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    #: event priority a signal from this endpoint defaults to
    default_priority: Mapped[str | None] = mapped_column(String(16))
    #: client-popup profile id (E15-14)
    popup_profile: Mapped[str | None] = mapped_column(String(64))
    #: escalation profile id
    escalation_profile: Mapped[str | None] = mapped_column(String(64))
    #: how a trigger picks the workflow template + version (E15-13). Free-form
    #: config object, interpreted by the trigger engine.
    workflow_selection_policy: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    #: bumped whenever the endpoint's trigger config changes (E15-10)
    active_config_version: Mapped[int] = mapped_column(Integer, server_default=text("1"))

    # --- door station (Siedle, E17-01). INTEGRATIONS_SIEDLE.md §"Technical
    # endpoint model". The DTMF *code* is never stored here — only the id of a
    # ``door_action_profiles`` row (E17-02) that holds it encrypted (§30). ---
    #: reference to the encrypted door-open DTMF profile (no code, ever). The FK
    #: to ``door_action_profiles`` is wired in migration 0036 (E17-02).
    dtmf_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("door_action_profiles.id", ondelete="SET NULL")
    )
    #: operator popup text, e.g. "Klingel XYZ"
    popup_text: Mapped[str | None] = mapped_column(String(200))
    #: seconds to wait for the open side effect before giving up
    door_open_timeout_seconds: Mapped[int | None] = mapped_column(Integer)


class TechnicalEndpointNumber(Base, TimestampMixin):
    """Telephony addressing for an endpoint: ANI / DNIS patterns + route point."""

    __tablename__ = "technical_endpoint_numbers"

    id: Mapped[uuid.UUID] = uuid_pk()
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("technical_endpoints.id", ondelete="CASCADE"), index=True
    )
    #: calling-number (ANI) pattern this endpoint is recognised by
    calling_pattern: Mapped[str | None] = mapped_column(String(64))
    #: called-number (DNIS) pattern
    called_pattern: Mapped[str | None] = mapped_column(String(64))
    #: CTI route point the call arrives on
    cti_route_point: Mapped[str | None] = mapped_column(String(64))
