"""Vendor-neutral video / camera presentation provider protocol (E16-02).

Canonical implementation target: ``coda_video`` (HxGN dC3 Video). The foundation
phase ships only a mock. Endpoint URLs, auth schemes, camera object models and
display-agent commands are **not** invented here — a real adapter implements
them strictly from official Coda / HxGN dC3 documentation (E16-13).

The normalized capability surface (``.ai/INTEGRATIONS_CODA_VIDEO.md``):

* ``video.health``        — via :meth:`Provider.health`
* ``video.resolve_camera``
* ``video.open_camera``
* ``video.focus_camera``
* ``video.open_camera_group``
* ``video.open_alarm_context``

Error / timeout semantics: a failed operation raises a
:class:`bbz_integration_sdk.providers.video_types.VideoProviderError`
(``CameraNotFoundError`` when a handle does not resolve); a provider that cannot
answer within its own deadline raises ``VideoTimeoutError`` rather than blocking
the caller. Camera opening is a decoupled side effect (ADR-0006) — a raised
error never rolls back the triggering domain event.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from bbz_integration_sdk.providers.base import Provider
from bbz_integration_sdk.providers.video_types import (
    AlarmContextView,
    CameraGroupView,
    CameraView,
    ResolvedCamera,
)

#: the methods a full VideoProvider implements (used by conformance checks)
VIDEO_METHODS: tuple[str, ...] = (
    "resolve_camera",
    "open_camera",
    "focus_camera",
    "open_camera_group",
    "open_alarm_context",
)


@runtime_checkable
class VideoProvider(Provider, Protocol):
    async def resolve_camera(self, *, external_id: str) -> ResolvedCamera:
        """Resolve an admin-mapped external camera id to a normalized handle.

        Raises ``CameraNotFoundError`` if nothing resolves.
        """
        ...

    async def open_camera(
        self, *, camera_id: str, workplace_id: str, command_id: str
    ) -> CameraView:
        """Open a live camera view on ``workplace_id``. Idempotent on ``command_id``."""
        ...

    async def focus_camera(
        self, *, camera_id: str, workplace_id: str, command_id: str, preset: str | None = None
    ) -> CameraView:
        """Bring an already-open camera to the foreground (optionally to a named
        PTZ/preset position). Idempotent on ``command_id``."""
        ...

    async def open_camera_group(
        self, *, camera_ids: list[str], workplace_id: str, command_id: str
    ) -> CameraGroupView:
        """Open a set of cameras together (e.g. an alarm's associated cameras)."""
        ...

    async def open_alarm_context(
        self, *, alarm_ref: str, workplace_id: str, command_id: str
    ) -> AlarmContextView:
        """Open the provider-defined camera context for an alarm reference."""
        ...
