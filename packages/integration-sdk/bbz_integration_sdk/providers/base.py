from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from bbz_integration_sdk.capabilities import CapabilitySet
from bbz_integration_sdk.diagnostics import DiagnosticsReport


class ProviderInfo(BaseModel):
    integration_id: str
    provider: str
    instance_id: str
    mock: bool = False


@runtime_checkable
class Provider(Protocol):
    """Common lifecycle every provider implements."""

    async def initialize(self) -> None: ...

    def info(self) -> ProviderInfo: ...

    def capabilities(self) -> CapabilitySet: ...

    async def health(self) -> DiagnosticsReport: ...

    async def shutdown(self) -> None: ...
