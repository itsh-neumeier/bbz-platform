"""Technical-endpoint admin API (roadmap E15-10).

CRUD over configured technical signal sources — door stations, BMA, panic
buttons, video alarms, alarm dialers (MASTER_PROMPT §29). Highly privileged:
these drive automatic event creation and door opening, so reads need
``technical_endpoints.view`` and every write needs ``technical_endpoints.manage``
and is audited (``TECHNICAL_ENDPOINT_*``).

Per-route CSRF is applied centrally in E23, as with the other admin routers.
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
from bbz_core.api.errors import ForbiddenError, NotFoundError, ValidationError
from bbz_core.authorization import PermissionService
from bbz_core.infra.repositories.authorization import SqlAlchemyGrantStore
from bbz_core.infra.repositories.technical_endpoints import (
    EndpointInput,
    EndpointNotFoundError,
    EndpointView,
    InvalidEndpointError,
    NumberPattern,
    TechnicalEndpointService,
)

router = APIRouter(prefix="/technical-endpoints", tags=["technical-endpoints"])

_TYPES = ("door_station", "bma", "panic_button", "video_alarm", "alarm_dialer", "custom")
_PRIORITIES = ("critical", "high", "medium", "low")


@contextlib.contextmanager
def _translate() -> Iterator[None]:
    try:
        yield
    except EndpointNotFoundError as exc:
        raise NotFoundError("technical endpoint not found") from exc
    except InvalidEndpointError as exc:
        raise ValidationError(str(exc)) from exc


class NumberIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    calling_pattern: str | None = Field(default=None, max_length=64)
    called_pattern: str | None = Field(default=None, max_length=64)
    cti_route_point: str | None = Field(default=None, max_length=64)


class DoorStationFields(BaseModel):
    """Siedle door-station config (E17-01). ``dtmf_profile_id`` is an id only —
    ``extra="forbid"`` rejects any attempt to pass a raw code (§30, ADR-0004)."""

    dtmf_profile_id: uuid.UUID | None = None
    popup_text: str | None = Field(default=None, max_length=200)
    door_open_timeout_seconds: int | None = Field(default=None, ge=1, le=600)


class EndpointIn(DoorStationFields):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    type: str = Field(pattern="^(" + "|".join(_TYPES) + ")$")
    site: str | None = Field(default=None, max_length=200)
    provider_id: str | None = Field(default=None, max_length=64)
    external_source_ids: list[str] = Field(default_factory=list, max_length=100)
    default_priority: str | None = Field(default=None, pattern="^(" + "|".join(_PRIORITIES) + ")$")
    popup_profile: str | None = Field(default=None, max_length=64)
    escalation_profile: str | None = Field(default=None, max_length=64)
    workflow_selection_policy: dict[str, object] | None = None
    enabled: bool = True
    numbers: list[NumberIn] = Field(default_factory=list, max_length=50)


class EndpointPatch(DoorStationFields):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    type: str | None = Field(default=None, pattern="^(" + "|".join(_TYPES) + ")$")
    site: str | None = Field(default=None, max_length=200)
    provider_id: str | None = Field(default=None, max_length=64)
    external_source_ids: list[str] | None = Field(default=None, max_length=100)
    default_priority: str | None = Field(default=None, pattern="^(" + "|".join(_PRIORITIES) + ")$")
    popup_profile: str | None = Field(default=None, max_length=64)
    escalation_profile: str | None = Field(default=None, max_length=64)
    workflow_selection_policy: dict[str, object] | None = None
    enabled: bool | None = None
    numbers: list[NumberIn] | None = None


class NumberOut(BaseModel):
    id: uuid.UUID
    calling_pattern: str | None
    called_pattern: str | None
    cti_route_point: str | None


class EndpointOut(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    site: str | None
    provider_id: str | None
    external_source_ids: list[str]
    default_priority: str | None
    popup_profile: str | None
    escalation_profile: str | None
    workflow_selection_policy: dict[str, object] | None
    enabled: bool
    active_config_version: int
    dtmf_profile_id: uuid.UUID | None
    popup_text: str | None
    door_open_timeout_seconds: int | None
    created_at: _dt.datetime
    updated_at: _dt.datetime
    numbers: list[NumberOut]


def _out(view: EndpointView) -> EndpointOut:
    e = view.endpoint
    return EndpointOut(
        id=e.id,
        name=e.name,
        type=e.type,
        site=e.site,
        provider_id=e.provider_id,
        external_source_ids=list(e.external_source_ids or []),
        default_priority=e.default_priority,
        popup_profile=e.popup_profile,
        escalation_profile=e.escalation_profile,
        workflow_selection_policy=e.workflow_selection_policy,
        enabled=e.enabled,
        active_config_version=e.active_config_version,
        dtmf_profile_id=e.dtmf_profile_id,
        popup_text=e.popup_text,
        door_open_timeout_seconds=e.door_open_timeout_seconds,
        created_at=e.created_at,
        updated_at=e.updated_at,
        numbers=[
            NumberOut(
                id=n.id,
                calling_pattern=n.calling_pattern,
                called_pattern=n.called_pattern,
                cti_route_point=n.cti_route_point,
            )
            for n in view.numbers
        ],
    )


def _patterns(numbers: list[NumberIn]) -> list[NumberPattern]:
    return [
        NumberPattern(
            calling_pattern=n.calling_pattern,
            called_pattern=n.called_pattern,
            cti_route_point=n.cti_route_point,
        )
        for n in numbers
    ]


def _svc(session: AsyncSession = Depends(db_session)) -> TechnicalEndpointService:
    return TechnicalEndpointService(session)


#: door-station-only fields — touching any of these (or the ``door_station`` type)
#: additionally needs ``door.configure`` (E17-01; MASTER_PROMPT §30).
_DOOR_FIELDS = ("dtmf_profile_id", "popup_text", "door_open_timeout_seconds")


async def _guard_door_config(
    session: AsyncSession, ctx: AuthContext, body: EndpointIn | EndpointPatch
) -> None:
    set_fields = body.model_fields_set
    touches_door = body.type == "door_station" or any(f in set_fields for f in _DOOR_FIELDS)
    if not touches_door:
        return
    allowed = await PermissionService(SqlAlchemyGrantStore(session)).authorize(
        ctx.user_id, "door.configure"
    )
    if not allowed:
        raise ForbiddenError("missing permission: door.configure")


@router.get("", response_model=list[EndpointOut])
async def list_endpoints(
    _: AuthContext = Depends(require("technical_endpoints.view")),
    svc: TechnicalEndpointService = Depends(_svc),
) -> list[EndpointOut]:
    return [_out(v) for v in await svc.list_views()]


@router.post("", response_model=EndpointOut, status_code=status.HTTP_201_CREATED)
async def create_endpoint(
    body: EndpointIn,
    ctx: AuthContext = Depends(require("technical_endpoints.manage")),
    session: AsyncSession = Depends(db_session),
    svc: TechnicalEndpointService = Depends(_svc),
) -> EndpointOut:
    await _guard_door_config(session, ctx, body)
    with _translate():
        view = await svc.create(
            EndpointInput(
                name=body.name,
                type=body.type,
                site=body.site,
                provider_id=body.provider_id,
                external_source_ids=list(body.external_source_ids),
                default_priority=body.default_priority,
                popup_profile=body.popup_profile,
                escalation_profile=body.escalation_profile,
                workflow_selection_policy=body.workflow_selection_policy,
                enabled=body.enabled,
                numbers=_patterns(body.numbers),
                dtmf_profile_id=body.dtmf_profile_id,
                popup_text=body.popup_text,
                door_open_timeout_seconds=body.door_open_timeout_seconds,
            ),
            actor_id=ctx.user_id,
        )
    return _out(view)


@router.get("/{endpoint_id}", response_model=EndpointOut)
async def get_endpoint(
    endpoint_id: uuid.UUID,
    _: AuthContext = Depends(require("technical_endpoints.view")),
    svc: TechnicalEndpointService = Depends(_svc),
) -> EndpointOut:
    with _translate():
        return _out(await svc.get(endpoint_id))


@router.patch("/{endpoint_id}", response_model=EndpointOut)
async def update_endpoint(
    endpoint_id: uuid.UUID,
    body: EndpointPatch,
    ctx: AuthContext = Depends(require("technical_endpoints.manage")),
    session: AsyncSession = Depends(db_session),
    svc: TechnicalEndpointService = Depends(_svc),
) -> EndpointOut:
    await _guard_door_config(session, ctx, body)
    fields = body.model_dump(exclude_unset=True)
    fields.pop("numbers", None)
    numbers_set = "numbers" in body.model_fields_set
    if not fields and not numbers_set:
        raise ValidationError("no fields to update")
    with _translate():
        view = await svc.update(
            endpoint_id,
            fields,
            numbers=_patterns(body.numbers) if numbers_set and body.numbers is not None else None,
            actor_id=ctx.user_id,
        )
    return _out(view)


@router.delete("/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_endpoint(
    endpoint_id: uuid.UUID,
    ctx: AuthContext = Depends(require("technical_endpoints.manage")),
    svc: TechnicalEndpointService = Depends(_svc),
) -> None:
    with _translate():
        await svc.delete(endpoint_id, actor_id=ctx.user_id)
