"""Trigger-rule admin API (roadmap E15-10, E15-11).

Rules + versions with a ``draft -> validated -> published -> retired``
lifecycle. Publishing needs a prior ``validate`` (conditions checked against the
typed ``TRIGGER_CONTEXT``, actions against the runnable action set); editing
anything but a draft is refused — a change is a new version. Every transition is
audited (``TRIGGER_RULE_*``).

``POST /trigger-rules/simulate`` (E15-11) dry-runs a synthetic signal against
the published rules: it reports the matching rules and the actions each would
run, with **no** real effect (no inbox row, no ``trigger_executions``, no
outbox, no event, no DTMF) — only a ``TRIGGER_SIMULATED`` audit row.

Highly privileged — a published rule can open a door automatically — so reads
need ``technical_endpoints.view`` and writes ``technical_endpoints.manage``.
Per-route CSRF is applied centrally in E23.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.api.errors import AppError, ConflictError, NotFoundError, ValidationError
from bbz_core.domain.triggers import InboundSignalRejected
from bbz_core.infra.models.trigger_rules import TriggerRule, TriggerRuleVersion
from bbz_core.infra.repositories.trigger_engine import SimulationReport, TriggerEngine
from bbz_core.infra.repositories.trigger_rules import (
    EndpointNotFoundError,
    InvalidRuleTransitionError,
    RuleHasPublishedVersionError,
    RuleInput,
    RuleNotFoundError,
    RuleNotValidatedError,
    RulePublishBlockedError,
    TriggerRuleAdminService,
    VersionNotFoundError,
)

router = APIRouter(tags=["trigger-rules"])


class _PublishBlockedError(AppError):
    code = "publish_blocked"
    http_status = status.HTTP_409_CONFLICT


@contextlib.contextmanager
def _translate() -> Iterator[None]:
    try:
        yield
    except RuleNotFoundError as exc:
        raise NotFoundError("trigger rule not found") from exc
    except VersionNotFoundError as exc:
        raise NotFoundError("trigger rule version not found") from exc
    except EndpointNotFoundError as exc:
        raise ValidationError("endpoint_id does not reference a technical endpoint") from exc
    except RuleNotValidatedError as exc:
        raise ConflictError(str(exc)) from exc
    except RuleHasPublishedVersionError as exc:
        raise ConflictError("retire the published version before deleting this rule") from exc
    except InvalidRuleTransitionError as exc:
        raise ConflictError(str(exc)) from exc
    except RulePublishBlockedError as exc:
        raise _PublishBlockedError(
            "this version cannot be published", details={"issues": exc.issues}
        ) from exc
    except DBAPIError as exc:
        if "a published version is immutable" in str(exc):
            raise ConflictError(
                "this version is published; add a new version to change it"
            ) from exc
        raise


class RuleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    priority: int = Field(default=100, ge=0, le=100_000)
    endpoint_id: uuid.UUID | None = None
    conditions: dict[str, object] = Field(default_factory=dict)
    actions: list[dict[str, object]] = Field(default_factory=list, max_length=50)
    changelog: str | None = Field(default=None, max_length=4000)


class RulePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    priority: int | None = Field(default=None, ge=0, le=100_000)
    endpoint_id: uuid.UUID | None = None


class VersionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conditions: dict[str, object] = Field(default_factory=dict)
    actions: list[dict[str, object]] = Field(default_factory=list, max_length=50)
    changelog: str | None = Field(default=None, max_length=4000)


class PublishIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    changelog: str | None = Field(default=None, max_length=4000)


class VersionOut(BaseModel):
    id: uuid.UUID
    rule_id: uuid.UUID
    version_no: int
    lifecycle: str
    conditions: dict[str, object]
    actions: list[object]
    changelog: str | None


class RuleOut(BaseModel):
    id: uuid.UUID
    name: str
    priority: int
    endpoint_id: uuid.UUID | None
    lifecycle: str


class RuleDetailOut(RuleOut):
    versions: list[VersionOut]


class ValidateOut(BaseModel):
    valid: bool
    lifecycle: str
    issues: list[str]


class SimulateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    #: a synthetic ``inbound_signal.v1`` object — validated by the engine
    signal: dict[str, object]


class SimulatedRuleOut(BaseModel):
    rule_id: uuid.UUID
    rule_name: str
    priority: int
    version_id: uuid.UUID
    version_no: int
    actions: list[dict[str, object]]


class SimulationOut(BaseModel):
    signal_type: str
    executed: bool
    matched: list[SimulatedRuleOut]
    planned_action_count: int


def _rule_out(rule: TriggerRule) -> RuleOut:
    return RuleOut(
        id=rule.id,
        name=rule.name,
        priority=rule.priority,
        endpoint_id=rule.endpoint_id,
        lifecycle=rule.lifecycle,
    )


def _version_out(v: TriggerRuleVersion) -> VersionOut:
    return VersionOut(
        id=v.id,
        rule_id=v.rule_id,
        version_no=v.version_no,
        lifecycle=v.lifecycle,
        conditions=dict(v.conditions or {}),
        actions=list(v.actions or []),
        changelog=v.changelog,
    )


def _svc(session: AsyncSession = Depends(db_session)) -> TriggerRuleAdminService:
    return TriggerRuleAdminService(session)


def _simulation_out(report: SimulationReport) -> SimulationOut:
    return SimulationOut(
        signal_type=report.signal_type,
        executed=report.executed,
        planned_action_count=report.planned_action_count,
        matched=[
            SimulatedRuleOut(
                rule_id=r.rule_id,
                rule_name=r.rule_name,
                priority=r.priority,
                version_id=r.version_id,
                version_no=r.version_no,
                actions=r.actions,
            )
            for r in report.matched
        ],
    )


# -- simulation (E15-11) ----------------------------------------------------


@router.post("/trigger-rules/simulate", response_model=SimulationOut)
async def simulate(
    body: SimulateIn,
    ctx: AuthContext = Depends(require("technical_endpoints.manage")),
    session: AsyncSession = Depends(db_session),
) -> SimulationOut:
    """Dry-run a synthetic signal against the published rules — reports the
    matching rules and their planned actions, with no real effect at all."""
    try:
        report = await TriggerEngine(session).simulate(dict(body.signal), actor_id=ctx.user_id)
    except InboundSignalRejected as exc:
        raise ValidationError(f"invalid signal: {exc}") from exc
    return _simulation_out(report)


# -- rules -------------------------------------------------------------------


@router.get("/trigger-rules", response_model=list[RuleOut])
async def list_rules(
    _: AuthContext = Depends(require("technical_endpoints.view")),
    svc: TriggerRuleAdminService = Depends(_svc),
) -> list[RuleOut]:
    return [_rule_out(r) for r in await svc.list_rules()]


@router.post("/trigger-rules", response_model=RuleDetailOut, status_code=status.HTTP_201_CREATED)
async def create_rule(
    body: RuleIn,
    ctx: AuthContext = Depends(require("technical_endpoints.manage")),
    svc: TriggerRuleAdminService = Depends(_svc),
) -> RuleDetailOut:
    with _translate():
        rule, version = await svc.create_rule(
            RuleInput(
                name=body.name,
                conditions=body.conditions,
                actions=body.actions,
                priority=body.priority,
                endpoint_id=body.endpoint_id,
                changelog=body.changelog,
            ),
            actor_id=ctx.user_id,
        )
    return RuleDetailOut(**_rule_out(rule).model_dump(), versions=[_version_out(version)])


@router.get("/trigger-rules/{rule_id}", response_model=RuleDetailOut)
async def get_rule(
    rule_id: uuid.UUID,
    _: AuthContext = Depends(require("technical_endpoints.view")),
    svc: TriggerRuleAdminService = Depends(_svc),
) -> RuleDetailOut:
    with _translate():
        rule = await svc.get_rule(rule_id)
        versions = await svc.versions_for(rule_id)
    return RuleDetailOut(
        **_rule_out(rule).model_dump(), versions=[_version_out(v) for v in versions]
    )


@router.patch("/trigger-rules/{rule_id}", response_model=RuleOut)
async def update_rule(
    rule_id: uuid.UUID,
    body: RulePatch,
    ctx: AuthContext = Depends(require("technical_endpoints.manage")),
    svc: TriggerRuleAdminService = Depends(_svc),
) -> RuleOut:
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise ValidationError("no fields to update")
    with _translate():
        rule = await svc.update_rule(rule_id, changes, actor_id=ctx.user_id)
    return _rule_out(rule)


@router.delete("/trigger-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: uuid.UUID,
    ctx: AuthContext = Depends(require("technical_endpoints.manage")),
    svc: TriggerRuleAdminService = Depends(_svc),
) -> None:
    with _translate():
        await svc.delete_rule(rule_id, actor_id=ctx.user_id)


@router.post(
    "/trigger-rules/{rule_id}/versions",
    response_model=VersionOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_version(
    rule_id: uuid.UUID,
    body: VersionIn,
    ctx: AuthContext = Depends(require("technical_endpoints.manage")),
    svc: TriggerRuleAdminService = Depends(_svc),
) -> VersionOut:
    with _translate():
        version = await svc.add_version(
            rule_id,
            conditions=body.conditions,
            actions=body.actions,
            changelog=body.changelog,
            actor_id=ctx.user_id,
        )
    return _version_out(version)


# -- versions --------------------------------------------------------------


@router.get("/trigger-rule-versions/{version_id}", response_model=VersionOut)
async def get_version(
    version_id: uuid.UUID,
    _: AuthContext = Depends(require("technical_endpoints.view")),
    svc: TriggerRuleAdminService = Depends(_svc),
) -> VersionOut:
    with _translate():
        return _version_out(await svc.get_version(version_id))


@router.patch("/trigger-rule-versions/{version_id}", response_model=VersionOut)
async def edit_version(
    version_id: uuid.UUID,
    body: VersionIn,
    ctx: AuthContext = Depends(require("technical_endpoints.manage")),
    svc: TriggerRuleAdminService = Depends(_svc),
) -> VersionOut:
    with _translate():
        version = await svc.edit_draft(
            version_id,
            conditions=body.conditions,
            actions=body.actions,
            changelog=body.changelog,
            actor_id=ctx.user_id,
        )
    return _version_out(version)


@router.delete("/trigger-rule-versions/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_version(
    version_id: uuid.UUID,
    ctx: AuthContext = Depends(require("technical_endpoints.manage")),
    svc: TriggerRuleAdminService = Depends(_svc),
) -> None:
    with _translate():
        await svc.delete_draft(version_id, actor_id=ctx.user_id)


@router.post("/trigger-rule-versions/{version_id}/validate", response_model=ValidateOut)
async def validate_version(
    version_id: uuid.UUID,
    ctx: AuthContext = Depends(require("technical_endpoints.manage")),
    svc: TriggerRuleAdminService = Depends(_svc),
) -> ValidateOut:
    with _translate():
        issues = await svc.validate(version_id, actor_id=ctx.user_id)
        version = await svc.get_version(version_id)
    return ValidateOut(valid=not issues, lifecycle=version.lifecycle, issues=issues)


@router.post("/trigger-rule-versions/{version_id}/publish", response_model=VersionOut)
async def publish_version(
    version_id: uuid.UUID,
    body: PublishIn,
    ctx: AuthContext = Depends(require("technical_endpoints.manage")),
    svc: TriggerRuleAdminService = Depends(_svc),
) -> VersionOut:
    with _translate():
        version = await svc.publish(version_id, actor_id=ctx.user_id, changelog=body.changelog)
    return _version_out(version)


@router.post("/trigger-rule-versions/{version_id}/retire", response_model=VersionOut)
async def retire_version(
    version_id: uuid.UUID,
    ctx: AuthContext = Depends(require("technical_endpoints.manage")),
    svc: TriggerRuleAdminService = Depends(_svc),
) -> VersionOut:
    with _translate():
        version = await svc.retire(version_id, actor_id=ctx.user_id)
    return _version_out(version)
