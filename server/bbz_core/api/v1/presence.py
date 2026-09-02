"""User presence: available / pause / offline (E02-11).

Self-service ``PUT /presence`` (any authenticated user), roster read guarded by
``users.view``. Effective state is ``offline`` whenever a user has no live
session. Stream publication is added with the event stream (E03-13).
"""

from __future__ import annotations

import datetime as _dt
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, current_auth, db_session
from bbz_core.api.errors import ValidationError
from bbz_core.api.schema import StrictModel
from bbz_core.infra.models.identity import PresenceState
from bbz_core.infra.repositories.presence import PresenceRepository

router = APIRouter(prefix="/presence", tags=["presence"])


class PresenceIn(StrictModel):
    state: str


class PresenceOut(BaseModel):
    user_id: uuid.UUID
    display_name: str
    state: str
    stored_state: str
    changed_at: _dt.datetime | None


def _repo(session: AsyncSession = Depends(db_session)) -> PresenceRepository:
    return PresenceRepository(session)


def _parse(state: str) -> PresenceState:
    try:
        return PresenceState(state)
    except ValueError as exc:
        raise ValidationError(f"state must be one of {[s.value for s in PresenceState]}") from exc


@router.get("", response_model=list[PresenceOut])
async def list_presence(
    _: AuthContext = Depends(require("users.view")),
    repo: PresenceRepository = Depends(_repo),
) -> list[PresenceOut]:
    return [PresenceOut(**v.__dict__) for v in await repo.list_all()]


@router.get("/me", response_model=PresenceOut)
async def my_presence(
    ctx: AuthContext = Depends(current_auth),
    repo: PresenceRepository = Depends(_repo),
) -> PresenceOut:
    view = await repo.get(ctx.user_id)
    if view is None:
        raise ValidationError("user not found")
    return PresenceOut(**view.__dict__)


@router.put("", response_model=PresenceOut)
async def set_my_presence(
    body: PresenceIn,
    ctx: AuthContext = Depends(current_auth),
    repo: PresenceRepository = Depends(_repo),
) -> PresenceOut:
    await repo.set_state(ctx.user_id, _parse(body.state), changed_by=ctx.user_id)
    view = await repo.get(ctx.user_id)
    if view is None:
        raise ValidationError("user not found")
    return PresenceOut(**view.__dict__)
