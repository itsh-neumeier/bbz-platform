"""Asterisk ARI transport for the ``telephony_sip`` provider (roadmap E13-03,
ADR-0023).

REST for channel control + a WebSocket for the event stream, JSON on both. The
adapter owns a channel from ``StasisStart`` and drives it over
``POST /channels/{id}/…``. This module is the **transport only** — ARI-event →
``inbound_signal.v1`` mapping is E13-04, the ``TelephonyProvider`` control verbs
are E13-05, DTMF is E13-06.

Credentials never appear in a URL or a log line: the WS upgrade uses an
``Authorization: Basic`` header, and errors carry the path, not the response.
"""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx
import websockets
from websockets.exceptions import WebSocketException


@dataclass(frozen=True)
class AriConfig:
    host: str
    port: int = 8088
    tls: bool = False
    username: str = ""
    password: str = ""
    #: the Stasis application the dialplan hands calls to
    app_name: str = "bbz-sip"
    #: seconds — REST request timeout and WS open timeout
    timeout: float = 10.0
    #: seconds — cap for the reconnect backoff
    max_backoff: float = 30.0


class AriError(RuntimeError):
    """An ARI REST call failed or the gateway is unreachable."""


@dataclass
class _WsState:
    connected: bool = False
    last_error: str | None = None
    reconnects: int = 0
    _closed: bool = field(default=False, repr=False)


class AriClient:
    """One Asterisk ARI connection. Not safe for concurrent ``events()`` calls;
    the adapter runs a single consumer task."""

    def __init__(
        self, config: AriConfig, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._c = config
        scheme = "https" if config.tls else "http"
        self._rest_base = f"{scheme}://{config.host}:{config.port}/ari"
        self._http = httpx.AsyncClient(
            base_url=self._rest_base,
            auth=(config.username, config.password),
            timeout=config.timeout,
            transport=transport,  # tests inject httpx.MockTransport
        )
        self.ws = _WsState()

    @property
    def app_name(self) -> str:
        return self._c.app_name

    # --- health / reachability ---------------------------------------

    async def info(self) -> dict[str, Any]:
        """``GET /ari/asterisk/info`` — the reachability probe used by
        :meth:`SipTelephonyProvider.health`."""
        return await self._get("/asterisk/info")

    # --- REST -------------------------------------------------------

    async def _get(self, path: str) -> Any:
        try:
            r = await self._http.get(path)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            raise AriError(f"ARI GET {path}: {type(exc).__name__}") from exc

    async def _post(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        try:
            r = await self._http.post(path, params=params)
            r.raise_for_status()
            return r.json() if r.content else None
        except httpx.HTTPError as exc:
            raise AriError(f"ARI POST {path}: {type(exc).__name__}") from exc

    async def _delete(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        try:
            r = await self._http.request("DELETE", path, params=params)
            r.raise_for_status()
            return r.json() if r.content else None
        except httpx.HTTPError as exc:
            raise AriError(f"ARI DELETE {path}: {type(exc).__name__}") from exc

    async def list_channels(self) -> list[dict[str, Any]]:
        result = await self._get("/channels")
        return list(result) if isinstance(result, list) else []

    async def answer(self, channel_id: str) -> None:
        await self._post(f"/channels/{channel_id}/answer")

    async def hangup(self, channel_id: str) -> None:
        # ARI hangs up a channel with DELETE /channels/{id} — there is no
        # POST .../hangup verb (that route 404s "Resource not found").
        await self._delete(f"/channels/{channel_id}")

    async def hold(self, channel_id: str) -> None:
        await self._post(f"/channels/{channel_id}/hold")

    async def unhold(self, channel_id: str) -> None:
        # remove-hold is DELETE /channels/{id}/hold, not POST .../unhold.
        await self._delete(f"/channels/{channel_id}/hold")

    async def send_dtmf(self, channel_id: str, digits: str) -> None:
        await self._post(f"/channels/{channel_id}/dtmf", params={"dtmf": digits})

    async def redirect(self, channel_id: str, endpoint: str) -> None:
        await self._post(f"/channels/{channel_id}/redirect", params={"endpoint": endpoint})

    async def originate(
        self,
        *,
        endpoint: str,
        extension: str = "",
        context: str = "",
        app: str = "",
    ) -> dict[str, Any]:
        """Create an outbound channel. ``app`` sends it straight into a Stasis
        application (used by the integration harness); otherwise it lands at
        ``extension@context`` in the dialplan (the ``dial`` verb's path)."""
        params: dict[str, Any] = {"endpoint": endpoint, "callerId": "BBZ"}
        if app:
            params["app"] = app
        if extension:
            params["extension"] = extension
        if context:
            params["context"] = context
        result = await self._post("/channels", params=params)
        return dict(result) if isinstance(result, dict) else {}

    async def create_bridge(self) -> str:
        result = await self._post("/bridges", params={"type": "mixing"})
        bid = result.get("id") if isinstance(result, dict) else None
        if not bid:
            raise AriError("ARI POST /bridges: no bridge id returned")
        return str(bid)

    async def add_to_bridge(self, bridge_id: str, channel_id: str) -> None:
        await self._post(f"/bridges/{bridge_id}/addChannel", params={"channel": channel_id})

    # --- event stream --------------------------------------------

    def _ws_uri(self) -> str:
        scheme = "wss" if self._c.tls else "ws"
        return f"{scheme}://{self._c.host}:{self._c.port}/ari/events?app={self._c.app_name}"

    def _auth_header(self) -> dict[str, str]:
        token = base64.b64encode(f"{self._c.username}:{self._c.password}".encode()).decode()
        return {"Authorization": f"Basic {token}"}

    async def events(self, *, reconnect: bool = True) -> AsyncIterator[dict[str, Any]]:
        """Yield ARI events as parsed dicts. On a dropped socket, reconnects with
        exponential backoff (the caller reconciles any gap against
        :meth:`list_channels`). Stops when :meth:`aclose` is called."""
        backoff = 1.0
        while not self.ws._closed:
            try:
                async with websockets.connect(
                    self._ws_uri(),
                    additional_headers=self._auth_header(),
                    open_timeout=self._c.timeout,
                ) as ws:
                    self.ws.connected = True
                    self.ws.last_error = None
                    backoff = 1.0
                    async for raw in ws:
                        try:
                            yield json.loads(raw)
                        except (json.JSONDecodeError, TypeError):
                            continue
            except (TimeoutError, WebSocketException, OSError) as exc:
                self.ws.connected = False
                self.ws.last_error = type(exc).__name__
                if not reconnect or self.ws._closed:
                    return
                self.ws.reconnects += 1
                await asyncio.sleep(min(backoff, self._c.max_backoff))
                backoff *= 2
            else:
                self.ws.connected = False
                return

    async def aclose(self) -> None:
        self.ws._closed = True
        await self._http.aclose()
