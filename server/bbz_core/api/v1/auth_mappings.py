"""Admin config for external identity-provider group → BBZ role mapping (E21-02).

``roles.manage`` only. Every write is a ``AUTH_MAPPING_CHANGED`` audit row. The
mappings take effect on each affected user's **next** external login.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.api.errors import ConflictError, NotFoundError, ValidationError
from bbz_core.infra.repositories.auth_group_mapping import (
    GroupMappingService,
    MappingNotFound,
    UnknownRoleKey,
)

router = APIRouter(prefix="/auth/group-mappings", tags=["auth"])


class MappingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = Field(min_length=1, max_length=64)
    external_group: str = Field(min_length=1, max_length=300)
    role_key: str = Field(min_length=1, max_length=64)


class MappingOut(BaseModel):
    id: uuid.UUID
    provider: str
    external_group: str
    role_key: str


class MappingsResponse(BaseModel):
    mappings: list[MappingOut]


@contextlib.contextmanager
def _translate() -> Iterator[None]:
    try:
        yield
    except UnknownRoleKey as exc:
        raise ValidationError(f"no such role: {exc}") from exc
    except MappingNotFound as exc:
        raise NotFoundError("group mapping not found") from exc
    except Exception as exc:  # a duplicate rule hits the unique constraint
        if type(exc).__name__ == "IntegrityError":
            raise ConflictError("that mapping already exists") from exc
        raise


@router.get("", response_model=MappingsResponse)
async def list_mappings(
    provider: str | None = Query(default=None, max_length=64),
    _: AuthContext = Depends(require("roles.manage")),
    session: AsyncSession = Depends(db_session),
) -> MappingsResponse:
    rows = await GroupMappingService(session).list_mappings(provider=provider)
    return MappingsResponse(
        mappings=[
            MappingOut(
                id=m.id, provider=m.provider, external_group=m.external_group, role_key=m.role_key
            )
            for m in rows
        ]
    )


@router.post("", response_model=MappingOut, status_code=status.HTTP_201_CREATED)
async def create_mapping(
    body: MappingIn,
    ctx: AuthContext = Depends(require("roles.manage")),
    session: AsyncSession = Depends(db_session),
) -> MappingOut:
    with _translate():
        m = await GroupMappingService(session).create(
            provider=body.provider,
            external_group=body.external_group,
            role_key=body.role_key,
            actor_id=ctx.user_id,
        )
    return MappingOut(
        id=m.id, provider=m.provider, external_group=m.external_group, role_key=m.role_key
    )


@router.delete("/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mapping(
    mapping_id: uuid.UUID,
    ctx: AuthContext = Depends(require("roles.manage")),
    session: AsyncSession = Depends(db_session),
) -> Response:
    with _translate():
        await GroupMappingService(session).delete_mapping(mapping_id, actor_id=ctx.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
