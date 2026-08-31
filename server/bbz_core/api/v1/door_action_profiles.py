"""Door-open DTMF profiles admin API (roadmap E17-02).

The plaintext DTMF code enters exactly here, in a POST / PATCH body over TLS; it
is encrypted immediately and is **never** returned, logged or audited
(MASTER_PROMPT §30, .ai/SECURITY.md — audit the profile id, not the code). Every
route needs ``door.configure``. Per-route CSRF is applied centrally in E23.
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.api.errors import NotFoundError, ServiceUnavailableError, ValidationError
from bbz_core.infra.door_secrets import DoorSecretsNotConfigured
from bbz_core.infra.repositories.door_action_profiles import (
    DoorActionProfileService,
    DoorProfileNotFoundError,
    InvalidDoorProfileError,
    ProfileView,
)

router = APIRouter(prefix="/door-action-profiles", tags=["door-action-profiles"])

_DTMF = r"^[0-9A-Da-d*#]{1,32}$"


@contextlib.contextmanager
def _translate() -> Iterator[None]:
    try:
        yield
    except DoorProfileNotFoundError as exc:
        raise NotFoundError("door action profile not found") from exc
    except InvalidDoorProfileError as exc:
        raise ValidationError(str(exc)) from exc
    except DoorSecretsNotConfigured as exc:
        raise ServiceUnavailableError("door DTMF encryption is not configured") from exc


class ProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    dtmf_code: str = Field(pattern=_DTMF)
    post_dtmf_delay_ms: int = Field(default=500, ge=0, le=10000)
    auto_hangup: bool = True


class ProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    dtmf_code: str | None = Field(default=None, pattern=_DTMF)
    post_dtmf_delay_ms: int | None = Field(default=None, ge=0, le=10000)
    auto_hangup: bool | None = None


class ProfileOut(BaseModel):
    id: uuid.UUID
    name: str
    post_dtmf_delay_ms: int
    auto_hangup: bool
    #: whether a DTMF code is stored — never the code itself
    configured: bool
    created_by: uuid.UUID | None
    created_at: _dt.datetime
    updated_at: _dt.datetime


def _out(v: ProfileView) -> ProfileOut:
    return ProfileOut(
        id=v.id,
        name=v.name,
        post_dtmf_delay_ms=v.post_dtmf_delay_ms,
        auto_hangup=v.auto_hangup,
        configured=v.configured,
        created_by=v.created_by,
        created_at=v.created_at,
        updated_at=v.updated_at,
    )


def _svc(session: AsyncSession = Depends(db_session)) -> DoorActionProfileService:
    return DoorActionProfileService(session)


@router.get("", response_model=list[ProfileOut])
async def list_profiles(
    _: AuthContext = Depends(require("door.configure")),
    svc: DoorActionProfileService = Depends(_svc),
) -> list[ProfileOut]:
    return [_out(v) for v in await svc.list_views()]


@router.post("", response_model=ProfileOut, status_code=status.HTTP_201_CREATED)
async def create_profile(
    body: ProfileIn,
    ctx: AuthContext = Depends(require("door.configure")),
    svc: DoorActionProfileService = Depends(_svc),
) -> ProfileOut:
    with _translate():
        return _out(
            await svc.create(
                name=body.name,
                dtmf_code=body.dtmf_code,
                post_dtmf_delay_ms=body.post_dtmf_delay_ms,
                auto_hangup=body.auto_hangup,
                actor_id=ctx.user_id,
            )
        )


@router.get("/{profile_id}", response_model=ProfileOut)
async def get_profile(
    profile_id: uuid.UUID,
    _: AuthContext = Depends(require("door.configure")),
    svc: DoorActionProfileService = Depends(_svc),
) -> ProfileOut:
    with _translate():
        return _out(await svc.get(profile_id))


@router.patch("/{profile_id}", response_model=ProfileOut)
async def update_profile(
    profile_id: uuid.UUID,
    body: ProfilePatch,
    ctx: AuthContext = Depends(require("door.configure")),
    svc: DoorActionProfileService = Depends(_svc),
) -> ProfileOut:
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise ValidationError("no fields to update")
    with _translate():
        return _out(await svc.update(profile_id, changes, actor_id=ctx.user_id))


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    profile_id: uuid.UUID,
    ctx: AuthContext = Depends(require("door.configure")),
    svc: DoorActionProfileService = Depends(_svc),
) -> None:
    with _translate():
        await svc.delete(profile_id, actor_id=ctx.user_id)
