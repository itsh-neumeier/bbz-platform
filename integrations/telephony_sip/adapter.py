"""``telephony_sip`` adapter — Asterisk ARI (roadmap E13-03, ADR-0023/0033).

A protocol-conformant :class:`~bbz_integration_sdk.providers.TelephonyProvider`.
With a ``gateway`` config block it opens an :class:`~integrations.telephony_sip.ari.AriClient`
and :meth:`health` probes the live gateway; without one it stays a scaffold
(``UNKNOWN`` health, control commands raise). Event mapping is E13-04, the
control verbs E13-05, DTMF E13-06 — those still raise :class:`SipNotConfiguredError`.

Never depends on ``integrations.telephony_cucm`` or Cisco JTAPI (ADR-0002 §8.17).
The raw DTMF code is always a secret — only the profile id is ever handled here
(ADR-0004).
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as _dt
from collections.abc import AsyncIterator
from typing import Any

from bbz_integration_sdk.capabilities import Capability, CapabilitySet
from bbz_integration_sdk.diagnostics import DiagnosticsReport, HealthState
from bbz_integration_sdk.providers.base import ProviderInfo
from bbz_integration_sdk.providers.telephony_types import (
    CallerResolution,
    CallEvent,
    CallSnapshot,
    LineInfo,
    LineState,
    ReconcileResult,
)
from integrations.telephony_sip.ari import AriClient, AriConfig, AriError
from integrations.telephony_sip.events import map_ari_event

_CAPABILITIES = (
    Capability.CALL_ANSWER,
    Capability.CALL_DIAL,
    Capability.CALL_HANGUP,
    Capability.CALL_HOLD,
    Capability.CALL_RESUME,
    Capability.CALL_TRANSFER,
    Capability.CALL_SEND_DTMF,
    Capability.CALL_MONITORING,
)


class SipNotConfiguredError(RuntimeError):
    """A control command was issued before the SIP gateway binding exists (E13-03+)."""


class SipTelephonyProvider:
    def __init__(
        self,
        *,
        instance_id: str = "sip",
        lines: list[str] | None = None,
        ari: AriClient | None = None,
    ) -> None:
        self._instance_id = instance_id
        self._lines = {lid: LineInfo(line_id=lid, state=LineState.UNKNOWN) for lid in (lines or [])}
        self._initialized = False
        self._ari = ari
        #: ARI events, mapped, waiting for the telephony-events singleton to drain
        self._buffer: asyncio.Queue[CallEvent] = asyncio.Queue()
        self._pump_task: asyncio.Task[None] | None = None

    # --- lifecycle ------------------------------------------------------

    async def initialize(self) -> None:
        self._initialized = True
        if self._ari is not None and self._pump_task is None:
            self._pump_task = asyncio.create_task(self._pump())

    async def _pump(self) -> None:
        """Consume the ARI event stream, map each event and buffer the ones we
        surface. Reconnects are handled inside ``AriClient.events``; on a
        reconnect the caller reconciles against ``get_active_calls``."""
        assert self._ari is not None
        async for raw in self._ari.events():
            mapped = map_ari_event(raw, provider="telephony_sip", gateway_node=self._instance_id)
            if mapped is not None:
                self._buffer.put_nowait(mapped)

    async def drain_events(self, limit: int = 100) -> list[CallEvent]:
        """Pop up to ``limit`` buffered events. The ``telephony-events`` cluster
        singleton calls this each tick and feeds the results through
        ``ingest_telephony_event`` (same signature as the mock provider's)."""
        out: list[CallEvent] = []
        while len(out) < limit:
            try:
                out.append(self._buffer.get_nowait())
            except asyncio.QueueEmpty:
                break
        return out

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            integration_id="telephony_sip",
            provider="sip",
            instance_id=self._instance_id,
            mock=False,
        )

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet(_CAPABILITIES)

    async def health(self) -> DiagnosticsReport:
        base = {"initialized": self._initialized, "lines": len(self._lines)}
        if self._ari is None:
            return DiagnosticsReport(
                integration_id="telephony_sip",
                state=HealthState.UNKNOWN,
                summary="no gateway configured (scaffold)",
                checked_at=_dt.datetime.now(_dt.UTC),
                details=base,
            )
        try:
            info = await self._ari.info()
        except AriError as exc:
            return DiagnosticsReport(
                integration_id="telephony_sip",
                state=HealthState.UNAVAILABLE,
                summary=f"Asterisk ARI unreachable: {exc}",
                checked_at=_dt.datetime.now(_dt.UTC),
                details={**base, "ws_connected": self._ari.ws.connected},
            )
        version = (info.get("system") or {}).get("version") if isinstance(info, dict) else None
        ws_ok = self._ari.ws.connected
        return DiagnosticsReport(
            integration_id="telephony_sip",
            state=HealthState.HEALTHY if ws_ok else HealthState.DEGRADED,
            summary=f"Asterisk {version or 'connected'}"
            + ("" if ws_ok else " — event stream not connected"),
            checked_at=_dt.datetime.now(_dt.UTC),
            details={**base, "asterisk_version": version, "ws_connected": ws_ok},
        )

    async def shutdown(self) -> None:
        self._initialized = False
        if self._pump_task is not None:
            self._pump_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._pump_task
            self._pump_task = None
        if self._ari is not None:
            await self._ari.aclose()

    # --- read queries (safe defaults) --------------------------------

    async def list_lines(self) -> list[LineInfo]:
        return list(self._lines.values())

    async def get_line_state(self, line_id: str) -> LineInfo:
        return self._lines.get(line_id, LineInfo(line_id=line_id, state=LineState.UNKNOWN))

    async def get_active_calls(self) -> list[CallSnapshot]:
        """Live channels in the Stasis app, as :class:`CallSnapshot`s — the
        reconnect resync source (a missed hangup during a WS drop is caught by
        comparing this against tracked calls)."""
        if self._ari is None:
            return []
        try:
            channels = await self._ari.list_channels()
        except AriError:
            return []
        out: list[CallSnapshot] = []
        for ch in channels:
            cid = ch.get("channelvars", {}).get("SIPCALLID") if isinstance(ch, dict) else None
            call_id = str(cid or ch.get("id", ""))
            if call_id:
                out.append(CallSnapshot(call_id=call_id, line_id=str(ch.get("name") or "") or None))
        return out

    async def subscribe_call_events(self) -> AsyncIterator[CallEvent]:
        """The mapped ARI event stream. A deployment consumes **either** this or
        :meth:`drain_events` (the ``telephony-events`` singleton uses the
        latter) — they share one buffer."""
        while self._ari is not None:
            yield await self._buffer.get()

    async def resolve_caller(self, *, number: str) -> CallerResolution:
        return CallerResolution(number=number, matched=False)

    async def reconcile(self) -> ReconcileResult:
        return ReconcileResult(
            lines=list(self._lines.values()),
            active_calls=[],
            note="telephony_sip scaffold — nothing to reconcile",
        )

    # --- control commands (not wired yet) ---------------------------

    async def dial(self, *, line_id: str, destination: str, command_id: str) -> Any:
        raise SipNotConfiguredError("dial")

    async def answer(self, *, call_id: str, command_id: str) -> Any:
        raise SipNotConfiguredError("answer")

    async def hangup(self, *, call_id: str, command_id: str) -> Any:
        raise SipNotConfiguredError("hangup")

    async def hold(self, *, call_id: str, command_id: str) -> Any:
        raise SipNotConfiguredError("hold")

    async def resume(self, *, call_id: str, command_id: str) -> Any:
        raise SipNotConfiguredError("resume")

    async def transfer(self, *, call_id: str, destination: str, command_id: str) -> Any:
        raise SipNotConfiguredError("transfer")

    async def conference(self, *, call_ids: list[str], command_id: str) -> Any:
        raise SipNotConfiguredError("conference")

    async def send_dtmf(self, *, call_id: str, dtmf: str, command_id: str) -> Any:
        # `dtmf` is the resolved secret sequence (ADR-0025) — a real adapter emits
        # it via SIP INFO / RFC 2833 and must never log or echo it (ADR-0004)
        raise SipNotConfiguredError("send_dtmf")


def build(config: dict[str, Any] | None = None) -> SipTelephonyProvider:
    """Entry point for the integration host's dynamic loader (E11-06).

    ``config`` shape is ``config_schema.json``. A ``gateway`` block opens the
    ARI client; production reads this from the DB (ADR-0033), dev/CI from
    env/config. Credentials come inline here only for a file-provisioned
    instance — the DB path decrypts them in-process (never inline).
    """
    cfg = config or {}
    ari: AriClient | None = None
    gw = cfg.get("gateway")
    if isinstance(gw, dict) and gw.get("host"):
        creds = cfg.get("credentials") or {}
        ari = AriClient(
            AriConfig(
                host=str(gw["host"]),
                port=int(gw.get("port", 8088)),
                tls=bool(gw.get("tls", False)),
                username=str(creds.get("username", "")),
                password=str(creds.get("password", "")),
                app_name=str(cfg.get("app_name", "bbz-sip")),
            )
        )
    return SipTelephonyProvider(lines=list(cfg.get("lines", [])), ari=ari)
