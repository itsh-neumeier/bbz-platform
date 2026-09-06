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
from bbz_integration_sdk.normalized_events import NormalizedTelephonyEvent as _E
from bbz_integration_sdk.providers.base import ProviderInfo
from bbz_integration_sdk.providers.telephony_types import (
    CallerResolution,
    CallEvent,
    CallSnapshot,
    CommandAccepted,
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
        line_endpoints: dict[str, str] | None = None,
        ari: AriClient | None = None,
    ) -> None:
        self._instance_id = instance_id
        self._line_endpoints = dict(line_endpoints or {})
        lids = list(lines or self._line_endpoints)
        self._lines = {lid: LineInfo(line_id=lid, state=LineState.UNKNOWN) for lid in lids}
        self._initialized = False
        self._ari = ari
        #: ARI events, mapped, waiting for the telephony-events singleton to drain
        self._buffer: asyncio.Queue[CallEvent] = asyncio.Queue()
        self._pump_task: asyncio.Task[None] | None = None
        #: source_call_id (SIP Call-ID) -> ARI channel id, kept current by the pump
        self._channels: dict[str, str] = {}
        #: command_id -> the ack it produced (idempotency, mirrors the mock)
        self._seen: dict[str, CommandAccepted] = {}

    # --- lifecycle ------------------------------------------------------

    async def initialize(self) -> None:
        self._initialized = True
        if self._ari is not None and self._pump_task is None:
            self._pump_task = asyncio.create_task(self._pump())

    async def _pump(self) -> None:
        """Consume the ARI event stream, map each event, keep the
        source-call-id → channel-id map current, and buffer the events we
        surface. Reconnects are handled inside ``AriClient.events``."""
        assert self._ari is not None
        async for raw in self._ari.events():
            mapped = map_ari_event(raw, provider="telephony_sip", gateway_node=self._instance_id)
            if mapped is None:
                continue
            channel_id = mapped.metadata.get("channel_id")
            if mapped.source_call_id and isinstance(channel_id, str):
                if mapped.event_type is _E.CALL_DISCONNECTED:
                    self._channels.pop(mapped.source_call_id, None)
                else:
                    self._channels[mapped.source_call_id] = channel_id
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
        active = await self.get_active_calls()
        return ReconcileResult(
            lines=list(self._lines.values()),
            active_calls=active,
            note=None if self._ari is not None else "telephony_sip scaffold — no gateway",
        )

    # --- control commands (E13-05) — idempotent on command_id --------------

    def _endpoint(self, line_id: str) -> str:
        """The Asterisk endpoint for a BBZ line. Explicit mapping wins; the
        default follows the ``PJSIP/<line>`` convention (the DB config, ADR-0033,
        fills the explicit map in production)."""
        return self._line_endpoints.get(line_id, f"PJSIP/{line_id}")

    def _ack(
        self,
        command_id: str,
        call_id: str | None,
        *,
        accepted: bool = True,
        detail: str | None = None,
    ) -> CommandAccepted:
        ack = CommandAccepted(
            command_id=command_id, accepted=accepted, call_id=call_id, detail=detail
        )
        self._seen[command_id] = ack
        return ack

    async def _on_channel(
        self, command_id: str, call_id: str, verb: str, op: str
    ) -> CommandAccepted:
        if command_id in self._seen:
            return self._seen[command_id]
        if self._ari is None:
            raise SipNotConfiguredError(verb)
        channel_id = self._channels.get(call_id)
        if channel_id is None:
            return self._ack(command_id, call_id, accepted=False, detail="call not tracked")
        try:
            await getattr(self._ari, op)(channel_id)
        except AriError as exc:
            return self._ack(command_id, call_id, accepted=False, detail=str(exc))
        return self._ack(command_id, call_id, detail=verb)

    async def dial(self, *, line_id: str, destination: str, command_id: str) -> CommandAccepted:
        if command_id in self._seen:
            return self._seen[command_id]
        if self._ari is None:
            raise SipNotConfiguredError("dial")
        try:
            channel = await self._ari.originate(
                endpoint=self._endpoint(line_id),
                extension=destination,
                context=self._ari.app_name,
            )
        except AriError as exc:
            return self._ack(command_id, None, accepted=False, detail=str(exc))
        ch_id = channel.get("id") if isinstance(channel, dict) else None
        cv = channel.get("channelvars") if isinstance(channel, dict) else {}
        call_id = (cv or {}).get("SIPCALLID") or ch_id
        if isinstance(call_id, str) and isinstance(ch_id, str):
            self._channels[call_id] = ch_id
        return self._ack(command_id, call_id if isinstance(call_id, str) else None, detail="dial")

    async def answer(self, *, call_id: str, command_id: str) -> CommandAccepted:
        return await self._on_channel(command_id, call_id, "answer", "answer")

    async def hangup(self, *, call_id: str, command_id: str) -> CommandAccepted:
        return await self._on_channel(command_id, call_id, "hangup", "hangup")

    async def hold(self, *, call_id: str, command_id: str) -> CommandAccepted:
        return await self._on_channel(command_id, call_id, "hold", "hold")

    async def resume(self, *, call_id: str, command_id: str) -> CommandAccepted:
        return await self._on_channel(command_id, call_id, "resume", "unhold")

    async def transfer(self, *, call_id: str, destination: str, command_id: str) -> CommandAccepted:
        if command_id in self._seen:
            return self._seen[command_id]
        if self._ari is None:
            raise SipNotConfiguredError("transfer")
        channel_id = self._channels.get(call_id)
        if channel_id is None:
            return self._ack(command_id, call_id, accepted=False, detail="call not tracked")
        try:
            await self._ari.redirect(channel_id, self._endpoint(destination))
        except AriError as exc:
            return self._ack(command_id, call_id, accepted=False, detail=str(exc))
        return self._ack(command_id, call_id, detail="blind transfer")

    async def conference(self, *, call_ids: list[str], command_id: str) -> CommandAccepted:
        if command_id in self._seen:
            return self._seen[command_id]
        if self._ari is None:
            raise SipNotConfiguredError("conference")
        channels = [self._channels[c] for c in call_ids if c in self._channels]
        if len(channels) < 2:
            return self._ack(
                command_id, call_ids[0] if call_ids else None, accepted=False, detail="need 2 calls"
            )
        try:
            bridge_id = await self._ari.create_bridge()
            for ch in channels:
                await self._ari.add_to_bridge(bridge_id, ch)
        except AriError as exc:
            return self._ack(command_id, call_ids[0], accepted=False, detail=str(exc))
        return self._ack(command_id, call_ids[0], detail=f"bridge {bridge_id}")

    async def send_dtmf(self, *, call_id: str, dtmf: str, command_id: str) -> CommandAccepted:
        """Emit the resolved DTMF sequence on the call's channel (E13-06).

        ``dtmf`` is the secret door-open sequence BBZ resolved (ADR-0025) — it is
        passed straight to ARI's ``channels/{id}/dtmf`` (the wire form, RFC 2833
        vs SIP INFO, is Asterisk config per ADR-0023) and is **never** logged,
        echoed in the ack ``detail``, or put in an error (ADR-0004). Idempotent
        on ``command_id`` — a replay is not re-emitted (the door must not open
        twice)."""
        if command_id in self._seen:
            return self._seen[command_id]
        if self._ari is None:
            raise SipNotConfiguredError("send_dtmf")
        channel_id = self._channels.get(call_id)
        if channel_id is None:
            return self._ack(command_id, call_id, accepted=False, detail="call not tracked")
        try:
            await self._ari.send_dtmf(channel_id, dtmf)
        except AriError:
            return self._ack(command_id, call_id, accepted=False, detail="gateway rejected dtmf")
        return self._ack(command_id, call_id, detail="dtmf sent")


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
    endpoints = cfg.get("line_endpoints")
    return SipTelephonyProvider(
        lines=list(cfg.get("lines", [])),
        line_endpoints={str(k): str(v) for k, v in endpoints.items()}
        if isinstance(endpoints, dict)
        else None,
        ari=ari,
    )
