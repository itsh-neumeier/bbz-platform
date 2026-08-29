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

from bbz_core.infra.db import session_scope
from bbz_core.infra.event_log import envelope, read_since

_POLL_SECONDS = 15.0
_CATCHUP_BATCH = 500


class EventBroker:
    def __init__(self) -> None:
        self._cond = asyncio.Condition()

    async def notify(self) -> None:
        async with self._cond:
            self._cond.notify_all()

    async def wait(self, *, timeout: float) -> None:
        async with self._cond:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._cond.wait(), timeout=timeout)


_broker = EventBroker()


def get_broker() -> EventBroker:
    return _broker


async def notify_event_appended() -> None:
    """Called by write paths after their transaction commits (best effort)."""
    await _broker.notify()


def _sse_frame(event_seq: int, event_type: str, data: dict[str, object]) -> bytes:
    body = json.dumps(data, default=str, separators=(",", ":"))
    return f"id: {event_seq}\nevent: {event_type}\ndata: {body}\n\n".encode()


async def sse_stream(
    after_seq: int,
    *,
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
) -> AsyncIterator[bytes]:
    """Yield SSE frames: catch-up from ``after_seq``, then live via poll + broker.

    ``is_disconnected`` is an optional zero-arg awaitable (``request.is_disconnected``)
    used to stop promptly when the client goes away.
    """
    broker = get_broker()
    last = after_seq
    yield b": connected\n\n"
    while True:
        if is_disconnected is not None and await is_disconnected():
            return
        async with session_scope() as session:
            rows = await read_since(session, last, limit=_CATCHUP_BATCH)
        for row in rows:
            last = row.event_seq
            yield _sse_frame(row.event_seq, row.event_type, envelope(row))
        if rows:
            continue  # drain backlog without waiting
        yield b": heartbeat\n\n"
        await broker.wait(timeout=_POLL_SECONDS)
