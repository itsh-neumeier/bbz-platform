"""Operator-facing per-event camera view (roadmap E16-12 / #357, ADR-0032).

Camera opening is a decoupled side effect (ADR-0006, E16-08): the trigger engine
enqueues an ``open_camera`` / ``open_camera_group`` outbox row and the dispatcher
delivers it to the ``video.*`` provider. The outcome is recorded on the
triggering event as a ``CAMERA_OPENED`` (success) or ``CAMERA_ACTION_FAILED``
(terminal failure) domain event.

- ``GET /events/{event_id}/cameras`` — the cameras that domain-event trail
  mentions, enriched with a live ``video.resolve_camera`` status. Degrades to
  ``provider_available: false`` (the "Video derzeit nicht verfügbar" case)
  rather than failing when the integration is down.
- ``POST /events/{event_id}/cameras/{camera_ref}/focus`` — (re)open one of those
  cameras on the requesting operator's workplace. Enqueues one outbox row (the
  E16-08 handler), idempotent on the command id, audited
  ``CAMERA_FOCUS_REQUESTED``. A delivery failure surfaces as
  ``CAMERA_ACTION_FAILED`` on the event and never blocks the operator.

Both are gated by ``integrations.view`` (as E16-12 specifies).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.api.errors import NotFoundError, ValidationError
from bbz_core.api.idempotency import CommandEnvelope, command_envelope
from bbz_core.audit import AuditAction, AuditService
from bbz_core.infra.models.domain_events import DomainEvent
from bbz_core.infra.models.events import Event
from bbz_core.infra.outbox import enqueue
from bbz_core.integrations_host.cameras import resolve_cameras

router = APIRouter(prefix="/events", tags=["events"])

_CAMERA_EVENT_TYPES = ("CAMERA_OPENED", "CAMERA_ACTION_FAILED")


class CameraOut(BaseModel):
    #: the normalized camera handle from the trigger mapping / domain-event trail
    ref: str
    name: str
    site: str | None = None
    #: live status from ``video.resolve_camera``; ``null`` when it could not be
    #: resolved (provider down, camera unknown, timeout)
    online: bool | None = None
    group_ids: list[str] = []
    #: "opened" | "failed" — the newest camera action on this event that named it
    last_action_state: str


class EventCamerasOut(BaseModel):
    #: false when there is no active ``video.*`` integration — the panel shows
    #: "Video derzeit nicht verfügbar" and still lists the known refs
    provider_available: bool
    cameras: list[CameraOut]


async def _require_event(session: AsyncSession, event_id: uuid.UUID) -> None:
    if await session.get(Event, event_id) is None:
        raise NotFoundError("event not found")


async def _camera_trail(session: AsyncSession, event_id: uuid.UUID) -> dict[str, str]:
    """ref -> last_action_state ("opened" | "failed"), newest action wins."""
    rows = (
        await session.execute(
            select(DomainEvent.event_type, DomainEvent.payload)
            .where(
                DomainEvent.aggregate_type == "event",
                DomainEvent.aggregate_id == str(event_id),
                DomainEvent.event_type.in_(_CAMERA_EVENT_TYPES),
            )
            .order_by(DomainEvent.event_seq)
        )
    ).all()
    state: dict[str, str] = {}
    for event_type, payload in rows:
        mark = "opened" if event_type == "CAMERA_OPENED" else "failed"
        for ref in payload.get("camera_refs") or []:
            state[str(ref)] = mark
    return state


@router.get("/{event_id}/cameras", response_model=EventCamerasOut)
async def list_event_cameras(
    event_id: uuid.UUID,
    _: AuthContext = Depends(require("integrations.view")),
    session: AsyncSession = Depends(db_session),
) -> EventCamerasOut:
    await _require_event(session, event_id)
    trail = await _camera_trail(session, event_id)
    if not trail:
        return EventCamerasOut(provider_available=True, cameras=[])

    resolution = await resolve_cameras(sorted(trail))
    return EventCamerasOut(
        provider_available=resolution.provider_available,
        cameras=[
            CameraOut(
                ref=c.ref,
                name=c.name,
                site=c.site,
                online=c.online,
                group_ids=list(c.group_ids),
                last_action_state=trail[c.ref],
            )
            for c in resolution.cameras
        ],
    )


class FocusCameraOut(BaseModel):
    enqueued: bool
    camera_ref: str
    workplace_id: str


@router.post("/{event_id}/cameras/{camera_ref}/focus", response_model=FocusCameraOut)
async def focus_event_camera(
    event_id: uuid.UUID,
    camera_ref: str,
    ctx: AuthContext = Depends(require("integrations.view")),
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> FocusCameraOut:
    if not env.workplace_id:
        raise ValidationError("X-Workplace-Id header is required to focus a camera")
    await _require_event(session, event_id)

    trail = await _camera_trail(session, event_id)
    if camera_ref not in trail:
        raise NotFoundError("camera is not associated with this event")

    dedupe = f"focus:{event_id}:{camera_ref}:{env.command_id}"
    await session.rollback()  # close the auth read tx before the write tx
    async with session.begin():
        enqueued = await enqueue(
            session,
            dedupe_key=dedupe,
            action_type="open_camera",
            payload={
                "camera_ref": camera_ref,
                "workplace_id": env.workplace_id,
                "command_id": dedupe,
                "event_id": str(event_id),
            },
        )
        # idempotent: a replayed X-Command-Id re-hits the outbox dedupe_key and
        # enqueues nothing — audit exactly the first, real request.
        if enqueued:
            await AuditService(session).write(
                AuditAction.CAMERA_FOCUS_REQUESTED,
                actor_user_id=ctx.user_id,
                target_type="event",
                target_id=str(event_id),
                after={"camera_ref": camera_ref, "workplace_id": env.workplace_id},
            )
    return FocusCameraOut(enqueued=enqueued, camera_ref=camera_ref, workplace_id=env.workplace_id)
