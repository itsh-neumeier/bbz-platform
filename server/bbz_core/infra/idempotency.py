"""Durable command dedupe / replay protection (ADR-0011/0012, MASTER_PROMPT §15).

Every write command carries a client-generated ``X-Command-Id``. The first time
we see a key we INSERT a *pending* row and let the caller run; on completion the
caller records the HTTP result. Any later request with the same key:

* same request body, first run finished  -> the stored result is replayed, the
  effect does **not** happen twice;
* same key, first run still in flight     -> :class:`CommandInProgressError`
  (HTTP 409, the client may retry);
* same key, **different** request body    -> :class:`CommandConflictError`
  (HTTP 409, a client bug — the key was reused).

Coordinating two things (the state change and this bookkeeping row) without
two-phase commit leaves one small window: if the process dies after the caller's
transaction commits but before :meth:`IdempotencyStore.complete`, the row stays
pending and retries get ``CommandInProgressError`` until :func:`purge_stale`
removes it. Completed rows are kept for the offline-replay window and then
dropped by :func:`purge_completed`. Both run from E22 housekeeping.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, cast

from sqlalchemy import CursorResult, and_, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.commands import Command


class CommandConflictError(Exception):
    """Same ``command_id`` reused with a different request body (HTTP 409)."""


class CommandInProgressError(Exception):
    """Same ``command_id``; the first execution has not finished yet (HTTP 409)."""


def request_hash(payload: Any) -> str:
    """Stable SHA-256 of a request body (dict/list/str/bytes), key order-insensitive."""
    if isinstance(payload, bytes | bytearray):
        raw = bytes(payload)
    else:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class StoredResult:
    status: int
    body: dict[str, Any] | None


@dataclass
class Slot:
    """Yielded by :func:`idempotent`. ``replay`` is set for a duplicate command."""

    replay: StoredResult | None = None
    _result: StoredResult | None = field(default=None, repr=False)

    def set_result(self, status: int, body: dict[str, Any] | None) -> None:
        self._result = StoredResult(status=status, body=body)


class IdempotencyStore:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def claim(
        self,
        *,
        command_id: uuid.UUID,
        endpoint: str,
        request_hash: str,
        user_id: uuid.UUID | None = None,
    ) -> StoredResult | None:
        """Reserve the key. Returns ``None`` to run, or the stored result to replay."""
        stmt = (
            pg_insert(Command)
            .values(
                command_id=command_id,
                user_id=user_id,
                endpoint=endpoint,
                request_hash=request_hash,
            )
            .on_conflict_do_nothing(index_elements=["command_id"])
            .returning(Command.command_id)
        )
        inserted = (await self._s.execute(stmt)).scalar_one_or_none()
        await self._s.commit()
        if inserted is not None:
            return None
        row = (
            await self._s.execute(select(Command).where(Command.command_id == command_id))
        ).scalar_one()
        if row.request_hash != request_hash:
            raise CommandConflictError(str(command_id))
        if row.result_status is None:
            raise CommandInProgressError(str(command_id))
        return StoredResult(status=row.result_status, body=row.result_json)

    async def complete(
        self, command_id: uuid.UUID, *, status: int, body: dict[str, Any] | None
    ) -> None:
        row = (
            await self._s.execute(select(Command).where(Command.command_id == command_id))
        ).scalar_one()
        row.result_status = status
        row.result_json = body
        row.completed_at = _dt.datetime.now(_dt.UTC)
        await self._s.commit()

    async def abandon(self, command_id: uuid.UUID) -> None:
        """Drop a still-pending row so the command can be retried cleanly."""
        await self._s.execute(
            delete(Command).where(Command.command_id == command_id, Command.result_status.is_(None))
        )
        await self._s.commit()


@asynccontextmanager
async def idempotent(
    session: AsyncSession,
    *,
    command_id: uuid.UUID,
    endpoint: str,
    request_hash: str,
    user_id: uuid.UUID | None = None,
) -> AsyncIterator[Slot]:
    """Guard a write path against duplicate ``command_id`` execution.

    ::

        async with idempotent(session, command_id=cid, endpoint="POST /x",
                              request_hash=h) as slot:
            if slot.replay is not None:
                return slot.replay
            ...            # do the work + append_event in session.begin()
            slot.set_result(200, response_body)
    """
    store = IdempotencyStore(session)
    replay = await store.claim(
        command_id=command_id,
        endpoint=endpoint,
        request_hash=request_hash,
        user_id=user_id,
    )
    slot = Slot(replay=replay)
    if replay is not None:
        yield slot
        return
    try:
        yield slot
    except BaseException:
        await store.abandon(command_id)
        raise
    if slot._result is None:
        await store.abandon(command_id)
        raise RuntimeError("idempotent(): body returned without calling slot.set_result()")
    await store.complete(command_id, status=slot._result.status, body=slot._result.body)


async def _purge(session: AsyncSession, where: Any) -> int:
    res = cast("CursorResult[Any]", await session.execute(delete(Command).where(where)))
    await session.commit()
    return res.rowcount or 0


async def purge_stale(session: AsyncSession, *, older_than: _dt.timedelta) -> int:
    """Remove pending rows left behind by a crash between claim and completion."""
    cutoff = _dt.datetime.now(_dt.UTC) - older_than
    return await _purge(session, and_(Command.result_status.is_(None), Command.created_at < cutoff))


async def purge_completed(session: AsyncSession, *, older_than: _dt.timedelta) -> int:
    """Drop completed rows past the offline-replay retention window."""
    cutoff = _dt.datetime.now(_dt.UTC) - older_than
    return await _purge(
        session, and_(Command.result_status.is_not(None), Command.completed_at < cutoff)
    )
