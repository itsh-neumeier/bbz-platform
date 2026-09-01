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
from collections.abc import Iterator

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.api.errors import ConflictError, ServiceUnavailableError, ValidationError
from bbz_core.api.idempotency import CommandEnvelope, command_envelope
from bbz_core.domain.monitor import INPUTS, OUTPUTS, MonitorDomainError
from bbz_core.infra.idempotency import CommandConflictError, CommandInProgressError
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


@contextlib.contextmanager
def _translate() -> Iterator[None]:
    try:
        yield
    except CommandConflictError as exc:
        raise ConflictError("command id reused with a different body") from exc
    except CommandInProgressError as exc:
        raise ConflictError("an identical monitor command is still being processed") from exc
    except MonitorDomainError as exc:
        raise ValidationError(str(exc)) from exc
    except NoActiveProvider as exc:
        raise ServiceUnavailableError("no monitor routing integration is active") from exc
    except MonitorProviderError as exc:
        raise ServiceUnavailableError(str(exc)) from exc


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
