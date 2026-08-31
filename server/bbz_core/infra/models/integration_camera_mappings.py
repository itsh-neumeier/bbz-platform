"""Integration camera mappings — endpoint / alarm source -> camera(s) (E16-05).

MASTER_PROMPT §34 / ``.ai/INTEGRATIONS_CODA_VIDEO.md`` "Admin mapping": a
configured technical endpoint **or** an external alarm/source id is mapped to
one or more cameras, in order. The camera reference is a **normalized handle**
(E16-02) — never a vendor object id. The admin API on top is E16-06; the runtime
that opens the cameras is E16-07 / E16-08.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base, TimestampMixin, uuid_pk


class IntegrationCameraMapping(Base, TimestampMixin):
    """One camera bound to a technical endpoint or to an external alarm source.

    At least one of ``endpoint_id`` / ``alarm_source_external_id`` anchors the
    mapping (CHECK ``anchor``). ``ordinal`` orders the cameras when a trigger
    opens several. ``provider_instance_id`` scopes the camera ref to a specific
    integration instance when more than one is configured.
    """

    __tablename__ = "integration_camera_mappings"
    __table_args__ = (
        CheckConstraint(
            "endpoint_id IS NOT NULL OR alarm_source_external_id IS NOT NULL",
            name="anchor",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    #: anchor A — a configured technical endpoint (mapping cascades with it)
    endpoint_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("technical_endpoints.id", ondelete="CASCADE"), index=True
    )
    #: anchor B — an external alarm/source id (e.g. Coda ``source_external_id``)
    alarm_source_external_id: Mapped[str | None] = mapped_column(String(200), index=True)
    #: normalized camera handle — no vendor object id crosses this boundary
    camera_external_ref: Mapped[str] = mapped_column(String(200))
    #: open order when a trigger opens several cameras
    ordinal: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    #: which integration instance this camera ref belongs to
    provider_instance_id: Mapped[str | None] = mapped_column(String(64))
