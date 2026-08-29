"""Event SSE fan-out: catch-up, ordering, heartbeat, live delivery (E03-13).

The generator is tested directly (no HTTP streaming client) — the API route is
a thin wrapper and its auth is covered in test_event_stream_api.py.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.event_log import append_event
from bbz_core.infra.event_stream import get_broker, notify_event_appended, sse_stream


async def _append(s: AsyncSession, event_type: str) -> int:
    async with s.begin():
        return await append_event(
            s,
            aggregate_type="event",
            aggregate_id=uuid.uuid4(),
            event_type=event_type,
            payload={},
        )


async def _next_frame(gen: object, *, timeout: float = 5.0) -> bytes:
    return await asyncio.wait_for(gen.__anext__(), timeout=timeout)  # type: ignore[attr-defined]


async def test_catch_up_replays_missed_events_in_seq_order(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    seq1 = await _append(s, "EVENT_CREATED")
    seq2 = await _append(s, "EVENT_ACCEPTED")

    gen = sse_stream(0)
    try:
        assert await _next_frame(gen) == b": connected\n\n"
        f1 = await _next_frame(gen)
        f2 = await _next_frame(gen)
    finally:
        await gen.aclose()

    assert f1.startswith(f"id: {seq1}\nevent: EVENT_CREATED\n".encode())
    assert f2.startswith(f"id: {seq2}\nevent: EVENT_ACCEPTED\n".encode())


async def test_heartbeat_when_no_events(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    gen = sse_stream(10_000_000)
    try:
        assert await _next_frame(gen) == b": connected\n\n"
        assert await _next_frame(gen) == b": heartbeat\n\n"
    finally:
        await gen.aclose()


async def test_live_event_is_delivered_after_connect(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    start = await _append(s, "EVENT_CREATED")

    gen = sse_stream(start)
    try:
        assert await _next_frame(gen) == b": connected\n\n"
        assert await _next_frame(gen) == b": heartbeat\n\n"  # nothing new yet

        pending = asyncio.ensure_future(_next_frame(gen, timeout=8.0))
        await asyncio.sleep(0.1)
        live_seq = await _append(s, "EVENT_OPENED")
        await notify_event_appended()  # wake the waiter promptly
        frame = await pending
    finally:
        await gen.aclose()

    assert frame.startswith(f"id: {live_seq}\nevent: EVENT_OPENED\n".encode())


async def test_broker_notify_is_safe_without_waiters() -> None:
    # no subscriber connected — must not raise
    await get_broker().notify()
    await notify_event_appended()


@pytest.mark.parametrize("after", [0, 5, 999])
async def test_stream_starts_with_connected_comment(db: object, after: int) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    gen = sse_stream(after)
    try:
        assert await _next_frame(gen) == b": connected\n\n"
    finally:
        await gen.aclose()
