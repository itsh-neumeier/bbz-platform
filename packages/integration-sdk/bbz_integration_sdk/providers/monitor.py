from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from bbz_integration_sdk.providers.base import Provider


@runtime_checkable
class MonitorProvider(Provider, Protocol):
    """Monitor / KVM routing provider (MASTER_PROMPT §9).

    ``monitor_mock`` now; ``monitor_weytec`` is interface-only until Weytec API
    documentation is supplied (RULES.md: never invent external API contracts).
    """

    async def list_inputs(self) -> list[Any]: ...

    async def list_outputs(self) -> list[Any]: ...

    async def get_routes(self) -> list[Any]: ...

    async def set_route(self, *, output_id: str, input_id: str, command_id: str) -> Any: ...

    async def apply_layout(self, *, layout: Any, command_id: str) -> Any: ...
