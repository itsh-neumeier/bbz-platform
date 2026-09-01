"""On-demand directory sync + last-run status (roadmap E21-04).

``users.manage`` only. The scheduled singleton (``directory-sync``) runs the same
:class:`DirectorySyncService`; this endpoint lets an admin trigger a run now or a
**dry run** (computes the diff, changes nothing), and read the last run's report.
"""

from __future__ import annotations

import datetime as _dt

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.infra.models.directory_sync import DirectorySyncState
from bbz_core.infra.repositories.directory_sync import DirectorySyncReport, DirectorySyncService

router = APIRouter(prefix="/auth/directory-sync", tags=["auth"])


class SyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dry_run: bool = False
    #: override the ``ldap_sync_max_deactivations`` safety cap for this run
    force: bool = False


class SyncReportOut(BaseModel):
    source: str
    ok: bool
    dry_run: bool
    aborted: bool
    error: str | None
    scanned: int
    created: int
    deactivated: int
    role_reconciles: int
    profile_updates: int
    errors: int
    created_uids: list[str]
    deactivated_uids: list[str]

    @classmethod
    def of(cls, r: DirectorySyncReport) -> SyncReportOut:
        return cls(
            source=r.source,
            ok=r.ok,
            dry_run=r.dry_run,
            aborted=r.aborted,
            error=r.error,
            scanned=r.scanned,
            created=r.created,
            deactivated=r.deactivated,
            role_reconciles=r.role_reconciles,
            profile_updates=r.profile_updates,
            errors=r.errors,
            created_uids=r.created_uids,
            deactivated_uids=r.deactivated_uids,
        )


class SyncStateOut(BaseModel):
    source: str
    last_run_at: _dt.datetime | None
    last_success_at: _dt.datetime | None
    last_error: str | None
    last_summary: dict[str, object] | None


@router.post("", response_model=SyncReportOut)
async def run_sync(
    body: SyncRequest,
    ctx: AuthContext = Depends(require("users.manage")),
    session: AsyncSession = Depends(db_session),
) -> SyncReportOut:
    report = await DirectorySyncService(session).run(
        dry_run=body.dry_run, force=body.force, actor_id=ctx.user_id
    )
    return SyncReportOut.of(report)


@router.get("/state", response_model=SyncStateOut)
async def sync_state(
    _: AuthContext = Depends(require("users.manage")),
    session: AsyncSession = Depends(db_session),
) -> SyncStateOut:
    row = (
        await session.execute(
            select(DirectorySyncState).where(DirectorySyncState.source == "ldap_ad")
        )
    ).scalar_one_or_none()
    if row is None:
        return SyncStateOut(
            source="ldap_ad",
            last_run_at=None,
            last_success_at=None,
            last_error=None,
            last_summary=None,
        )
    return SyncStateOut(
        source=row.source,
        last_run_at=row.last_run_at,
        last_success_at=row.last_success_at,
        last_error=row.last_error,
        last_summary=row.last_summary,
    )
