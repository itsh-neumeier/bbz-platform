"""Unmapped-source queue + diagnostics (roadmap E15-12).

:func:`record_unmapped` is what the engine (E15-09) calls when a valid inbound
signal matched no published rule — an upsert on ``dedupe_key`` that bumps
``occurrences`` and ``last_seen_at`` rather than piling up rows. It never raises
for a "normal" duplicate; a genuinely unroutable event is a diagnostic, not an
error.

:class:`UnmappedSignalService` is the admin surface: list the open queue,
resolve an entry (optionally binding it to a technical endpoint — audited
``TECHNICAL_ENDPOINT_MAPPED``), and read the diagnostic counters.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import AuditAction, AuditService
from bbz_core.infra.models.technical_endpoints import TechnicalEndpoint
from bbz_core.infra.models.unmapped_signals import UnmappedSignal

#: source fields that identify where a signal came from (used for the dedupe key)
_IDENT_FIELDS = (
    "ani",
    "dnis",
    "external_source_id",
    "technical_endpoint_id",
    "cti_route_point",
    "site",
)


def unmapped_dedupe_key(signal: dict[str, Any]) -> str:
    src = signal.get("source") or {}
    ident = "|".join(str(src.get(k) or "") for k in _IDENT_FIELDS)
    provider = str(signal.get("provider") or "")
    signal_type = str(signal.get("signal_type") or "")
    return f"{provider}:{signal_type}:{ident}"[:200]


async def record_unmapped(
    session: AsyncSession,
    *,
    signal: dict[str, Any],
    resolved_endpoint_id: uuid.UUID | None = None,
) -> None:
    """Upsert an unmapped-signal row for ``signal`` (bumps the counter on repeat).

    Runs in the caller's transaction. A row already resolved by an admin is left
    resolved but its ``occurrences`` / ``last_seen_at`` still advance, so the
    diagnostics show the source is still firing.
    """
    now = _dt.datetime.now(_dt.UTC)
    stmt = (
        pg_insert(UnmappedSignal)
        .values(
            dedupe_key=unmapped_dedupe_key(signal),
            provider=str(signal.get("provider") or "unknown"),
            signal_type=str(signal.get("signal_type") or "unknown"),
            source=dict(signal.get("source") or {}),
            sample=signal,
            occurrences=1,
            first_seen_at=now,
            last_seen_at=now,
            resolved_endpoint_id=resolved_endpoint_id,
        )
        .on_conflict_do_update(
            constraint="uq_unmapped_signals_dedupe_key",
            set_={
                "occurrences": UnmappedSignal.occurrences + 1,
                "last_seen_at": now,
                "sample": signal,
            },
        )
    )
    await session.execute(stmt)


class UnmappedSignalError(Exception):
    pass


class UnmappedNotFoundError(UnmappedSignalError):
    pass


class MappingEndpointNotFoundError(UnmappedSignalError):
    """``endpoint_id`` does not reference an existing technical endpoint."""


@dataclass(frozen=True)
class DiagnosticsSummary:
    open: int
    resolved: int
    total_occurrences: int
    by_signal_type: dict[str, int]


class UnmappedSignalService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def list_queue(
        self, *, include_resolved: bool = False, limit: int = 200
    ) -> list[UnmappedSignal]:
        stmt = select(UnmappedSignal).order_by(UnmappedSignal.last_seen_at.desc()).limit(limit)
        if not include_resolved:
            stmt = stmt.where(UnmappedSignal.resolved_at.is_(None))
        return list(
            (await self._s.execute(stmt.execution_options(populate_existing=True))).scalars().all()
        )

    async def resolve(
        self,
        unmapped_id: uuid.UUID,
        *,
        endpoint_id: uuid.UUID | None,
        note: str | None,
        actor_id: uuid.UUID | None,
    ) -> UnmappedSignal:
        row = await self._s.get(UnmappedSignal, unmapped_id)
        if row is None:
            raise UnmappedNotFoundError(str(unmapped_id))
        if endpoint_id is not None and await self._s.get(TechnicalEndpoint, endpoint_id) is None:
            raise MappingEndpointNotFoundError(str(endpoint_id))

        row.resolved_at = _dt.datetime.now(_dt.UTC)
        row.resolved_by = actor_id
        row.resolved_endpoint_id = endpoint_id
        if note is not None:
            row.note = note
        await AuditService(self._s).write(
            AuditAction.TECHNICAL_ENDPOINT_MAPPED,
            actor_user_id=actor_id,
            target_type="unmapped_signal",
            target_id=str(unmapped_id),
            after={
                "dedupe_key": row.dedupe_key,
                "signal_type": row.signal_type,
                "endpoint_id": str(endpoint_id) if endpoint_id else None,
                "occurrences": row.occurrences,
            },
        )
        await self._s.commit()
        return row

    async def diagnostics(self) -> DiagnosticsSummary:
        open_count = (
            await self._s.execute(
                select(func.count())
                .select_from(UnmappedSignal)
                .where(UnmappedSignal.resolved_at.is_(None))
            )
        ).scalar_one()
        resolved_count = (
            await self._s.execute(
                select(func.count())
                .select_from(UnmappedSignal)
                .where(UnmappedSignal.resolved_at.is_not(None))
            )
        ).scalar_one()
        total_occ = (
            await self._s.execute(select(func.coalesce(func.sum(UnmappedSignal.occurrences), 0)))
        ).scalar_one()
        by_type_rows = (
            await self._s.execute(
                select(UnmappedSignal.signal_type, func.count())
                .where(UnmappedSignal.resolved_at.is_(None))
                .group_by(UnmappedSignal.signal_type)
            )
        ).all()
        return DiagnosticsSummary(
            open=int(open_count),
            resolved=int(resolved_count),
            total_occurrences=int(total_occ),
            by_signal_type={row[0]: int(row[1]) for row in by_type_rows},
        )
