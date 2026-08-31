"""Live event fan-out + catch-up for the SSE / WebSocket streams (E03-13/14).

Catch-up is authoritative: a subscriber replays ``domain_events`` from its last
acknowledged ``event_seq`` via :func:`bbz_core.infra.event_log.read_since`, then
follows along. "Following along" is a short DB poll; the in-process
:class:`EventBroker` only *shortens* the poll wait when this node just wrote an
event (it is a latency hint, never the source of truth — a missed notification
is caught by the next poll). After a node failover the client simply reconnects
with its ``after_seq`` against the other node's identical log (ADR-0011).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from bbz_core.infra.db import session_scope
from bbz_core.infra.event_log import envelope, head_seq, read_since

_POLL_SECONDS = 15.0
_CATCHUP_BATCH = 500


class EventBroker:
    """A latency hint for the stream poll, never the source of truth.

    Loop-aware: an :class:`asyncio.Condition` is pinned to the loop it is first
    awaited on, so the broker makes a fresh one whenever the running loop
    changes. In production the loop never changes (one uvicorn loop); this only
    matters for per-test loop isolation and for any worker that swaps loops.
    """

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._cond = asyncio.Condition()

    def _condition(self) -> asyncio.Condition:
        loop = asyncio.get_running_loop()
        if loop is not self._loop:
            self._loop = loop
            self._cond = asyncio.Condition()
        return self._cond

    async def notify(self) -> None:
        cond = self._condition()
        async with cond:
            cond.notify_all()

    async def wait(self, *, timeout: float) -> None:
        cond = self._condition()
        async with cond:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(cond.wait(), timeout=timeout)


_broker = EventBroker()


def get_broker() -> EventBroker:
    return _broker


async def notify_event_appended() -> None:
    """Called by write paths after their transaction commits (best effort)."""
    await _broker.notify()


@dataclass(frozen=True)
class EventFrame:
    event_seq: int
    event_type: str
    envelope: dict[str, Any]


@dataclass(frozen=True)
class CatchUpComplete:
    """Emitted once, after the ``after_seq`` backlog is drained: the client now
    holds everything through ``head`` and can trust a later ``event_seq`` jump
    as a failover gap, not a loss (docs/client-catchup)."""

    head: int


async def event_feed(
    after_seq: int,
    *,
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
) -> AsyncIterator[EventFrame | CatchUpComplete | None]:
    """Catch-up from ``after_seq`` then live: an :class:`EventFrame` per event,
    a single :class:`CatchUpComplete` once the backlog is drained, ``None`` as a
    heartbeat tick. Shared by the SSE and WebSocket endpoints.
    """
    broker = get_broker()
    last = after_seq
    caught_up = False
    while True:
        if is_disconnected is not None and await is_disconnected():
            return
        async with session_scope() as session:
            rows = await read_since(session, last, limit=_CATCHUP_BATCH)
            for row in rows:
                last = row.event_seq
                yield EventFrame(row.event_seq, row.event_type, envelope(row))
            if not rows and not caught_up:
                last = max(last, await head_seq(session))
        if rows:
            continue  # drain backlog without waiting
        if not caught_up:
            caught_up = True
            yield CatchUpComplete(last)
        yield None
        await broker.wait(timeout=_POLL_SECONDS)


def _sse_frame(event_seq: int, event_type: str, data: dict[str, object]) -> bytes:
    body = json.dumps(data, default=str, separators=(",", ":"))
    return f"id: {event_seq}\nevent: {event_type}\ndata: {body}\n\n".encode()


async def sse_stream(
    after_seq: int,
    *,
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
) -> AsyncIterator[bytes]:
    """SSE framing over :func:`event_feed`."""
    from bbz_core.infra.metrics import stream_connection

    yield b": connected\n\n"
    with stream_connection("sse"):
        async for frame in event_feed(after_seq, is_disconnected=is_disconnected):
            if frame is None:
                yield b": heartbeat\n\n"
            elif isinstance(frame, CatchUpComplete):
                body = json.dumps({"head": frame.head}, separators=(",", ":"))
                yield f"event: caught_up\ndata: {body}\n\n".encode()
            else:
                yield _sse_frame(frame.event_seq, frame.event_type, frame.envelope)
