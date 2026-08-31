"""Per-alarm-source admin API (roadmap E16-06).

Configure a Coda (or any) external alarm source in one place: the BBZ technical
endpoint it maps to, its site, BBZ priority, popup / EPK / escalation profile,
its cameras and the enabled flag (MASTER_PROMPT §36). A facade over the
technical-endpoint (E15-10) and camera-mapping (E16-05) stores.

Highly privileged — this defines automatic critical-event creation, so a write
needs **both** ``technical_endpoints.manage`` and ``integrations.configure`` and
is audited (``CODA_ALARM_SOURCE_*``). Per-route CSRF is applied centrally in E23.
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.api.errors import NotFoundError, ValidationError
from bbz_core.infra.repositories.coda_alarm_sources import (
    AlarmSourceConfigService,
    AlarmSourceInput,
    AlarmSourceNotFoundError,
    AlarmSourceView,
    InvalidAlarmSourceError,
)

router = APIRouter(prefix="/coda-alarm-sources", tags=["coda-alarm-sources"])

_TYPES = ("video_alarm", "panic_button", "bma", "custom")
_PRIORITIES = ("critical", "high", "medium", "low")


@contextlib.contextmanager
def _translate() -> Iterator[None]:
    try:
        yield
    except AlarmSourceNotFoundError as exc:
        raise NotFoundError("alarm source not configured") from exc
    except InvalidAlarmSourceError as exc:
        raise ValidationError(str(exc)) from exc


class AlarmSourceConfigIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    endpoint_name: str = Field(min_length=1, max_length=200)
    endpoint_type: str = Field(default="video_alarm", pattern="^(" + "|".join(_TYPES) + ")$")
    site: str | None = Field(default=None, max_length=200)
    priority: str | None = Field(default=None, pattern="^(" + "|".join(_PRIORITIES) + ")$")
    camera_refs: list[str] = Field(default_factory=list, max_length=50)
    popup_profile: str | None = Field(default=None, max_length=64)
    workflow_selection_policy: dict[str, object] | None = None
    escalation_profile: str | None = Field(default=None, max_length=64)
    enabled: bool = True
    provider_instance_id: str | None = Field(default=None, max_length=64)


class AlarmSourceOut(BaseModel):
    external_source_id: str
    endpoint_id: uuid.UUID
    endpoint_name: str
    endpoint_type: str
    site: str | None
    priority: str | None
    camera_refs: list[str]
    popup_profile: str | None
    escalation_profile: str | None
    workflow_selection_policy: dict[str, object] | None
    enabled: bool
    active_config_version: int
    updated_at: _dt.datetime


def _out(view: AlarmSourceView) -> AlarmSourceOut:
    e = view.endpoint
    return AlarmSourceOut(
        external_source_id=view.external_source_id,
        endpoint_id=e.id,
        endpoint_name=e.name,
        endpoint_type=e.type,
        site=e.site,
        priority=e.default_priority,
        camera_refs=list(view.camera_refs),
        popup_profile=e.popup_profile,
        escalation_profile=e.escalation_profile,
        workflow_selection_policy=e.workflow_selection_policy,
        enabled=e.enabled,
        active_config_version=e.active_config_version,
        updated_at=e.updated_at,
    )


def _svc(session: AsyncSession = Depends(db_session)) -> AlarmSourceConfigService:
    return AlarmSourceConfigService(session)


@router.get("", response_model=list[AlarmSourceOut])
async def list_alarm_sources(
    _: AuthContext = Depends(require("technical_endpoints.view")),
    svc: AlarmSourceConfigService = Depends(_svc),
) -> list[AlarmSourceOut]:
    return [_out(v) for v in await svc.list_sources()]


@router.get("/{external_source_id}", response_model=AlarmSourceOut)
async def get_alarm_source(
    external_source_id: str,
    _: AuthContext = Depends(require("technical_endpoints.view")),
    svc: AlarmSourceConfigService = Depends(_svc),
) -> AlarmSourceOut:
    with _translate():
        return _out(await svc.get(external_source_id))


@router.put("/{external_source_id}", response_model=AlarmSourceOut)
async def configure_alarm_source(
    external_source_id: str,
    body: AlarmSourceConfigIn,
    ctx: AuthContext = Depends(require("technical_endpoints.manage")),
    _: AuthContext = Depends(require("integrations.configure")),
    svc: AlarmSourceConfigService = Depends(_svc),
) -> AlarmSourceOut:
    with _translate():
        view = await svc.configure(
            external_source_id,
            AlarmSourceInput(
                endpoint_name=body.endpoint_name,
                endpoint_type=body.endpoint_type,
                site=body.site,
                priority=body.priority,
                camera_refs=list(body.camera_refs),
                popup_profile=body.popup_profile,
                workflow_selection_policy=body.workflow_selection_policy,
                escalation_profile=body.escalation_profile,
                enabled=body.enabled,
                provider_instance_id=body.provider_instance_id,
            ),
            actor_id=ctx.user_id,
        )
    return _out(view)


@router.delete("/{external_source_id}", status_code=204)
async def remove_alarm_source(
    external_source_id: str,
    ctx: AuthContext = Depends(require("technical_endpoints.manage")),
    _: AuthContext = Depends(require("integrations.configure")),
    svc: AlarmSourceConfigService = Depends(_svc),
) -> None:
    with _translate():
        await svc.remove(external_source_id, actor_id=ctx.user_id)
