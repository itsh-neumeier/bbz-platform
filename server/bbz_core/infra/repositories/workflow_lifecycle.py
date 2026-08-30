"""Workflow template-version lifecycle (roadmap E05-07, ADR-0005).

``draft -> validated -> published -> deprecated``. Immutability from PUBLISHED
is enforced twice: this service refuses to edit a non-draft version, and the DB
trigger from migration 0017 blocks a ``definition`` change on a published row.
A new change is a **new draft version** (``create_draft_version``).

Each mutating method commits its own transaction (autobegun by the first query)
and writes an audit row (``WORKFLOW_TEMPLATE_VALIDATED`` / ``_PUBLISHED`` /
``_DEPRECATED``) in it.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import AuditAction, AuditService
from bbz_core.domain.workflow import (
    SimulationReport,
    ValidationIssue,
    diff_definitions,
    simulate,
    validate_publishable,
)
from bbz_core.infra.models.workflow import (
    WorkflowLifecycle,
    WorkflowTemplate,
    WorkflowTemplateVersion,
)
from bbz_core.infra.models.workflow_runtime import WorkflowInstance
from bbz_core.infra.repositories.workflow_graph import rebuild_graph_index


class WorkflowLifecycleError(Exception):
    pass


class VersionNotFoundError(WorkflowLifecycleError):
    pass


class InvalidTransitionError(WorkflowLifecycleError):
    """The version is not in a lifecycle state that allows this action."""


class NotValidatedError(WorkflowLifecycleError):
    """publish() was called on a version that was never validated."""


class ChangelogRequiredError(WorkflowLifecycleError):
    pass


class TemplateKeyExistsError(WorkflowLifecycleError):
    pass


class TemplateNotFoundError(WorkflowLifecycleError):
    pass


class VersionInUseError(WorkflowLifecycleError):
    """A draft version cannot be deleted while an instance is pinned to it."""


class GraphNotPublishableError(WorkflowLifecycleError):
    def __init__(self, issues: list[ValidationIssue]) -> None:
        super().__init__(f"{len(issues)} validation issue(s)")
        self.issues = issues


class WorkflowLifecycleService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def _require(self, version_id: uuid.UUID) -> WorkflowTemplateVersion:
        row = await self._s.get(WorkflowTemplateVersion, version_id)
        if row is None:
            raise VersionNotFoundError(str(version_id))
        return row

    async def create_template(
        self, *, key: str, name: str, actor_id: uuid.UUID | None
    ) -> WorkflowTemplate:
        tpl = WorkflowTemplate(key=key, name=name, owner_id=actor_id)
        self._s.add(tpl)
        try:
            await self._s.flush()
        except DBAPIError as exc:
            raise TemplateKeyExistsError(key) from exc
        await self._audit_template(AuditAction.WORKFLOW_TEMPLATE_CREATED, tpl, actor_id)
        await self._s.commit()
        return tpl

    async def rename_template(
        self, template_id: uuid.UUID, *, name: str, actor_id: uuid.UUID | None
    ) -> WorkflowTemplate:
        tpl = await self._s.get(WorkflowTemplate, template_id)
        if tpl is None:
            raise TemplateNotFoundError(str(template_id))
        tpl.name = name
        await self._audit_template(AuditAction.WORKFLOW_TEMPLATE_UPDATED, tpl, actor_id)
        await self._s.commit()
        return tpl

    async def create_draft_version(
        self,
        template_id: uuid.UUID,
        *,
        definition: dict[str, Any],
        changelog: str | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> WorkflowTemplateVersion:
        next_no = (
            await self._s.execute(
                select(func.coalesce(func.max(WorkflowTemplateVersion.version_no), 0) + 1).where(
                    WorkflowTemplateVersion.template_id == template_id
                )
            )
        ).scalar_one()
        row = WorkflowTemplateVersion(
            template_id=template_id,
            version_no=next_no,
            lifecycle=WorkflowLifecycle.DRAFT.value,
            definition=definition,
            changelog=changelog,
        )
        self._s.add(row)
        await self._s.flush()
        await self._audit(AuditAction.WORKFLOW_TEMPLATE_UPDATED, row, actor_id)
        await self._s.commit()
        return row

    async def edit_draft(
        self,
        version_id: uuid.UUID,
        *,
        definition: dict[str, Any],
        changelog: str | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> None:
        row = await self._require(version_id)
        if row.lifecycle != WorkflowLifecycle.DRAFT.value:
            raise InvalidTransitionError(
                f"version is {row.lifecycle}; create a new draft version to change it"
            )
        row.definition = definition
        if changelog is not None:
            row.changelog = changelog
        await self._audit(AuditAction.WORKFLOW_TEMPLATE_UPDATED, row, actor_id)
        await self._s.commit()

    async def delete_draft_version(
        self, version_id: uuid.UUID, *, actor_id: uuid.UUID | None = None
    ) -> None:
        row = await self._require(version_id)
        if row.lifecycle != WorkflowLifecycle.DRAFT.value:
            raise InvalidTransitionError(f"cannot delete a {row.lifecycle} version")
        pinned = (
            await self._s.execute(
                select(WorkflowInstance.id)
                .where(WorkflowInstance.template_version_id == version_id)
                .limit(1)
            )
        ).first()
        if pinned is not None:
            raise VersionInUseError(str(version_id))
        await self._audit(AuditAction.WORKFLOW_TEMPLATE_UPDATED, row, actor_id)
        await self._s.execute(
            delete(WorkflowTemplateVersion).where(WorkflowTemplateVersion.id == version_id)
        )
        await self._s.commit()

    async def simulate_version(
        self,
        version_id: uuid.UUID,
        *,
        context: dict[str, Any] | None = None,
        decisions: dict[str, list[str]] | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> SimulationReport:
        """Dry-run the version's graph — no real outbox rows, no side effects."""
        row = await self._require(version_id)
        report = simulate(row.definition, context=context, decisions=decisions)
        await self._audit(AuditAction.WORKFLOW_SIMULATED, row, actor_id)
        await self._s.commit()
        return report

    async def version_diff(self, version_id: uuid.UUID) -> dict[str, Any]:
        """Structural diff of this version against the previous version_no."""
        row = await self._require(version_id)
        prev = (
            await self._s.execute(
                select(WorkflowTemplateVersion.definition)
                .where(
                    WorkflowTemplateVersion.template_id == row.template_id,
                    WorkflowTemplateVersion.version_no < row.version_no,
                )
                .order_by(WorkflowTemplateVersion.version_no.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return diff_definitions(prev, row.definition)

    async def validate(
        self,
        version_id: uuid.UUID,
        *,
        actor_id: uuid.UUID,
        known_capabilities: Iterable[str] | None = None,
    ) -> list[ValidationIssue]:
        row = await self._require(version_id)
        if row.lifecycle not in (
            WorkflowLifecycle.DRAFT.value,
            WorkflowLifecycle.VALIDATED.value,
        ):
            raise InvalidTransitionError(f"cannot validate a {row.lifecycle} version")
        issues = validate_publishable(row.definition, known_capabilities=known_capabilities)
        if issues:
            return issues
        row.lifecycle = WorkflowLifecycle.VALIDATED.value
        await rebuild_graph_index(
            self._s, template_version_id=version_id, definition=row.definition
        )
        await self._audit(AuditAction.WORKFLOW_TEMPLATE_VALIDATED, row, actor_id)
        await self._s.commit()
        return []

    async def publish(
        self, version_id: uuid.UUID, *, actor_id: uuid.UUID, changelog: str
    ) -> WorkflowTemplateVersion:
        row = await self._require(version_id)
        if row.lifecycle != WorkflowLifecycle.VALIDATED.value:
            raise NotValidatedError(
                f"version is {row.lifecycle}; it must be validated before publishing"
            )
        if not changelog.strip():
            raise ChangelogRequiredError("a changelog is required when publishing")
        row.lifecycle = WorkflowLifecycle.PUBLISHED.value
        row.changelog = changelog.strip()
        row.published_at = _dt.datetime.now(_dt.UTC)
        row.published_by = actor_id
        await self._audit(AuditAction.WORKFLOW_TEMPLATE_PUBLISHED, row, actor_id, reason=changelog)
        await self._s.commit()
        return row

    async def deprecate(
        self, version_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> WorkflowTemplateVersion:
        row = await self._require(version_id)
        if row.lifecycle != WorkflowLifecycle.PUBLISHED.value:
            raise InvalidTransitionError(f"cannot deprecate a {row.lifecycle} version")
        row.lifecycle = WorkflowLifecycle.DEPRECATED.value
        await self._audit(AuditAction.WORKFLOW_TEMPLATE_DEPRECATED, row, actor_id)
        await self._s.commit()
        return row

    async def _audit(
        self,
        action: AuditAction,
        row: WorkflowTemplateVersion,
        actor_id: uuid.UUID | None,
        *,
        reason: str | None = None,
    ) -> None:
        await AuditService(self._s).write(
            action,
            actor_user_id=actor_id,
            target_type="workflow_template_version",
            target_id=str(row.id),
            after={
                "template_id": str(row.template_id),
                "version_no": row.version_no,
                "lifecycle": row.lifecycle,
            },
            reason=reason,
        )

    async def _audit_template(
        self, action: AuditAction, tpl: WorkflowTemplate, actor_id: uuid.UUID | None
    ) -> None:
        await AuditService(self._s).write(
            action,
            actor_user_id=actor_id,
            target_type="workflow_template",
            target_id=str(tpl.id),
            after={"key": tpl.key, "name": tpl.name},
        )
