"""Audit-write service (roadmap E04-02, MASTER_PROMPT §17/§26.12).

``AuditService.write`` appends an audit row **in the caller's transaction** —
exactly like :class:`bbz_core.infra.repositories.events.EventRepository`, it
refuses to run outside one, so "state changed but nothing was audited" and its
opposite are both impossible (they commit or roll back together).

Some actions must carry a ``reason`` (:data:`REASON_REQUIRED`); the service
enforces that. :func:`changed_fields` builds a ``{field: {from, to}}`` diff for
the ``before`` / ``after`` columns.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit.actions import AuditAction
from bbz_core.infra.models.audit import AuditEvent
from bbz_core.logging import correlation_id
from bbz_core.settings import get_settings

#: Actions for which a human-readable ``reason`` is mandatory (MASTER_PROMPT §17).
#: Feature epics add their own as they wire ``AuditService.write`` in (E04-03+).
REASON_REQUIRED: frozenset[AuditAction] = frozenset({AuditAction.EVENT_REACTIVATED})


class AuditError(RuntimeError):
    pass


class AuditNotInTransactionError(AuditError):
    """write() was called outside the caller's transaction (§17 atomicity)."""


class AuditReasonRequiredError(AuditError):
    """A reason-mandatory action was recorded without one."""


def changed_fields(
    before: Mapping[str, Any] | None, after: Mapping[str, Any] | None
) -> dict[str, dict[str, Any]]:
    """``{field: {"from": old, "to": new}}`` for every key that actually changed."""
    before = before or {}
    after = after or {}
    changes: dict[str, dict[str, Any]] = {}
    for key in before.keys() | after.keys():
        old, new = before.get(key), after.get(key)
        if old != new:
            changes[key] = {"from": old, "to": new}
    return changes


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def write(
        self,
        action: AuditAction,
        *,
        actor_user_id: uuid.UUID | None = None,
        actor_client_id: str | None = None,
        workplace_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        before: Mapping[str, Any] | None = None,
        after: Mapping[str, Any] | None = None,
        reason: str | None = None,
        event_seq_ref: int | None = None,
    ) -> None:
        if not self._s.in_transaction():
            raise AuditNotInTransactionError(
                "AuditService.write must run inside the triggering transaction"
            )
        reason = (reason or "").strip() or None
        if action in REASON_REQUIRED and reason is None:
            raise AuditReasonRequiredError(f"{action.value} requires a reason")
        self._s.add(
            AuditEvent(
                node_id=get_settings().node_id,
                action=action.value,
                actor_user_id=actor_user_id,
                actor_client_id=actor_client_id,
                workplace_id=workplace_id,
                target_type=target_type,
                target_id=target_id,
                before=dict(before) if before is not None else None,
                after=dict(after) if after is not None else None,
                reason=reason,
                correlation_id=correlation_id.get(),
                event_seq_ref=event_seq_ref,
            )
        )
        await self._s.flush()
