"""Append audit rows. Immutable — there is no update/delete path."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit.actions import AuditAction
from bbz_core.infra.models.audit import AuditEvent
from bbz_core.logging import correlation_id
from bbz_core.settings import get_settings


@dataclass(frozen=True)
class AuditRecord:
    id: uuid.UUID
    occurred_at_utc: Any
    node_id: str
    action: str
    actor_user_id: uuid.UUID | None
    actor_client_id: str | None
    workplace_id: str | None
    target_type: str | None
    target_id: str | None
    reason: str | None
    correlation_id: str | None


class AuditWriter:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def record(
        self,
        action: AuditAction,
        *,
        actor_user_id: uuid.UUID | None = None,
        actor_client_id: str | None = None,
        workplace_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        reason: str | None = None,
        commit: bool = True,
    ) -> None:
        """Append one audit row.

        ``commit=False`` only flushes, so the row commits atomically with the
        caller's transaction (required for actions whose audit entry is
        mandatory, e.g. event takeover — E03-10).
        """
        self._s.add(
            AuditEvent(
                node_id=get_settings().node_id,
                action=action.value,
                actor_user_id=actor_user_id,
                actor_client_id=actor_client_id,
                workplace_id=workplace_id,
                target_type=target_type,
                target_id=target_id,
                before=before,
                after=after,
                reason=reason,
                correlation_id=correlation_id.get(),
            )
        )
        if commit:
            await self._s.commit()
        else:
            await self._s.flush()

    async def query(
        self,
        *,
        action: str | None = None,
        actor_user_id: uuid.UUID | None = None,
        target_type: str | None = None,
        since: Any | None = None,
        until: Any | None = None,
        limit: int = 100,
    ) -> list[AuditRecord]:
        stmt = select(AuditEvent).order_by(AuditEvent.occurred_at_utc.desc(), AuditEvent.id.desc())
        if action:
            stmt = stmt.where(AuditEvent.action == action)
        if actor_user_id:
            stmt = stmt.where(AuditEvent.actor_user_id == actor_user_id)
        if target_type:
            stmt = stmt.where(AuditEvent.target_type == target_type)
        if since is not None:
            stmt = stmt.where(AuditEvent.occurred_at_utc >= since)
        if until is not None:
            stmt = stmt.where(AuditEvent.occurred_at_utc <= until)
        rows = (await self._s.execute(stmt.limit(min(limit, 500)))).scalars().all()
        return [
            AuditRecord(
                id=r.id,
                occurred_at_utc=r.occurred_at_utc,
                node_id=r.node_id,
                action=r.action,
                actor_user_id=r.actor_user_id,
                actor_client_id=r.actor_client_id,
                workplace_id=r.workplace_id,
                target_type=r.target_type,
                target_id=r.target_id,
                reason=r.reason,
                correlation_id=r.correlation_id,
            )
            for r in rows
        ]
