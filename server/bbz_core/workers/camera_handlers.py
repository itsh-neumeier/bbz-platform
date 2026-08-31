"""Outbox dispatch handlers for the camera trigger actions (roadmap E16-08).

``open_camera`` / ``open_camera_group`` enqueue an ``external_action_outbox`` row
(E15-07). This is where the dispatcher delivers it: each handler reaches the
active ``video.*`` provider (E16-02). A provider error propagates so the
dispatcher retries with backoff and, after the attempt cap, records the row
``failed`` (``EXTERNAL_ACTION_FAILED``) and notes it on the triggering event —
camera opening is a **decoupled** side effect, so none of this ever rolls back
the event or its operator popup (MASTER_PROMPT §31/§36, ADR-0006).

Idempotent: the handler passes the row's ``command_id`` (the stable trigger
execution key) straight to the provider, and the outbox ``dedupe_key`` UNIQUE
already blocks a second enqueue — so a camera never opens twice.
"""

from __future__ import annotations

from typing import Any

from bbz_core.integrations_host.providers import active_video_provider

#: display target when a rule action carries no workplace_id — the alarm-context
#: wall display rather than a specific operator seat.
_ALARM_CONTEXT_TARGET = "alarm-context"

#: action types this module handles (also the outbox dispatcher registration set)
CAMERA_ACTION_TYPES: frozenset[str] = frozenset({"open_camera", "open_camera_group"})


def _target(payload: dict[str, Any]) -> str:
    return str(payload.get("workplace_id") or _ALARM_CONTEXT_TARGET)


async def open_camera(payload: dict[str, Any]) -> dict[str, Any]:
    provider = await active_video_provider()
    view = await provider.open_camera(
        camera_id=str(payload["camera_ref"]),
        workplace_id=_target(payload),
        command_id=str(payload["command_id"]),
    )
    return {"camera_id": view.camera_id, "action": view.action}


async def open_camera_group(payload: dict[str, Any]) -> dict[str, Any]:
    provider = await active_video_provider()
    view = await provider.open_camera_group(
        camera_ids=[str(r) for r in payload["camera_refs"]],
        workplace_id=_target(payload),
        command_id=str(payload["command_id"]),
    )
    return {"camera_ids": list(view.camera_ids), "workplace_id": view.workplace_id}


CAMERA_HANDLERS: dict[str, Any] = {
    "open_camera": open_camera,
    "open_camera_group": open_camera_group,
}
