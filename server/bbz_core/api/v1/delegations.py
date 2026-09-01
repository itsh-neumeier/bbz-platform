"""Temporary permission delegation API (roadmap E21-07).

``permissions.manage``. The caller delegates one of **their own** permissions to
another user for a bounded time; the delegatee gains it until it expires or is
revoked. Both actions audit (`PERMISSION_DELEGATED` / `PERMISSION_DELEGATION_REVOKED`).
"""

from __future__ import annotations

import datetime as _dt
import uuid

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.api.errors import NotFoundError, ValidationError
from bbz_core.authorization.keys import PermissionKeyError
from bbz_core.infra.repositories.delegation import (
    DelegationError,
    DelegationNotFound,
    DelegationService,
    DelegationView,
    NotDelegatorsToGive,
)

router = APIRouter(prefix="/permissions/delegations", tags=["rbac"])


class DelegationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to_user_id: uuid.UUID
    permission_key: str = Field(min_length=1, max_length=100)
    expires_at: _dt.datetime
    scope: str = "global"


class DelegationOut(BaseModel):
    id: uuid.UUID
    from_user_id: uuid.UUID
    to_user_id: uuid.UUID
    permission_key: str
    scope: str
    granted_at: _dt.datetime
    expires_at: _dt.datetime
    revoked_at: _dt.datetime | None
    active: bool


class DelegationsResponse(BaseModel):
    delegations: list[DelegationOut]


def _out(d: DelegationView) -> DelegationOut:
    return DelegationOut(
        id=d.id,
        from_user_id=d.from_user_id,
        to_user_id=d.to_user_id,
        permission_key=d.permission_key,
        scope=d.scope,
        granted_at=d.granted_at,
        expires_at=d.expires_at,
        revoked_at=d.revoked_at,
        active=d.active,
    )


@router.post("", response_model=DelegationOut, status_code=status.HTTP_201_CREATED)
async def create_delegation(
    body: DelegationIn,
    ctx: AuthContext = Depends(require("permissions.manage")),
    session: AsyncSession = Depends(db_session),
) -> DelegationOut:
    try:
        view = await DelegationService(session).delegate(
            from_user_id=ctx.user_id,
            to_user_id=body.to_user_id,
            permission_key=body.permission_key,
            expires_at=body.expires_at,
            scope=body.scope,
            actor_id=ctx.user_id,
        )
    except PermissionKeyError as exc:
        raise ValidationError(f"unknown permission: {body.permission_key}") from exc
    except NotDelegatorsToGive as exc:
        raise ValidationError(f"you do not hold '{body.permission_key}'") from exc
    except DelegationError as exc:
        raise ValidationError(str(exc)) from exc
    return _out(view)


@router.get("", response_model=DelegationsResponse)
async def list_delegations(
    active_only: bool = False,
    ctx: AuthContext = Depends(require("permissions.manage")),
    session: AsyncSession = Depends(db_session),
) -> DelegationsResponse:
    rows = await DelegationService(session).list_involving(ctx.user_id, active_only=active_only)
    return DelegationsResponse(delegations=[_out(r) for r in rows])


@router.delete("/{delegation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_delegation(
    delegation_id: uuid.UUID,
    ctx: AuthContext = Depends(require("permissions.manage")),
    session: AsyncSession = Depends(db_session),
) -> None:
    try:
        await DelegationService(session).revoke(delegation_id, actor_id=ctx.user_id)
    except DelegationNotFound as exc:
        raise NotFoundError("delegation not found") from exc
