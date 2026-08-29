"""Durable command dedupe: claim/replay, body mismatch, in-flight, races."""

from __future__ import annotations

import asyncio
import datetime as _dt
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.idempotency import (
    CommandConflictError,
    CommandInProgressError,
    IdempotencyStore,
    idempotent,
    purge_stale,
    request_hash,
)

ENDPOINT = "POST /api/v1/events"


def test_request_hash_is_key_order_insensitive() -> None:
    assert request_hash({"a": 1, "b": 2}) == request_hash({"b": 2, "a": 1})
    assert request_hash({"a": 1}) != request_hash({"a": 2})
    assert request_hash(b"raw") == request_hash(b"raw")


async def test_claim_runs_once_then_replays(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    store = IdempotencyStore(s)
    cid = uuid.uuid4()
    h = request_hash({"title": "x"})

    assert await store.claim(command_id=cid, endpoint=ENDPOINT, request_hash=h) is None
    await store.complete(cid, status=201, body={"id": "abc"})

    replay = await store.claim(command_id=cid, endpoint=ENDPOINT, request_hash=h)
    assert replay is not None
    assert replay.status == 201
    assert replay.body == {"id": "abc"}


async def test_same_key_different_body_conflicts(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    store = IdempotencyStore(s)
    cid = uuid.uuid4()

    await store.claim(command_id=cid, endpoint=ENDPOINT, request_hash=request_hash({"a": 1}))
    await store.complete(cid, status=201, body=None)

    with pytest.raises(CommandConflictError):
        await store.claim(command_id=cid, endpoint=ENDPOINT, request_hash=request_hash({"a": 2}))


async def test_duplicate_while_in_flight_raises(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    store = IdempotencyStore(s)
    cid = uuid.uuid4()
    h = request_hash({"a": 1})

    assert await store.claim(command_id=cid, endpoint=ENDPOINT, request_hash=h) is None
    with pytest.raises(CommandInProgressError):
        await store.claim(command_id=cid, endpoint=ENDPOINT, request_hash=h)


async def test_abandon_allows_retry(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    store = IdempotencyStore(s)
    cid = uuid.uuid4()
    h = request_hash({"a": 1})

    assert await store.claim(command_id=cid, endpoint=ENDPOINT, request_hash=h) is None
    await store.abandon(cid)
    # key is free again
    assert await store.claim(command_id=cid, endpoint=ENDPOINT, request_hash=h) is None


async def test_idempotent_cm_executes_once(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    cid = uuid.uuid4()
    h = request_hash({"title": "x"})
    runs = 0

    for _ in range(3):
        async with idempotent(s, command_id=cid, endpoint=ENDPOINT, request_hash=h) as slot:
            if slot.replay is not None:
                assert slot.replay.status == 201
                continue
            runs += 1
            slot.set_result(201, {"n": runs})

    assert runs == 1


async def test_idempotent_cm_abandons_on_error(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    cid = uuid.uuid4()
    h = request_hash({"a": 1})

    with pytest.raises(RuntimeError, match="boom"):
        async with idempotent(s, command_id=cid, endpoint=ENDPOINT, request_hash=h) as slot:
            assert slot.replay is None
            raise RuntimeError("boom")

    # nothing persisted -> retry succeeds
    async with idempotent(s, command_id=cid, endpoint=ENDPOINT, request_hash=h) as slot:
        assert slot.replay is None
        slot.set_result(201, None)


async def test_concurrent_identical_commands_execute_once(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    from bbz_core.infra.db import get_sessionmaker

    cid = uuid.uuid4()
    h = request_hash({"title": "x"})

    async def attempt() -> str:
        async with get_sessionmaker()() as sess:
            store = IdempotencyStore(sess)
            try:
                res = await store.claim(command_id=cid, endpoint=ENDPOINT, request_hash=h)
            except CommandInProgressError:
                return "in_progress"
            return "ran" if res is None else "replayed"

    outcomes = await asyncio.gather(*(attempt() for _ in range(6)))
    assert outcomes.count("ran") == 1
    assert all(o in {"ran", "in_progress"} for o in outcomes)


async def test_purge_stale_removes_old_pending_rows(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    from sqlalchemy import text

    store = IdempotencyStore(s)
    cid = uuid.uuid4()
    await store.claim(command_id=cid, endpoint=ENDPOINT, request_hash=request_hash({}))
    await s.execute(
        text("UPDATE commands SET created_at = now() - interval '2 days' WHERE command_id = :c"),
        {"c": cid},
    )
    await s.commit()

    removed = await purge_stale(s, older_than=_dt.timedelta(days=1))
    assert removed == 1
    assert (
        await store.claim(command_id=cid, endpoint=ENDPOINT, request_hash=request_hash({})) is None
    )
