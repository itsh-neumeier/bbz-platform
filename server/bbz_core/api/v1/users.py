"""User administration API (E02-10).

Local-account lifecycle. Deactivation and password reset revoke every live
session immediately (both nodes — the session registry is authoritative).
Guarded by ``users.view`` / ``users.manage``.

Deactivation audits ``USER_DEACTIVATED`` (E21-04). TODO(E04-03 / #66): also emit
USER_CREATED / USER_PASSWORD_RESET.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.api.errors import ConflictError, NotFoundError, ValidationError
from bbz_core.api.rate_limit import rate_limit_by_user
from bbz_core.api.schema import StrictModel
from bbz_core.auth.policy import PasswordPolicyError
from bbz_core.infra.repositories.users_admin import (
    LastAdminError,
    NewUser,
    UsernameTakenError,
    UsersAdminError,
    UsersAdminRepository,
)

router = APIRouter(prefix="/users", tags=["users"])


@contextlib.contextmanager
def _translate() -> Iterator[None]:
    try:
        yield
    except (LastAdminError, UsernameTakenError) as exc:
        raise ConflictError(str(exc)) from exc
    except (UsersAdminError, PasswordPolicyError) as exc:
        raise ValidationError(str(exc)) from exc


class UserOut(BaseModel):
    id: uuid.UUID
    display_name: str
    status: str
    external_ref: str | None


class CreateUserIn(StrictModel):
    display_name: str = Field(min_length=1, max_length=200)
    external_ref: str | None = Field(default=None, max_length=255)
    local_username: str | None = Field(default=None, min_length=3, max_length=255)
    initial_password: str | None = None


class UpdateUserIn(StrictModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    external_ref: str | None = Field(default=None, max_length=255)


class PasswordResetIn(StrictModel):
    new_password: str


class RevokedOut(BaseModel):
    sessions_revoked: int


def _repo(session: AsyncSession = Depends(db_session)) -> UsersAdminRepository:
    return UsersAdminRepository(session)


@router.get("", response_model=list[UserOut])
async def list_users(
    include_disabled: bool = True,
    _: AuthContext = Depends(require("users.view")),
    repo: UsersAdminRepository = Depends(_repo),
) -> list[UserOut]:
    users = await repo.list_users(include_disabled=include_disabled)
    return [UserOut.model_validate(u, from_attributes=True) for u in users]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserIn,
    _: AuthContext = Depends(require("users.manage")),
    repo: UsersAdminRepository = Depends(_repo),
) -> UserOut:
    if body.initial_password and not body.local_username:
        raise ValidationError("initial_password requires local_username")
    with _translate():
        user = await repo.create(
            NewUser(
                display_name=body.display_name,
                external_ref=body.external_ref,
                local_username=body.local_username,
                initial_password=body.initial_password,
            )
        )
    return UserOut.model_validate(user, from_attributes=True)


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: uuid.UUID,
    _: AuthContext = Depends(require("users.view")),
    repo: UsersAdminRepository = Depends(_repo),
) -> UserOut:
    user = await repo.get(user_id)
    if user is None:
        raise NotFoundError("user not found")
    return UserOut.model_validate(user, from_attributes=True)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID,
    body: UpdateUserIn,
    _: AuthContext = Depends(require("users.manage")),
    repo: UsersAdminRepository = Depends(_repo),
) -> UserOut:
    user = await repo.get(user_id)
    if user is None:
        raise NotFoundError("user not found")
    updated = await repo.update(
        user, display_name=body.display_name, external_ref=body.external_ref
    )
    return UserOut.model_validate(updated, from_attributes=True)


@router.post("/{user_id}/deactivate", response_model=RevokedOut)
async def deactivate_user(
    user_id: uuid.UUID,
    ctx: AuthContext = Depends(require("users.manage")),
    repo: UsersAdminRepository = Depends(_repo),
) -> RevokedOut:
    user = await repo.get(user_id)
    if user is None:
        raise NotFoundError("user not found")
    with _translate():
        revoked = await repo.set_active(user, active=False, actor_id=ctx.user_id)
    return RevokedOut(sessions_revoked=revoked)


@router.post("/{user_id}/activate", response_model=UserOut)
async def activate_user(
    user_id: uuid.UUID,
    _: AuthContext = Depends(require("users.manage")),
    repo: UsersAdminRepository = Depends(_repo),
) -> UserOut:
    user = await repo.get(user_id)
    if user is None:
        raise NotFoundError("user not found")
    await repo.set_active(user, active=True)
    return UserOut.model_validate(user, from_attributes=True)


@router.post(
    "/{user_id}/password-reset",
    response_model=RevokedOut,
    dependencies=[Depends(rate_limit_by_user("password_reset"))],
)
async def reset_password(
    user_id: uuid.UUID,
    body: PasswordResetIn,
    _: AuthContext = Depends(require("users.manage")),
    repo: UsersAdminRepository = Depends(_repo),
) -> RevokedOut:
    user = await repo.get(user_id)
    if user is None:
        raise NotFoundError("user not found")
    with _translate():
        revoked = await repo.reset_password(user, body.new_password)
    return RevokedOut(sessions_revoked=revoked)
