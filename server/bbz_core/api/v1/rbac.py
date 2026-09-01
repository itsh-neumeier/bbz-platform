"""RBAC administration API (E02-09).

Roles/permissions/groups are data — administrators manage them here and the
change is effective on the next request (the permission service reads the DB
per request, both nodes). Guarded by ``roles.manage`` / ``permissions.manage``.

TODO(E04-03 / #66): emit ROLE_CREATED / ROLE_PERMISSION_CHANGED /
USER_ROLE_ASSIGNED etc. audit events once the audit-write service exists.
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import uuid
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require, require_stepup
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.api.errors import ConflictError, NotFoundError, ValidationError
from bbz_core.authorization import SCOPES
from bbz_core.infra.repositories.rbac_admin import (
    LastAdminError,
    PermissionAssignment,
    RbacAdminError,
    RbacAdminRepository,
)

router = APIRouter(tags=["rbac"])


@contextlib.contextmanager
def _translate() -> Iterator[None]:
    try:
        yield
    except LastAdminError as exc:
        raise ConflictError(str(exc)) from exc
    except RbacAdminError as exc:
        raise ValidationError(str(exc)) from exc


class RoleIn(BaseModel):
    key: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=120)


class RoleRename(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class RoleOut(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    builtin: bool


class PermAssignmentIn(BaseModel):
    permission_key: str
    scope: str = "global"
    condition: dict[str, Any] | None = None


class RoleRef(BaseModel):
    role_id: uuid.UUID
    #: optional validity window for this assignment (E21-07)
    valid_from: _dt.datetime | None = None
    valid_to: _dt.datetime | None = None


class GroupIn(BaseModel):
    key: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=120)


class GroupOut(BaseModel):
    id: uuid.UUID
    key: str
    name: str


def _repo(session: AsyncSession = Depends(db_session)) -> RbacAdminRepository:
    return RbacAdminRepository(session)


# --- roles ---------------------------------------------------------------


@router.get("/roles", response_model=list[RoleOut])
async def list_roles(
    _: AuthContext = Depends(require("roles.view")),
    repo: RbacAdminRepository = Depends(_repo),
) -> list[RoleOut]:
    return [RoleOut.model_validate(r, from_attributes=True) for r in await repo.list_roles()]


@router.post("/roles", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
async def create_role(
    body: RoleIn,
    _: AuthContext = Depends(require("roles.manage")),
    repo: RbacAdminRepository = Depends(_repo),
) -> RoleOut:
    role = await repo.create_role(body.key, body.name)
    return RoleOut.model_validate(role, from_attributes=True)


@router.patch("/roles/{role_id}", response_model=RoleOut)
async def rename_role(
    role_id: uuid.UUID,
    body: RoleRename,
    _: AuthContext = Depends(require("roles.manage")),
    repo: RbacAdminRepository = Depends(_repo),
) -> RoleOut:
    role = await repo.get_role(role_id)
    if role is None:
        raise NotFoundError("role not found")
    return RoleOut.model_validate(await repo.rename_role(role, body.name), from_attributes=True)


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: uuid.UUID,
    _: AuthContext = Depends(require("roles.manage")),
    repo: RbacAdminRepository = Depends(_repo),
) -> None:
    role = await repo.get_role(role_id)
    if role is None:
        raise NotFoundError("role not found")
    with _translate():
        await repo.delete_role(role)


@router.get("/roles/{role_id}/permissions", response_model=list[PermAssignmentIn])
async def get_role_permissions(
    role_id: uuid.UUID,
    _: AuthContext = Depends(require("roles.view")),
    repo: RbacAdminRepository = Depends(_repo),
) -> list[PermAssignmentIn]:
    return [
        PermAssignmentIn(permission_key=a.permission_key, scope=a.scope, condition=a.condition)
        for a in await repo.get_role_permissions(role_id)
    ]


@router.put("/roles/{role_id}/permissions", status_code=status.HTTP_204_NO_CONTENT)
async def set_role_permissions(
    role_id: uuid.UUID,
    body: list[PermAssignmentIn],
    _: AuthContext = Depends(require_stepup("permissions.manage")),
    repo: RbacAdminRepository = Depends(_repo),
) -> None:
    role = await repo.get_role(role_id)
    if role is None:
        raise NotFoundError("role not found")
    bad_scopes = {a.scope for a in body} - SCOPES
    if bad_scopes:
        raise ValidationError(f"unknown scopes: {sorted(bad_scopes)}")
    with _translate():
        await repo.set_role_permissions(
            role,
            [PermissionAssignment(a.permission_key, a.scope, a.condition) for a in body],
        )


# --- assignments -----------------------------------------------------


@router.post("/users/{user_id}/roles", status_code=status.HTTP_204_NO_CONTENT)
async def assign_user_role(
    user_id: uuid.UUID,
    body: RoleRef,
    ctx: AuthContext = Depends(require("roles.manage")),
    repo: RbacAdminRepository = Depends(_repo),
) -> None:
    with _translate():
        await repo.assign_user_role(
            user_id,
            body.role_id,
            granted_by=ctx.user_id,
            valid_from=body.valid_from,
            valid_to=body.valid_to,
        )


@router.delete("/users/{user_id}/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_user_role(
    user_id: uuid.UUID,
    role_id: uuid.UUID,
    _: AuthContext = Depends(require("roles.manage")),
    repo: RbacAdminRepository = Depends(_repo),
) -> None:
    with _translate():
        await repo.revoke_user_role(user_id, role_id)


# --- groups ---------------------------------------------------------


@router.get("/groups", response_model=list[GroupOut])
async def list_groups(
    _: AuthContext = Depends(require("roles.view")),
    repo: RbacAdminRepository = Depends(_repo),
) -> list[GroupOut]:
    return [GroupOut.model_validate(g, from_attributes=True) for g in await repo.list_groups()]


@router.post("/groups", response_model=GroupOut, status_code=status.HTTP_201_CREATED)
async def create_group(
    body: GroupIn,
    _: AuthContext = Depends(require("roles.manage")),
    repo: RbacAdminRepository = Depends(_repo),
) -> GroupOut:
    return GroupOut.model_validate(
        await repo.create_group(body.key, body.name), from_attributes=True
    )


@router.post("/groups/{group_id}/roles", status_code=status.HTTP_204_NO_CONTENT)
async def assign_group_role(
    group_id: uuid.UUID,
    body: RoleRef,
    _: AuthContext = Depends(require("roles.manage")),
    repo: RbacAdminRepository = Depends(_repo),
) -> None:
    await repo.assign_group_role(group_id, body.role_id)


@router.delete("/groups/{group_id}/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_group_role(
    group_id: uuid.UUID,
    role_id: uuid.UUID,
    _: AuthContext = Depends(require("roles.manage")),
    repo: RbacAdminRepository = Depends(_repo),
) -> None:
    with _translate():
        await repo.revoke_group_role(group_id, role_id)
