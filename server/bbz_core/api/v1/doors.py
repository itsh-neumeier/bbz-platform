"""Door-open API (roadmap E17-05, ADR-0025).

``POST /api/v1/doors/{endpoint_id}/open`` runs the Siedle door-open sequence for
the operator who pressed "Öffnen" on the doorbell popup. Requires ``door.open``.
Idempotent on ``X-Command-Id`` — the same key replays the stored result and never
opens the door a second time. The request body never carries a DTMF code (the
model is ``extra="forbid"``); the sequence lives encrypted in
``door_action_profiles`` and is resolved server-side, transiently.

The outcome is always reported (``opened`` / ``caller_gone`` / ``media_timeout``
/ …) with HTTP 200 for a completed attempt; 4xx only for a bad request.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.api.errors import (
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)
from bbz_core.api.idempotency import CommandEnvelope, command_envelope
from bbz_core.infra.door_secrets import DoorSecretsNotConfigured
from bbz_core.infra.idempotency import CommandConflictError, CommandInProgressError
from bbz_core.infra.repositories.door_open import DoorOpenError, DoorOpenService

router = APIRouter(prefix="/doors", tags=["doors"])


class DoorOpenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    #: the provider call id (``source_call_id``) of the doorbell call — from the
    #: ``DOORBELL_RINGING`` signal the popup was raised on
    call_id: str = Field(min_length=1, max_length=128)


class DoorOpenOut(BaseModel):
    command_id: uuid.UUID
    endpoint_id: uuid.UUID
    #: ``opened`` | ``caller_gone`` | ``media_timeout`` | ``no_dtmf_capability`` |
    #: ``no_profile`` | ``provider_error`` | ``telephony_unavailable``
    outcome: str
    opened: bool
    detail: str


@contextlib.contextmanager
def _translate() -> Iterator[None]:
    try:
        yield
    except DoorSecretsNotConfigured as exc:
        raise ServiceUnavailableError("door DTMF encryption is not configured") from exc
    except CommandConflictError as exc:
        raise ConflictError("command id reused with a different body") from exc
    except CommandInProgressError as exc:
        raise ConflictError("an identical door-open command is still being processed") from exc
    except DoorOpenError as exc:
        if exc.code == "not_found":
            raise NotFoundError(str(exc)) from exc
        raise ValidationError(str(exc)) from exc


@router.post("/{endpoint_id}/open", response_model=DoorOpenOut)
async def open_door(
    endpoint_id: uuid.UUID,
    body: DoorOpenIn,
    ctx: AuthContext = Depends(require("door.open")),
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> DoorOpenOut:
    with _translate():
        result = await DoorOpenService(session).open(
            endpoint_id=endpoint_id,
            call_id=body.call_id,
            command_id=env.command_id,
            actor_id=ctx.user_id,
        )
    return DoorOpenOut(
        command_id=result.command_id,
        endpoint_id=result.endpoint_id,
        outcome=result.outcome,
        opened=result.opened,
        detail=result.detail,
    )
