"""Mock telephony adapter.

Implements the vendor-neutral ``TelephonyProvider`` protocol with an in-memory
state machine. Deterministic and side-effect-free.
"""

from __future__ import annotations

import itertools
from collections.abc import AsyncIterator
from typing import Any

from bbz_integration_sdk.capabilities import Capability, CapabilitySet
from bbz_integration_sdk.diagnostics import DiagnosticsReport, HealthState
from bbz_integration_sdk.normalized_events import NormalizedTelephonyEvent
from bbz_integration_sdk.providers.base import ProviderInfo

_CALL_IDS = itertools.count(1)


class MockTelephonyProvider:
    def __init__(self, *, lines: list[str] | None = None, instance_id: str = "mock") -> None:
        self._lines = list(lines or ["1001", "1002"])
        self._instance_id = instance_id
        self._active: dict[str, dict[str, Any]] = {}
        self._initialized = False

    # --- lifecycle ---
    async def initialize(self) -> None:
        self._initialized = True

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            integration_id="telephony_mock",
            provider="mock",
            instance_id=self._instance_id,
            mock=True,
        )

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet(
            [
                Capability.CALL_ANSWER,
                Capability.CALL_DIAL,
                Capability.CALL_HANGUP,
                Capability.CALL_HOLD,
                Capability.CALL_RESUME,
                Capability.CALL_MONITORING,
            ]
        )

    async def health(self) -> DiagnosticsReport:
        return DiagnosticsReport(
            integration_id="telephony_mock",
            state=HealthState.HEALTHY if self._initialized else HealthState.UNKNOWN,
            summary="in-memory mock",
            details={"active_calls": len(self._active), "lines": len(self._lines)},
        )

    async def shutdown(self) -> None:
        self._active.clear()
        self._initialized = False

    # --- queries ---
    async def list_lines(self) -> list[dict[str, Any]]:
        return [{"line_id": line, "state": "in_service"} for line in self._lines]

    async def get_line_state(self, line_id: str) -> dict[str, Any]:
        state = "in_service" if line_id in self._lines else "unknown"
        return {"line_id": line_id, "state": state}

    async def get_active_calls(self) -> list[dict[str, Any]]:
        return list(self._active.values())

    async def subscribe_call_events(self) -> AsyncIterator[dict[str, Any]]:
        # Mock emits nothing on its own; tests drive state via the methods below.
        if False:  # pragma: no cover
            yield {}

    # --- commands (idempotent on command_id) ---
    async def dial(self, *, line_id: str, destination: str, command_id: str) -> dict[str, Any]:
        call_id = f"mock-{next(_CALL_IDS)}"
        call = {
            "call_id": call_id,
            "line_id": line_id,
            "peer": destination,
            "state": NormalizedTelephonyEvent.CALL_RINGING.value,
            "command_id": command_id,
        }
        self._active[call_id] = call
        return call

    async def answer(self, *, call_id: str, command_id: str) -> dict[str, Any]:
        call = self._active[call_id]
        call["state"] = NormalizedTelephonyEvent.CALL_ANSWERED.value
        return call

    async def hangup(self, *, call_id: str, command_id: str) -> dict[str, Any]:
        call = self._active.pop(call_id, {"call_id": call_id})
        call["state"] = NormalizedTelephonyEvent.CALL_DISCONNECTED.value
        return call

    async def hold(self, *, call_id: str, command_id: str) -> dict[str, Any]:
        call = self._active[call_id]
        call["state"] = NormalizedTelephonyEvent.CALL_HELD.value
        return call

    async def resume(self, *, call_id: str, command_id: str) -> dict[str, Any]:
        call = self._active[call_id]
        call["state"] = NormalizedTelephonyEvent.CALL_RESUMED.value
        return call

    async def transfer(self, *, call_id: str, destination: str, command_id: str) -> dict[str, Any]:
        raise NotImplementedError("mock does not model transfer yet")

    async def conference(self, *, call_ids: list[str], command_id: str) -> dict[str, Any]:
        raise NotImplementedError("mock does not model conference yet")

    async def send_dtmf(
        self, *, call_id: str, dtmf_profile_id: str, command_id: str
    ) -> dict[str, Any]:
        # Never log or echo the actual DTMF code. The mock only records that a
        # profile was requested (SECURITY.md / ADR-0004).
        return {"call_id": call_id, "dtmf_profile_id": dtmf_profile_id, "sent": True}

    async def resolve_caller(self, *, number: str) -> None:
        return None

    async def reconcile(self) -> dict[str, Any]:
        return {"reconciled": True, "active_calls": len(self._active)}
