"""Trigger-rule admin repository + lifecycle (roadmap E15-10).

``draft -> validated -> published -> retired`` for a
:class:`TriggerRuleVersion`, mirroring
:class:`bbz_core.infra.repositories.workflow_lifecycle.WorkflowLifecycleService`
(ADR-0005 / ADR-0010). Immutability from PUBLISHED is enforced twice: this
service refuses to edit a non-draft version, and the DB trigger from migration
0031 blocks a ``conditions`` / ``actions`` change on a published row. A change
to a published rule is a **new draft version** (:meth:`add_version`).

* :meth:`validate` is the publish gate — :func:`bbz_core.domain.triggers.publish_blockers`
  checks the DSL conditions against ``TRIGGER_CONTEXT`` (E15-05) and every action
  against the typed, currently-runnable action set (E15-06/08);
* :meth:`publish` refuses a version that was never validated, retires the rule's
  previously-published version, and mirrors ``published`` onto the parent rule so
  the engine (E15-09) picks it up.

Every transition writes a ``TRIGGER_RULE_*`` audit row in its own transaction.
Highly privileged: a published rule can open doors automatically.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import AuditAction, AuditService
from bbz_core.domain.triggers import publish_blockers
from bbz_core.infra.models.technical_endpoints import TechnicalEndpoint
from bbz_core.infra.models.trigger_rules import (
    TriggerLifecycle,
    TriggerRule,
    TriggerRuleVersion,
)

_DRAFT = TriggerLifecycle.DRAFT.value
_VALIDATED = TriggerLifecycle.VALIDATED.value
_PUBLISHED = TriggerLifecycle.PUBLISHED.value
_RETIRED = TriggerLifecycle.RETIRED.value


class TriggerRuleAdminError(Exception):
    pass


class RuleNotFoundError(TriggerRuleAdminError):
    pass


class VersionNotFoundError(TriggerRuleAdminError):
    pass


class EndpointNotFoundError(TriggerRuleAdminError):
    """``endpoint_id`` does not reference an existing technical endpoint."""


class InvalidRuleTransitionError(TriggerRuleAdminError):
    """The version is not in a lifecycle state that allows this action."""


class RuleNotValidatedError(TriggerRuleAdminError):
    """publish() on a version that is not in the ``validated`` state."""


class RulePublishBlockedError(TriggerRuleAdminError):
    def __init__(self, issues: list[str]) -> None:
        super().__init__(f"{len(issues)} issue(s) block publishing")
        self.issues = issues


class RuleHasPublishedVersionError(TriggerRuleAdminError):
    """A rule with a published version cannot be deleted — retire it first."""


@dataclass
class RuleInput:
    name: str
    conditions: dict[str, Any]
    actions: list[Any]
    priority: int = 100
    endpoint_id: uuid.UUID | None = None
    changelog: str | None = None


class TriggerRuleAdminService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # --- reads ------------------------------------------------------------
    #
    # No ``rollback()`` here: these run on a fresh request session and a leading
    # rollback would expire ORM objects the caller still holds (the router
    # serialises them after the call returns). The mutating methods below own the
    # single defensive rollback.

    async def list_rules(self) -> list[TriggerRule]:
        return list(
            (
                await self._s.execute(
                    select(TriggerRule)
                    .order_by(TriggerRule.priority, TriggerRule.name)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )

    async def get_rule(self, rule_id: uuid.UUID) -> TriggerRule:
        rule = (
            await self._s.execute(
                select(TriggerRule)
                .where(TriggerRule.id == rule_id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if rule is None:
            raise RuleNotFoundError(str(rule_id))
        return rule

    async def versions_for(self, rule_id: uuid.UUID) -> list[TriggerRuleVersion]:
        return list(
            (
                await self._s.execute(
                    select(TriggerRuleVersion)
                    .where(TriggerRuleVersion.rule_id == rule_id)
                    .order_by(TriggerRuleVersion.version_no)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )

    async def get_version(self, version_id: uuid.UUID) -> TriggerRuleVersion:
        row = (
            await self._s.execute(
                select(TriggerRuleVersion)
                .where(TriggerRuleVersion.id == version_id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if row is None:
            raise VersionNotFoundError(str(version_id))
        return row

    # --- rule CRUD ------------------------------------------------------------

    async def create_rule(
        self, data: RuleInput, *, actor_id: uuid.UUID | None
    ) -> tuple[TriggerRule, TriggerRuleVersion]:
        await self._s.rollback()
        await self._require_endpoint(data.endpoint_id)
        rule = TriggerRule(
            name=data.name,
            priority=data.priority,
            endpoint_id=data.endpoint_id,
            lifecycle=_DRAFT,
        )
        self._s.add(rule)
        await self._s.flush()
        version = TriggerRuleVersion(
            rule_id=rule.id,
            version_no=1,
            lifecycle=_DRAFT,
            conditions=data.conditions,
            actions=data.actions,
            changelog=data.changelog,
        )
        self._s.add(version)
        await self._s.flush()
        await self._audit(
            AuditAction.TRIGGER_RULE_CREATED,
            rule.id,
            actor_id,
            after={"name": rule.name, "priority": rule.priority, "version_id": str(version.id)},
        )
        await self._s.commit()
        return rule, version

    async def update_rule(
        self, rule_id: uuid.UUID, changes: dict[str, Any], *, actor_id: uuid.UUID | None
    ) -> TriggerRule:
        allowed = {"name", "priority", "endpoint_id"}
        unknown = set(changes) - allowed
        if unknown:
            raise InvalidRuleTransitionError(f"cannot change: {', '.join(sorted(unknown))}")
        await self._s.rollback()
        rule = await self._s.get(TriggerRule, rule_id)
        if rule is None:
            raise RuleNotFoundError(str(rule_id))
        if "endpoint_id" in changes:
            await self._require_endpoint(changes["endpoint_id"])
        before = {k: _jsonable(getattr(rule, k)) for k in changes}
        after = {k: _jsonable(v) for k, v in changes.items()}
        if before == after:
            await self._s.rollback()
            return await self.get_rule(rule_id)
        for key, value in changes.items():
            setattr(rule, key, value)
        await self._audit(
            AuditAction.TRIGGER_RULE_UPDATED,
            rule_id,
            actor_id,
            after={"before": before, "after": after},
        )
        await self._s.commit()
        return rule

    async def delete_rule(self, rule_id: uuid.UUID, *, actor_id: uuid.UUID | None) -> None:
        await self._s.rollback()
        rule = await self._s.get(TriggerRule, rule_id)
        if rule is None:
            raise RuleNotFoundError(str(rule_id))
        if await self._published_version_id(rule_id) is not None:
            raise RuleHasPublishedVersionError(str(rule_id))
        await self._audit(
            AuditAction.TRIGGER_RULE_UPDATED, rule_id, actor_id, after={"deleted": rule.name}
        )
        await self._s.execute(delete(TriggerRule).where(TriggerRule.id == rule_id))
        await self._s.commit()

    # --- version CRUD -------------------------------------------------------

    async def add_version(
        self,
        rule_id: uuid.UUID,
        *,
        conditions: dict[str, Any],
        actions: list[Any],
        changelog: str | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> TriggerRuleVersion:
        await self._s.rollback()
        if await self._s.get(TriggerRule, rule_id) is None:
            raise RuleNotFoundError(str(rule_id))
        next_no = (
            await self._s.execute(
                select(func.coalesce(func.max(TriggerRuleVersion.version_no), 0) + 1).where(
                    TriggerRuleVersion.rule_id == rule_id
                )
            )
        ).scalar_one()
        version = TriggerRuleVersion(
            rule_id=rule_id,
            version_no=next_no,
            lifecycle=_DRAFT,
            conditions=conditions,
            actions=actions,
            changelog=changelog,
        )
        self._s.add(version)
        await self._s.flush()
        await self._audit(
            AuditAction.TRIGGER_RULE_UPDATED,
            rule_id,
            actor_id,
            after={"new_version_no": next_no, "version_id": str(version.id)},
        )
        await self._s.commit()
        return version

    async def edit_draft(
        self,
        version_id: uuid.UUID,
        *,
        conditions: dict[str, Any],
        actions: list[Any],
        changelog: str | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> TriggerRuleVersion:
        await self._s.rollback()
        row = await self.get_version(version_id)
        if row.lifecycle != _DRAFT:
            raise InvalidRuleTransitionError(
                f"version is {row.lifecycle}; add a new version to change a non-draft"
            )
        row.conditions = conditions
        row.actions = actions
        if changelog is not None:
            row.changelog = changelog
        await self._audit(
            AuditAction.TRIGGER_RULE_UPDATED,
            row.rule_id,
            actor_id,
            after={"version_id": str(version_id), "edited": True},
        )
        await self._s.commit()
        return row

    async def delete_draft(
        self, version_id: uuid.UUID, *, actor_id: uuid.UUID | None = None
    ) -> None:
        await self._s.rollback()
        row = await self.get_version(version_id)
        if row.lifecycle != _DRAFT:
            raise InvalidRuleTransitionError(f"cannot delete a {row.lifecycle} version")
        rule_id = row.rule_id
        await self._audit(
            AuditAction.TRIGGER_RULE_UPDATED,
            rule_id,
            actor_id,
            after={"deleted_version_id": str(version_id)},
        )
        await self._s.execute(delete(TriggerRuleVersion).where(TriggerRuleVersion.id == version_id))
        await self._s.commit()

    # --- lifecycle --------------------------------------------------------

    async def validate(self, version_id: uuid.UUID, *, actor_id: uuid.UUID | None) -> list[str]:
        await self._s.rollback()
        row = await self.get_version(version_id)
        if row.lifecycle not in (_DRAFT, _VALIDATED):
            raise InvalidRuleTransitionError(f"cannot validate a {row.lifecycle} version")
        issues = publish_blockers(row.conditions, row.actions)
        if issues:
            await self._s.rollback()
            return issues
        row.lifecycle = _VALIDATED
        await self._audit(
            AuditAction.TRIGGER_RULE_VALIDATED,
            row.rule_id,
            actor_id,
            after={"version_id": str(version_id), "version_no": row.version_no},
        )
        await self._s.commit()
        return []

    async def publish(
        self, version_id: uuid.UUID, *, actor_id: uuid.UUID | None, changelog: str | None = None
    ) -> TriggerRuleVersion:
        await self._s.rollback()
        row = await self.get_version(version_id)
        if row.lifecycle != _VALIDATED:
            raise RuleNotValidatedError(
                f"version is {row.lifecycle}; it must be validated before publishing"
            )
        issues = publish_blockers(row.conditions, row.actions)
        if issues:
            await self._s.rollback()
            raise RulePublishBlockedError(issues)

        superseded = await self._retire_current_published(row.rule_id, keep=version_id)
        row.lifecycle = _PUBLISHED
        row.published_at = _dt.datetime.now(_dt.UTC)
        row.published_by = actor_id
        if changelog is not None and changelog.strip():
            row.changelog = changelog.strip()

        rule = await self._s.get(TriggerRule, row.rule_id)
        assert rule is not None
        rule.lifecycle = _PUBLISHED

        await self._audit(
            AuditAction.TRIGGER_RULE_PUBLISHED,
            row.rule_id,
            actor_id,
            after={
                "version_id": str(version_id),
                "version_no": row.version_no,
                "superseded_version_id": str(superseded) if superseded else None,
            },
            reason=changelog,
        )
        await self._s.commit()
        return row

    async def retire(
        self, version_id: uuid.UUID, *, actor_id: uuid.UUID | None
    ) -> TriggerRuleVersion:
        await self._s.rollback()
        row = await self.get_version(version_id)
        if row.lifecycle != _PUBLISHED:
            raise InvalidRuleTransitionError(f"cannot retire a {row.lifecycle} version")
        row.lifecycle = _RETIRED
        if await self._published_version_id(row.rule_id, exclude=version_id) is None:
            rule = await self._s.get(TriggerRule, row.rule_id)
            assert rule is not None
            rule.lifecycle = _RETIRED
        await self._audit(
            AuditAction.TRIGGER_RULE_RETIRED,
            row.rule_id,
            actor_id,
            after={"version_id": str(version_id), "version_no": row.version_no},
        )
        await self._s.commit()
        return row

    # --- internals ------------------------------------------------------------

    async def _require_endpoint(self, endpoint_id: uuid.UUID | None) -> None:
        if endpoint_id is None:
            return
        if await self._s.get(TechnicalEndpoint, endpoint_id) is None:
            raise EndpointNotFoundError(str(endpoint_id))

    async def _published_version_id(
        self, rule_id: uuid.UUID, *, exclude: uuid.UUID | None = None
    ) -> uuid.UUID | None:
        stmt = select(TriggerRuleVersion.id).where(
            TriggerRuleVersion.rule_id == rule_id,
            TriggerRuleVersion.lifecycle == _PUBLISHED,
        )
        if exclude is not None:
            stmt = stmt.where(TriggerRuleVersion.id != exclude)
        return (await self._s.execute(stmt.limit(1))).scalar_one_or_none()

    async def _retire_current_published(
        self, rule_id: uuid.UUID, *, keep: uuid.UUID
    ) -> uuid.UUID | None:
        rows = (
            (
                await self._s.execute(
                    select(TriggerRuleVersion).where(
                        TriggerRuleVersion.rule_id == rule_id,
                        TriggerRuleVersion.lifecycle == _PUBLISHED,
                        TriggerRuleVersion.id != keep,
                    )
                )
            )
            .scalars()
            .all()
        )
        superseded: uuid.UUID | None = None
        for r in rows:
            r.lifecycle = _RETIRED
            superseded = r.id
        return superseded

    async def _audit(
        self,
        action: AuditAction,
        rule_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        *,
        after: dict[str, Any],
        reason: str | None = None,
    ) -> None:
        await AuditService(self._s).write(
            action,
            actor_user_id=actor_id,
            target_type="trigger_rule",
            target_id=str(rule_id),
            after=after,
            reason=reason,
        )


def _jsonable(value: object) -> object:
    return str(value) if isinstance(value, uuid.UUID) else value
