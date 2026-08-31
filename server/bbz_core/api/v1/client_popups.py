"""Client-popup delivery API (roadmap E15-14, backend slice).

A BBZ client polls ``GET /api/v1/client/popups`` for the live popups bound to
its workplace (a trigger ``show_client_popup`` action created them, E15-06), and
confirms delivery / dismissal. The popup only ever reaches its bound workplace.

The bottom-right UI component, its timeout animation, keyboard handling and any
context action (e.g. door open) are Epic 07 / Epic 17.
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.api.errors import ForbiddenError, NotFoundError
from bbz_core.infra.models.client_popup_events import ClientPopupEvent
from bbz_core.infra.repositories.client_popups import (
    ClientPopupService,
    PopupNotFoundError,
    PopupWorkplaceMismatchError,
)

router = APIRouter(prefix="/client", tags=["client-popups"])


@contextlib.contextmanager
def _translate() -> Iterator[None]:
    try:
        yield
    except PopupNotFoundError as exc:
        raise NotFoundError("client popup not found") from exc
    except PopupWorkplaceMismatchError as exc:
        raise ForbiddenError("this popup is bound to a different workplace") from exc


class PopupOut(BaseModel):
    id: uuid.UUID
    workplace_id: uuid.UUID
    kind: str
    payload: dict[str, object]
    expires_at: _dt.datetime
    delivered_at: _dt.datetime | None
    dismissed_at: _dt.datetime | None


def _out(row: ClientPopupEvent) -> PopupOut:
    return PopupOut(
        id=row.id,
        workplace_id=row.workplace_id,
        kind=row.kind,
        payload=dict(row.payload or {}),
        expires_at=row.expires_at,
        delivered_at=row.delivered_at,
        dismissed_at=row.dismissed_at,
    )


def _svc(session: AsyncSession = Depends(db_session)) -> ClientPopupService:
    return ClientPopupService(session)


@router.get("/popups", response_model=list[PopupOut])
async def list_popups(
    workplace_id: uuid.UUID = Query(...),
    _: AuthContext = Depends(require("events.view")),
    svc: ClientPopupService = Depends(_svc),
) -> list[PopupOut]:
    """The live (unexpired, undismissed) popups for one workplace."""
    return [_out(r) for r in await svc.pending_for(workplace_id)]


@router.post("/popups/{popup_id}/delivered", response_model=PopupOut)
async def mark_delivered(
    popup_id: uuid.UUID,
    workplace_id: uuid.UUID = Query(...),
    ctx: AuthContext = Depends(require("events.view")),
    svc: ClientPopupService = Depends(_svc),
) -> PopupOut:
    """The client confirms it displayed the popup — idempotent, audited."""
    with _translate():
        return _out(
            await svc.mark_delivered(popup_id, workplace_id=workplace_id, actor_id=ctx.user_id)
        )


@router.post("/popups/{popup_id}/dismiss", response_model=PopupOut, status_code=status.HTTP_200_OK)
async def dismiss_popup(
    popup_id: uuid.UUID,
    workplace_id: uuid.UUID = Query(...),
    ctx: AuthContext = Depends(require("events.view")),
    svc: ClientPopupService = Depends(_svc),
) -> PopupOut:
    with _translate():
        return _out(await svc.dismiss(popup_id, workplace_id=workplace_id, actor_id=ctx.user_id))
