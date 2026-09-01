"""Monitor / KVM routing API (roadmap E19-04, MASTER_PROMPT §9).

* ``GET  /api/v1/monitor/routes`` — the current route per output + the input /
  output catalog + provider health (``monitor.view``).
* ``PUT  /api/v1/monitor/routes`` — set one or more routes as a batch, idempotent
  on ``X-Command-Id`` (``monitor.route``).
* ``POST /api/v1/monitor/routes/reset-standard`` — restore the standard layout,
  idempotent (``monitor.reset_standard``).

Every applied change is a ``MONITOR_ROUTE_CHANGED`` audit row. The fixed
"lower-left is always BBZ-OS" rule (E19-03) is enforced server-side: a request
that reassigns that output is rejected with 422.
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import uuid
from collections.abc import Iterator
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.api.errors import (
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)
from bbz_core.api.idempotency import CommandEnvelope, command_envelope
from bbz_core.domain.monitor import INPUTS, OUTPUTS, MonitorDomainError
from bbz_core.infra.idempotency import CommandConflictError, CommandInProgressError
from bbz_core.infra.repositories.monitor_profiles import (
    MonitorProfileNameConflict,
    MonitorProfileNotFoundError,
    MonitorProfileService,
    ProfileView,
)
from bbz_core.infra.repositories.monitor_routing import (
    MonitorProviderError,
    MonitorRoutingService,
    MonitorState,
)
from bbz_core.integrations_host.providers import NoActiveProvider

router = APIRouter(prefix="/monitor", tags=["monitor"])


class InputOut(BaseModel):
    key: str
    label: str


class OutputOut(BaseModel):
    key: str
    label: str
    grid_row: int | None
    grid_col: int | None
    is_large_display: bool
    is_fixed: bool


class RouteOut(BaseModel):
    output_key: str
    input_key: str | None
    is_fixed: bool
    set_at: _dt.datetime | None


class MonitorStateOut(BaseModel):
    inputs: list[InputOut]
    outputs: list[OutputOut]
    routes: list[RouteOut]
    provider_available: bool
    provider_healthy: bool


class SetRoutesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    #: output key -> input key; a partial batch is fine
    assignments: dict[str, str] = Field(min_length=1)


class ProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    scope: Literal["user", "workplace"]
    layout: dict[str, str] = Field(min_length=1)
    #: required for a ``workplace`` profile
    workplace_id: uuid.UUID | None = None


class ProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    layout: dict[str, str] | None = None


class ProfileOut(BaseModel):
    id: uuid.UUID
    name: str
    scope: str
    workplace_id: uuid.UUID | None
    layout: dict[str, str]


class ProfilesResponse(BaseModel):
    profiles: list[ProfileOut]


@contextlib.contextmanager
def _translate() -> Iterator[None]:
    try:
        yield
    except CommandConflictError as exc:
        raise ConflictError("command id reused with a different body") from exc
    except CommandInProgressError as exc:
        raise ConflictError("an identical monitor command is still being processed") from exc
    except MonitorProfileNameConflict as exc:
        raise ConflictError(f"a profile named {exc} already exists in this scope") from exc
    except MonitorProfileNotFoundError as exc:
        raise NotFoundError("monitor profile not found") from exc
    except MonitorDomainError as exc:
        raise ValidationError(str(exc)) from exc
    except NoActiveProvider as exc:
        raise ServiceUnavailableError("no monitor routing integration is active") from exc
    except MonitorProviderError as exc:
        raise ServiceUnavailableError(str(exc)) from exc


def _profile_out(p: ProfileView) -> ProfileOut:
    return ProfileOut(
        id=p.id, name=p.name, scope=p.scope, workplace_id=p.workplace_id, layout=p.layout
    )


def _out(state: MonitorState) -> MonitorStateOut:
    fixed = {r.output_key for r in state.routes if r.is_fixed}
    return MonitorStateOut(
        inputs=[InputOut(key=i.key, label=i.label) for i in INPUTS],
        outputs=[
            OutputOut(
                key=o.key,
                label=o.label,
                grid_row=o.grid_row,
                grid_col=o.grid_col,
                is_large_display=o.is_large_display,
                is_fixed=o.key in fixed,
            )
            for o in OUTPUTS
        ],
        routes=[
            RouteOut(
                output_key=r.output_key,
                input_key=r.input_key,
                is_fixed=r.is_fixed,
                set_at=r.set_at,
            )
            for r in state.routes
        ],
        provider_available=state.provider_available,
        provider_healthy=state.provider_healthy,
    )


@router.get("/routes", response_model=MonitorStateOut)
async def get_routes(
    _: AuthContext = Depends(require("monitor.view")),
    session: AsyncSession = Depends(db_session),
) -> MonitorStateOut:
    return _out(await MonitorRoutingService(session).state())


@router.put("/routes", response_model=MonitorStateOut)
async def set_routes(
    body: SetRoutesIn,
    ctx: AuthContext = Depends(require("monitor.route")),
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> MonitorStateOut:
    with _translate():
        state = await MonitorRoutingService(session).set_routes(
            assignments=body.assignments,
            command_id=env.command_id,
            actor_id=ctx.user_id,
        )
    return _out(state)


@router.post(
    "/routes/reset-standard",
    response_model=MonitorStateOut,
    status_code=status.HTTP_200_OK,
)
async def reset_standard(
    ctx: AuthContext = Depends(require("monitor.reset_standard")),
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> MonitorStateOut:
    with _translate():
        state = await MonitorRoutingService(session).reset_to_standard(
            command_id=env.command_id,
            actor_id=ctx.user_id,
        )
    return _out(state)


# --- layout profiles (E19-05) -------------------------------------------


@router.get("/profiles", response_model=ProfilesResponse)
async def list_profiles(
    workplace_id: uuid.UUID | None = Query(default=None),
    ctx: AuthContext = Depends(require("monitor.view")),
    session: AsyncSession = Depends(db_session),
) -> ProfilesResponse:
    profiles = await MonitorProfileService(session).list_visible(
        user_id=ctx.user_id, workplace_id=workplace_id
    )
    return ProfilesResponse(profiles=[_profile_out(p) for p in profiles])


@router.post("/profiles", response_model=ProfileOut, status_code=status.HTTP_201_CREATED)
async def create_profile(
    body: ProfileIn,
    ctx: AuthContext = Depends(require("monitor.manage_profiles")),
    session: AsyncSession = Depends(db_session),
) -> ProfileOut:
    with _translate():
        p = await MonitorProfileService(session).create(
            name=body.name,
            scope=body.scope,
            layout=body.layout,
            user_id=ctx.user_id,
            workplace_id=body.workplace_id,
        )
    return _profile_out(p)


@router.put("/profiles/{profile_id}", response_model=ProfileOut)
async def update_profile(
    profile_id: uuid.UUID,
    body: ProfilePatch,
    workplace_id: uuid.UUID | None = Query(default=None),
    ctx: AuthContext = Depends(require("monitor.manage_profiles")),
    session: AsyncSession = Depends(db_session),
) -> ProfileOut:
    with _translate():
        p = await MonitorProfileService(session).update(
            profile_id=profile_id,
            user_id=ctx.user_id,
            workplace_id=workplace_id,
            name=body.name,
            layout=body.layout,
        )
    return _profile_out(p)


@router.delete("/profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    profile_id: uuid.UUID,
    workplace_id: uuid.UUID | None = Query(default=None),
    ctx: AuthContext = Depends(require("monitor.manage_profiles")),
    session: AsyncSession = Depends(db_session),
) -> Response:
    with _translate():
        await MonitorProfileService(session).delete(
            profile_id=profile_id, user_id=ctx.user_id, workplace_id=workplace_id
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/profiles/{profile_id}/apply", response_model=MonitorStateOut)
async def apply_profile(
    profile_id: uuid.UUID,
    workplace_id: uuid.UUID | None = Query(default=None),
    ctx: AuthContext = Depends(require("monitor.route")),
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> MonitorStateOut:
    with _translate():
        state = await MonitorProfileService(session).apply(
            profile_id=profile_id,
            command_id=env.command_id,
            user_id=ctx.user_id,
            workplace_id=workplace_id,
        )
    return _out(state)
