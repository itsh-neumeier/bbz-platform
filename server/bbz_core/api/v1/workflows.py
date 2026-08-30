"""Workflow template + version lifecycle API (roadmap E05-07).

``draft -> validated -> published -> deprecated``. Publishing needs a prior
``validate`` and a changelog; editing anything but a draft is refused (409 —
"create a new draft version"). Every transition is audited.

Per-route CSRF is applied centrally in E23, as with the other admin routers.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.api.errors import ConflictError, NotFoundError, ValidationError
from bbz_core.infra.models.events import Event
from bbz_core.infra.models.workflow import WorkflowTemplate, WorkflowTemplateVersion
from bbz_core.infra.repositories.workflow_engine import (
    NoPublishedVersionError,
    TemplateNotFoundError,
    WorkflowEngineService,
)
from bbz_core.infra.repositories.workflow_lifecycle import (
    ChangelogRequiredError,
    InvalidTransitionError,
    NotValidatedError,
    VersionNotFoundError,
    WorkflowLifecycleService,
)

router = APIRouter(tags=["workflows"])


@contextlib.contextmanager
def _translate() -> Iterator[None]:
    try:
        yield
    except VersionNotFoundError as exc:
        raise NotFoundError("workflow template version not found") from exc
    except NotValidatedError as exc:
        raise ConflictError(str(exc)) from exc
    except InvalidTransitionError as exc:
        raise ConflictError(str(exc)) from exc
    except ChangelogRequiredError as exc:
        raise ValidationError(str(exc)) from exc
    except DBAPIError as exc:
        if "published definition is immutable" in str(exc):
            raise ConflictError(
                "this version is published; create a new draft version to change it"
            ) from exc
        raise


class TemplateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)


class TemplateOut(BaseModel):
    id: uuid.UUID
    key: str
    name: str


class VersionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    definition: dict[str, object]
    changelog: str | None = Field(default=None, max_length=4000)


class EditVersionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    definition: dict[str, object]


class PublishIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    changelog: str = Field(min_length=1, max_length=4000)


class VersionOut(BaseModel):
    id: uuid.UUID
    template_id: uuid.UUID
    version_no: int
    lifecycle: str
    definition: dict[str, object]
    changelog: str | None


class ValidateOut(BaseModel):
    valid: bool
    lifecycle: str
    issues: list[dict[str, str | None]]


def _version_out(v: WorkflowTemplateVersion) -> VersionOut:
    return VersionOut.model_validate(v, from_attributes=True)


def _svc(session: AsyncSession = Depends(db_session)) -> WorkflowLifecycleService:
    return WorkflowLifecycleService(session)


# -- templates -----------------------------------------------------------------


@router.get("/workflow-templates", response_model=list[TemplateOut])
async def list_templates(
    _: AuthContext = Depends(require("workflows.view")),
    session: AsyncSession = Depends(db_session),
) -> list[TemplateOut]:
    rows = (
        (await session.execute(select(WorkflowTemplate).order_by(WorkflowTemplate.key)))
        .scalars()
        .all()
    )
    return [TemplateOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/workflow-templates", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
async def create_template(
    body: TemplateIn,
    ctx: AuthContext = Depends(require("workflows.manage_templates")),
    session: AsyncSession = Depends(db_session),
) -> TemplateOut:
    tpl = WorkflowTemplate(key=body.key, name=body.name, owner_id=ctx.user_id)
    session.add(tpl)
    try:
        await session.commit()
    except DBAPIError as exc:  # unique key
        raise ConflictError(f"template key {body.key!r} already exists") from exc
    return TemplateOut.model_validate(tpl, from_attributes=True)


@router.post(
    "/workflow-templates/{template_id}/versions",
    response_model=VersionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_version(
    template_id: uuid.UUID,
    body: VersionIn,
    _: AuthContext = Depends(require("workflows.manage_templates")),
    svc: WorkflowLifecycleService = Depends(_svc),
    session: AsyncSession = Depends(db_session),
) -> VersionOut:
    if await session.get(WorkflowTemplate, template_id) is None:
        raise NotFoundError("workflow template not found")
    v = await svc.create_draft_version(
        template_id, definition=body.definition, changelog=body.changelog
    )
    return _version_out(v)


# -- versions ----------------------------------------------------------------


@router.get("/workflow-template-versions/{version_id}", response_model=VersionOut)
async def get_version(
    version_id: uuid.UUID,
    _: AuthContext = Depends(require("workflows.view")),
    session: AsyncSession = Depends(db_session),
) -> VersionOut:
    v = await session.get(WorkflowTemplateVersion, version_id)
    if v is None:
        raise NotFoundError("workflow template version not found")
    return _version_out(v)


@router.patch("/workflow-template-versions/{version_id}", response_model=VersionOut)
async def edit_version(
    version_id: uuid.UUID,
    body: EditVersionIn,
    _: AuthContext = Depends(require("workflows.manage_templates")),
    svc: WorkflowLifecycleService = Depends(_svc),
    session: AsyncSession = Depends(db_session),
) -> VersionOut:
    with _translate():
        await svc.edit_draft(version_id, definition=body.definition)
    v = await session.get(WorkflowTemplateVersion, version_id)
    assert v is not None
    return _version_out(v)


@router.post("/workflow-template-versions/{version_id}/validate", response_model=ValidateOut)
async def validate_version(
    version_id: uuid.UUID,
    ctx: AuthContext = Depends(require("workflows.manage_templates")),
    svc: WorkflowLifecycleService = Depends(_svc),
    session: AsyncSession = Depends(db_session),
) -> ValidateOut:
    with _translate():
        issues = await svc.validate(version_id, actor_id=ctx.user_id)
    v = await session.get(WorkflowTemplateVersion, version_id)
    assert v is not None
    return ValidateOut(
        valid=not issues,
        lifecycle=v.lifecycle,
        issues=[{"code": i.code, "message": i.message, "node_key": i.node_key} for i in issues],
    )


@router.post("/workflow-template-versions/{version_id}/publish", response_model=VersionOut)
async def publish_version(
    version_id: uuid.UUID,
    body: PublishIn,
    ctx: AuthContext = Depends(require("workflows.manage_templates")),
    svc: WorkflowLifecycleService = Depends(_svc),
    session: AsyncSession = Depends(db_session),
) -> VersionOut:
    with _translate():
        v = await svc.publish(version_id, actor_id=ctx.user_id, changelog=body.changelog)
    return _version_out(v)


@router.post("/workflow-template-versions/{version_id}/deprecate", response_model=VersionOut)
async def deprecate_version(
    version_id: uuid.UUID,
    ctx: AuthContext = Depends(require("workflows.manage_templates")),
    svc: WorkflowLifecycleService = Depends(_svc),
    session: AsyncSession = Depends(db_session),
) -> VersionOut:
    with _translate():
        v = await svc.deprecate(version_id, actor_id=ctx.user_id)
    return _version_out(v)


# -- instance start (E05-11) --------------------------------------------------


class StartWorkflowIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template_key: str = Field(min_length=1, max_length=64)


class InstanceOut(BaseModel):
    instance_id: uuid.UUID
    event_id: uuid.UUID
    template_version_id: uuid.UUID
    status: str


@router.post(
    "/events/{event_id}/workflow",
    response_model=InstanceOut,
    status_code=status.HTTP_201_CREATED,
)
async def start_event_workflow(
    event_id: uuid.UUID,
    body: StartWorkflowIn,
    ctx: AuthContext = Depends(require("workflows.execute")),
    session: AsyncSession = Depends(db_session),
) -> InstanceOut:
    """Pin a new workflow instance to this event and the template's current
    PUBLISHED version. Idempotent, and immune to later publishes (ADR-0005)."""
    if await session.get(Event, event_id) is None:
        raise NotFoundError("event not found")
    try:
        inst = await WorkflowEngineService(session).start_for_event(
            event_id, body.template_key, actor_id=ctx.user_id
        )
    except TemplateNotFoundError as exc:
        raise NotFoundError(f"workflow template {body.template_key!r} not found") from exc
    except NoPublishedVersionError as exc:
        raise ConflictError(str(exc)) from exc
    return InstanceOut(
        instance_id=inst.id,
        event_id=inst.event_id,
        template_version_id=inst.template_version_id,
        status=inst.status,
    )
