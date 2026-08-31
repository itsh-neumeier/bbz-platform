"""Door-open command state machine (roadmap E17-05, ADR-0025).

One row per ``door.open`` request (keyed by the client ``X-Command-Id``). It
tracks the open flow — answer the doorbell call if needed, wait for media, send
the DTMF sequence exactly once, wait the post-DTMF delay, hang up — so a crash or
retry mid-flow never opens the door twice and an operator can see the outcome.

The DTMF **sequence is never here** (ADR-0025 / §30): the row references the
``door_action_profiles`` id, and the code is resolved transiently on the path.
"""

from __future__ import annotations

import datetime as _dt
import enum
import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base, TimestampMixin, uuid_pk


class DoorOpenState(enum.StrEnum):
    REQUESTED = "requested"
    ANSWERING = "answering"
    CONNECTING = "connecting"
    DTMF_SENT = "dtmf_sent"
    COMPLETING = "completing"
    # terminal
    DONE = "done"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class DoorOpenOutcome(enum.StrEnum):
    OPENED = "opened"
    CALLER_GONE = "caller_gone"
    MEDIA_TIMEOUT = "media_timeout"
    NO_DTMF_CAPABILITY = "no_dtmf_capability"
    NO_PROFILE = "no_profile"
    PROVIDER_ERROR = "provider_error"
    TELEPHONY_UNAVAILABLE = "telephony_unavailable"
    #: the doorbell call still had to be answered but the operator lacks door.answer
    ANSWER_FORBIDDEN = "answer_forbidden"


class DoorOpenCommand(Base, TimestampMixin):
    __tablename__ = "door_open_commands"

    id: Mapped[uuid.UUID] = uuid_pk()
    #: the client-generated idempotency key (``X-Command-Id``) — one open per key
    command_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("technical_endpoints.id", ondelete="CASCADE"), index=True
    )
    #: the door-open profile in effect (id only — never the code). SET NULL so a
    #: profile can still be deleted; the audit trail keeps the reference.
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("door_action_profiles.id", ondelete="SET NULL")
    )
    #: the provider call id (``source_call_id``) the DTMF is sent on
    call_id: Mapped[str | None] = mapped_column(String(128))
    state: Mapped[str] = mapped_column(String(16), default=DoorOpenState.REQUESTED.value)
    #: set once the flow reaches a terminal state
    outcome: Mapped[str | None] = mapped_column(String(32))
    detail: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    dtmf_sent_at: Mapped[_dt.datetime | None] = mapped_column()
    completed_at: Mapped[_dt.datetime | None] = mapped_column()
