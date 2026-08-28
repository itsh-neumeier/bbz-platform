from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from bbz_integration_sdk.providers.base import Provider


@runtime_checkable
class VideoProvider(Provider, Protocol):
    """Video / camera presentation provider (ADR-0006).

    Canonical implementation target: ``coda_video`` (HxGN dC3 Video). Foundation
    phase ships only a mock. Endpoint URLs, auth schemes, camera object models
    and display-agent commands are NOT invented — implemented only from official
    Coda/HxGN documentation.
    """

    async def resolve_camera(self, *, external_id: str) -> Any: ...

    async def open_camera(self, *, camera_id: str, workplace_id: str, command_id: str) -> Any: ...

    async def open_camera_group(
        self, *, camera_ids: list[str], workplace_id: str, command_id: str
    ) -> Any: ...

    async def open_alarm_context(
        self, *, alarm_ref: str, workplace_id: str, command_id: str
    ) -> Any: ...
