"""Outbox dispatcher worker (roadmap E04-06).

Polls :class:`ExternalActionOutbox` for due rows, runs the registered handler,
and records the outcome — with retry + exponential backoff, and a terminal
``failed`` state after :data:`bbz_core.infra.outbox.MAX_ATTEMPTS`. Every row is
processed in its own transaction so one bad action can't block the batch, and
the status update commits together with an audit row
(``EXTERNAL_ACTION_DISPATCHED`` / ``EXTERNAL_ACTION_FAILED``).

Cluster-wide single execution is E04-08 (etcd lease); combined with the
``dedupe_key`` UNIQUE and ``SKIP LOCKED`` claim, a duplicate dispatch is not
possible.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import AuditAction, AuditService
from bbz_core.infra.db import session_scope
from bbz_core.infra.models.outbox import ExternalActionOutbox
from bbz_core.infra.outbox import MAX_ATTEMPTS, OutboxRepository
from bbz_core.logging import get_logger

_log = get_logger(__name__)

Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]


class HandlerError(RuntimeError):
    """A handler failed in a way that should be retried."""


async def _noop(_payload: dict[str, Any]) -> dict[str, Any] | None:
    return None


async def _notify(payload: dict[str, Any]) -> dict[str, Any] | None:
    # Real transports (mail/push/SIP) are wired by their own epics. For now this
    # just records that a notification would have been sent.
    _log.info("outbox_notify", channel=payload.get("channel"), subject=payload.get("subject"))
    return {"delivered": True}


DEFAULT_HANDLERS: dict[str, Handler] = {"noop": _noop, "notify": _notify}


def _camera_refs(row: ExternalActionOutbox) -> list[str]:
    refs = row.payload.get("camera_refs") or (
        [row.payload["camera_ref"]] if row.payload.get("camera_ref") else []
    )
    return [str(r) for r in refs]


async def _on_terminal_failure(session: AsyncSession, row: ExternalActionOutbox) -> None:
    """A camera action that exhausted its retries is recorded on the triggering
    event (E16-08) so an operator sees the view is unavailable — the event and
    its popup are untouched. Best-effort: never re-raises into the dispatcher.
    """
    from bbz_core.workers.camera_handlers import CAMERA_ACTION_TYPES

    event_id = row.payload.get("event_id")
    if row.action_type not in CAMERA_ACTION_TYPES or not event_id:
        return
    from bbz_core.infra.event_log import append_event

    try:
        await append_event(
            session,
            aggregate_type="event",
            aggregate_id=str(event_id),
            event_type="CAMERA_ACTION_FAILED",
            payload={
                "action_type": row.action_type,
                "camera_refs": _camera_refs(row),
                "error": row.last_error,
                "attempts": row.attempts,
            },
        )
    except Exception:  # pragma: no cover - the failure note must never block the worker
        _log.warning("camera_failure_note_failed", outbox_id=str(row.id))


async def _on_camera_dispatched(session: AsyncSession, row: ExternalActionOutbox) -> None:
    """A camera action that carried an ``event_id`` was delivered — record a
    ``CAMERA_OPENED`` domain event on the triggering event so the operator
    camera panel (``GET /events/{id}/cameras``, E16-12 / ADR-0032) can list the
    associated cameras. Best-effort mirror of :func:`_on_terminal_failure`.
    """
    from bbz_core.workers.camera_handlers import CAMERA_ACTION_TYPES

    event_id = row.payload.get("event_id")
    if row.action_type not in CAMERA_ACTION_TYPES or not event_id:
        return
    from bbz_core.infra.event_log import append_event

    try:
        await append_event(
            session,
            aggregate_type="event",
            aggregate_id=str(event_id),
            event_type="CAMERA_OPENED",
            payload={
                "action_type": row.action_type,
                "camera_refs": _camera_refs(row),
                "workplace_id": row.payload.get("workplace_id"),
            },
        )
    except Exception:  # pragma: no cover - the note must never block the worker
        _log.warning("camera_opened_note_failed", outbox_id=str(row.id))


class OutboxDispatcher:
    def __init__(self, handlers: dict[str, Handler] | None = None) -> None:
        self._handlers = dict(DEFAULT_HANDLERS if handlers is None else handlers)

    def register(self, action_type: str, handler: Handler) -> None:
        self._handlers[action_type] = handler

    async def run_once(self, *, limit: int = 20) -> int:
        """Process one batch of due rows. Returns how many rows were handled."""
        async with session_scope() as session:
            repo = OutboxRepository(session)
            async with session.begin():
                rows = await repo.claim_due(limit=limit)
                ids = [r.id for r in rows]
            # claim released; process each row in its own transaction
        handled = 0
        for row_id in ids:
            await self._process_one(row_id)
            handled += 1
        return handled

    async def _process_one(self, row_id: uuid.UUID) -> None:
        async with session_scope() as session:
            repo = OutboxRepository(session)
            async with session.begin():
                row = await session.get(ExternalActionOutbox, row_id, with_for_update=True)
                if row is None or row.status != "pending":
                    return
                handler = self._handlers.get(row.action_type)
                if handler is None:
                    await repo.mark_failed(row, error=f"no handler for {row.action_type!r}")
                    await self._audit(session, row, ok=False)
                    return
                try:
                    result = await handler(row.payload)
                except Exception as exc:
                    if row.attempts + 1 >= MAX_ATTEMPTS:
                        await repo.mark_failed(row, error=repr(exc))
                        await self._audit(session, row, ok=False)
                        await _on_terminal_failure(session, row)
                    else:
                        await repo.mark_retry(row, error=repr(exc))
                    return
                await repo.mark_dispatched(row, result=result)
                await self._audit(session, row, ok=True)
                await _on_camera_dispatched(session, row)

    @staticmethod
    async def _audit(session: AsyncSession, row: ExternalActionOutbox, *, ok: bool) -> None:
        await AuditService(session).write(
            AuditAction.EXTERNAL_ACTION_DISPATCHED if ok else AuditAction.EXTERNAL_ACTION_FAILED,
            target_type="external_action",
            target_id=str(row.id),
            after={
                "action_type": row.action_type,
                "attempts": row.attempts,
                "status": row.status,
            },
            reason=None if ok else (row.last_error or "dispatch failed"),
        )

    async def run_forever(self, *, idle_seconds: float = 2.0) -> None:  # pragma: no cover
        while True:
            with contextlib.suppress(Exception):
                if await self.run_once() == 0:
                    await asyncio.sleep(idle_seconds)
