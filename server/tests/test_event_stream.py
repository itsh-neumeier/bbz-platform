"""Event SSE fan-out: catch-up, ordering, heartbeat, live delivery (E03-13).

The generator is tested directly (no HTTP streaming client) — the API route is
a thin wrapper and its auth is covered in test_event_stream_api.py.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.event_log import append_event, head_seq
from bbz_core.infra.event_stream import (
    CatchUpComplete,
    EventFrame,
    event_feed,
    get_broker,
    notify_event_appended,
    sse_stream,
)

_PAYLOADS: dict[str, dict[str, str]] = {
    "EVENT_CREATED": {"title": "x", "priority": "high", "actor_id": "u1"},
}


def _payload(event_type: str) -> dict[str, str]:
    return _PAYLOADS.get(event_type, {"from": "new", "to": "accepted", "actor_id": "u1"})


async def _append(s: AsyncSession, event_type: str) -> int:
    async with s.begin():
        return await append_event(
            s,
            aggregate_type="event",
            aggregate_id=uuid.uuid4(),
            event_type=event_type,
            payload=_payload(event_type),
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


async def test_caught_up_frame_follows_the_backlog(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    await _append(s, "EVENT_CREATED")
    seq2 = await _append(s, "EVENT_ACCEPTED")

    gen = sse_stream(0)
    frames: list[bytes] = []
    try:
        for _ in range(4):  # connected, event, event, caught_up
            frames.append(await _next_frame(gen))
    finally:
        await gen.aclose()

    assert frames[3] == f'event: caught_up\ndata: {{"head":{seq2}}}\n\n'.encode()


async def test_heartbeat_when_no_events(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    gen = sse_stream(10_000_000)
    try:
        assert await _next_frame(gen) == b": connected\n\n"
        f = await _next_frame(gen)
        assert f.startswith(b"event: caught_up\n")  # client is already current
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
        assert (await _next_frame(gen)).startswith(b"event: caught_up\n")
        assert await _next_frame(gen) == b": heartbeat\n\n"  # nothing new yet

        pending = asyncio.ensure_future(_next_frame(gen, timeout=8.0))
        await asyncio.sleep(0.1)
        live_seq = await _append(s, "EVENT_OPENED")
        await notify_event_appended()  # wake the waiter promptly
        frame = await pending
    finally:
        await gen.aclose()

    assert frame.startswith(f"id: {live_seq}\nevent: EVENT_OPENED\n".encode())


async def test_event_feed_yields_typed_frames_then_heartbeat(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    seq = await _append(s, "EVENT_CREATED")

    gen = event_feed(0)
    try:
        first = await asyncio.wait_for(gen.__anext__(), timeout=5.0)
        second = await asyncio.wait_for(gen.__anext__(), timeout=5.0)
    finally:
        await gen.aclose()

    assert isinstance(first, EventFrame)
    assert (first.event_seq, first.event_type) == (seq, "EVENT_CREATED")
    assert first.envelope["event_seq"] == seq
    assert second == CatchUpComplete(seq)  # backlog drained -> caught up at `seq`


async def test_head_seq_and_gap_tolerant_catch_up(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    assert await head_seq(s) >= 0
    await s.rollback()
    s1 = await _append(s, "EVENT_CREATED")
    s2 = await _append(s, "EVENT_ACCEPTED")
    assert await head_seq(s) == s2
    await s.rollback()

    # a client that is already ahead of everything: no events, immediate caught_up
    gen = event_feed(s2)
    try:
        first = await asyncio.wait_for(gen.__anext__(), timeout=5.0)
    finally:
        await gen.aclose()
    assert first == CatchUpComplete(s2)

    # a client mid-log gets exactly the rows above its cursor, then caught_up
    gen = event_feed(s1)
    got: list[object] = []
    try:
        for _ in range(2):
            got.append(await asyncio.wait_for(gen.__anext__(), timeout=5.0))
    finally:
        await gen.aclose()
    assert isinstance(got[0], EventFrame) and got[0].event_seq == s2
    assert got[1] == CatchUpComplete(s2)


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
