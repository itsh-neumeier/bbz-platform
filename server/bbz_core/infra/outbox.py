"""Transactional-outbox access (ADR-0011).

:func:`enqueue` runs in the caller's transaction — the outbox row commits or
rolls back with the state change that needs the side effect. The dispatcher
(``bbz_core.workers.outbox_dispatcher``) picks rows up with
``FOR UPDATE SKIP LOCKED`` so two workers never grab the same row, and the
``dedupe_key`` UNIQUE constraint makes a double-enqueue impossible.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.outbox import ExternalActionOutbox, OutboxStatus
from bbz_core.logging import correlation_id

_BASE_BACKOFF = _dt.timedelta(seconds=5)
_MAX_BACKOFF = _dt.timedelta(minutes=30)
MAX_ATTEMPTS = 8


class OutboxError(RuntimeError):
    pass


class NotInTransactionError(OutboxError):
    pass


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


def _backoff(attempts: int) -> _dt.datetime:
    delay: _dt.timedelta = min(_BASE_BACKOFF * (2**attempts), _MAX_BACKOFF)
    return _now() + delay


async def enqueue(
    session: AsyncSession,
    *,
    dedupe_key: str,
    action_type: str,
    payload: dict[str, Any],
) -> bool:
    """Add an outbox row in the caller's transaction. Returns False if the
    ``dedupe_key`` already exists (the action is already queued/done)."""
    if not session.in_transaction():
        raise NotInTransactionError("enqueue must run inside the caller's transaction")
    stmt = (
        pg_insert(ExternalActionOutbox)
        .values(
            dedupe_key=dedupe_key,
            action_type=action_type,
            payload=payload,
            correlation_id=correlation_id.get(),
        )
        .on_conflict_do_nothing(index_elements=["dedupe_key"])
        .returning(ExternalActionOutbox.id)
    )
    inserted = (await session.execute(stmt)).scalar_one_or_none()
    return inserted is not None


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def claim_due(self, *, limit: int = 20) -> list[ExternalActionOutbox]:
        """Lock up to ``limit`` due pending rows for this worker."""
        rows = (
            (
                await self._s.execute(
                    select(ExternalActionOutbox)
                    .where(
                        ExternalActionOutbox.status == OutboxStatus.PENDING.value,
                        ExternalActionOutbox.next_attempt_at <= _now(),
                    )
                    .order_by(ExternalActionOutbox.next_attempt_at.asc())
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def mark_dispatched(
        self, row: ExternalActionOutbox, *, result: dict[str, Any] | None
    ) -> None:
        row.status = OutboxStatus.DISPATCHED.value
        row.attempts += 1
        row.result = result
        row.last_error = None
        row.dispatched_at = _now()

    async def mark_retry(self, row: ExternalActionOutbox, *, error: str) -> None:
        row.attempts += 1
        row.last_error = error
        row.next_attempt_at = _backoff(row.attempts)

    async def mark_failed(self, row: ExternalActionOutbox, *, error: str) -> None:
        row.status = OutboxStatus.FAILED.value
        row.attempts += 1
        row.last_error = error
