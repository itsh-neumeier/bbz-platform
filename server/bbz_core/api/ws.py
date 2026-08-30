"""WebSocket event stream (roadmap E03-14).

``/ws/events?after_seq=N`` — the same catch-up + live semantics as the SSE
endpoint (they share :func:`bbz_core.infra.event_stream.event_feed`), for
bidirectional clients (kiosk / agent). Commands stay on REST (ADR-0012); the
only client → server message is an ACK cursor, which is a *hint* for logging /
metrics and never changes what the server replays.
"""

from __future__ import annotations

import asyncio
import contextlib

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

from bbz_core.api.deps import ACCESS_COOKIE
from bbz_core.auth.sessions import SessionService
from bbz_core.auth.tokens import TokenError, decode_access_token
from bbz_core.authorization import PermissionService
from bbz_core.infra.db import session_scope
from bbz_core.infra.event_stream import CatchUpComplete, event_feed
from bbz_core.infra.repositories.authorization import SqlAlchemyGrantStore
from bbz_core.infra.repositories.sessions import SqlAlchemySessionStore
from bbz_core.logging import get_logger
from bbz_core.settings import get_settings

router = APIRouter()
_log = get_logger(__name__)

# Close code (RFC 6455): 1008 = policy violation.
_POLICY = 1008


def _token(websocket: WebSocket) -> str | None:
    auth = websocket.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return websocket.query_params.get("access_token") or websocket.cookies.get(ACCESS_COOKIE)


def _origin_allowed(websocket: WebSocket) -> bool:
    allowed = get_settings().cors_allow_origins
    if not allowed:
        return True  # no allow-list configured (dev) -> accept
    origin = websocket.headers.get("origin")
    return origin is None or origin in allowed


async def _authorize(websocket: WebSocket) -> bool:
    """True if the socket may subscribe. Does not accept/close the socket."""
    token = _token(websocket)
    if not token or not _origin_allowed(websocket):
        return False
    try:
        claims = decode_access_token(token)
    except TokenError:
        return False
    async with session_scope() as session:
        if not await SessionService(SqlAlchemySessionStore(session)).is_active(claims.session_id):
            return False
        svc = PermissionService(SqlAlchemyGrantStore(session))
        return await svc.authorize(claims.user_id, "events.view")


async def _pump_events(websocket: WebSocket, after_seq: int) -> None:
    from bbz_core.infra.metrics import stream_connection

    async def _disconnected() -> bool:
        return websocket.client_state != WebSocketState.CONNECTED

    with stream_connection("ws"):
        async for frame in event_feed(after_seq, is_disconnected=_disconnected):
            if websocket.client_state != WebSocketState.CONNECTED:
                return
            if frame is None:
                await websocket.send_json({"type": "heartbeat"})
            elif isinstance(frame, CatchUpComplete):
                await websocket.send_json({"type": "caught_up", "head": frame.head})
            else:
                await websocket.send_json(
                    {
                        "type": "event",
                        "event_seq": frame.event_seq,
                        "event_type": frame.event_type,
                        "envelope": frame.envelope,
                    }
                )


async def _read_acks(websocket: WebSocket) -> None:
    while True:
        message = await websocket.receive_json()
        if isinstance(message, dict) and message.get("type") == "ack":
            _log.debug("ws_ack", after_seq=message.get("after_seq"))


@router.websocket("/ws/events")
async def ws_events(websocket: WebSocket) -> None:
    if not await _authorize(websocket):
        await websocket.close(code=_POLICY)
        return
    try:
        after_seq = int(websocket.query_params.get("after_seq", "0"))
    except ValueError:
        after_seq = 0

    await websocket.accept()
    await websocket.send_json({"type": "connected", "after_seq": after_seq})

    pump = asyncio.create_task(_pump_events(websocket, after_seq))
    acks = asyncio.create_task(_read_acks(websocket))
    try:
        _, pending = await asyncio.wait({pump, acks}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
    except WebSocketDisconnect:
        pass
    finally:
        if websocket.client_state == WebSocketState.CONNECTED:
            with contextlib.suppress(RuntimeError):
                await websocket.close()
