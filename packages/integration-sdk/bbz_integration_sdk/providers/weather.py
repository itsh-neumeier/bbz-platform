from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from bbz_integration_sdk.providers.base import Provider


@runtime_checkable
class WeatherProvider(Provider, Protocol):
    """Weather provider (MASTER_PROMPT §10).

    Target implementation: ``dwd`` using DWD's public, documented open-data
    services (Phase 7). Concrete endpoints are chosen in ADR during Phase 7 — not
    invented here.
    """

    async def get_warnings(self, *, region: str) -> list[Any]: ...

    async def get_observations(self, *, station_ids: list[str]) -> list[Any]: ...

    async def get_radar_frames(self, *, area: str) -> list[Any]: ...
