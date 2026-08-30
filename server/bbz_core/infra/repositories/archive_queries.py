"""Archive detail aggregator (roadmap E20-01).

An archived event keeps its **full** history. Archiving is a status transition
(``EVENT_ARCHIVED`` audit + a status-history row + a domain event) — nothing is
deleted or summarised. There is therefore **no ``event_archive`` table**: the
archive detail is a read over the same append-only tables that back an active
event (see ``docs/domain/archive.md`` and ADR-0011).

:meth:`ArchiveQueryRepository.detail` bundles, for one event regardless of its
archived state:

* the active-event detail (core fields, description, status history, notes),
* the ordered domain-event log (``domain_events``),
* every workflow instance with its task results and decisions,
* the audit-trail references that target the event.

Calls (Epic 11) will be folded in once that schema exists; the ``calls`` field
is already present and empty so the shape is stable for the UI (E07-11).
"""

from __future__ import annotations

import datetime as _dt
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.domain_events import DomainEvent
from bbz_core.infra.models.workflow import WorkflowTemplate, WorkflowTemplateVersion
from bbz_core.infra.models.workflow_runtime import (
    WorkflowDecision,
    WorkflowInstance,
    WorkflowTaskResult,
)
from bbz_core.infra.repositories.event_queries import (
    DomainEventItem,
    EventDetail,
    EventQueryRepository,
)


@dataclass(frozen=True)
class WorkflowTaskResultItem:
    node_key: str
    result: dict[str, Any]
    completed_by: uuid.UUID | None
    completed_at: _dt.datetime


@dataclass(frozen=True)
class WorkflowDecisionItem:
    connector_node_key: str
    chosen_branches: list[str]
    auto: bool
    decided_by: uuid.UUID | None
    decided_at: _dt.datetime


@dataclass(frozen=True)
class WorkflowInstanceItem:
    id: uuid.UUID
    template_key: str | None
    template_name: str | None
    template_version: int | None
    status: str
    started_at: _dt.datetime
    ended_at: _dt.datetime | None
    task_results: list[WorkflowTaskResultItem]
    decisions: list[WorkflowDecisionItem]


@dataclass(frozen=True)
class AuditRefItem:
    id: uuid.UUID
    occurred_at_utc: _dt.datetime
    action: str
    actor_user_id: uuid.UUID | None
    correlation_id: str | None
    event_seq_ref: int | None


@dataclass(frozen=True)
class ArchiveDetail:
    detail: EventDetail
    domain_events: list[DomainEventItem]
    workflows: list[WorkflowInstanceItem]
    audit_refs: list[AuditRefItem]
    calls: list[Any] = field(default_factory=list)  # Epic 11


class ArchiveQueryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def detail(self, event_id: uuid.UUID) -> ArchiveDetail | None:
        detail = await EventQueryRepository(self._s).detail(event_id)
        if detail is None:
            return None
        return ArchiveDetail(
            detail=detail,
            domain_events=await self._domain_events(event_id),
            workflows=await self._workflows(event_id),
            audit_refs=await self._audit_refs(event_id),
        )

    async def _domain_events(self, event_id: uuid.UUID) -> list[DomainEventItem]:
        rows = (
            (
                await self._s.execute(
                    select(DomainEvent)
                    .where(DomainEvent.aggregate_id == str(event_id))
                    .order_by(DomainEvent.event_seq.asc())
                )
            )
            .scalars()
            .all()
        )
        return [
            DomainEventItem(
                event_seq=r.event_seq,
                event_type=r.event_type,
                occurred_at_utc=r.occurred_at_utc,
                user_id=r.user_id,
                payload=r.payload,
            )
            for r in rows
        ]

    async def _workflows(self, event_id: uuid.UUID) -> list[WorkflowInstanceItem]:
        rows = (
            await self._s.execute(
                select(WorkflowInstance, WorkflowTemplateVersion, WorkflowTemplate)
                .join(
                    WorkflowTemplateVersion,
                    WorkflowTemplateVersion.id == WorkflowInstance.template_version_id,
                    isouter=True,
                )
                .join(
                    WorkflowTemplate,
                    WorkflowTemplate.id == WorkflowTemplateVersion.template_id,
                    isouter=True,
                )
                .where(WorkflowInstance.event_id == event_id)
                .order_by(WorkflowInstance.started_at.asc(), WorkflowInstance.id.asc())
            )
        ).all()
        out: list[WorkflowInstanceItem] = []
        for inst, version, template in rows:
            out.append(
                WorkflowInstanceItem(
                    id=inst.id,
                    template_key=template.key if template is not None else None,
                    template_name=template.name if template is not None else None,
                    template_version=version.version_no if version is not None else None,
                    status=inst.status,
                    started_at=inst.started_at,
                    ended_at=inst.ended_at,
                    task_results=await self._task_results(inst.id),
                    decisions=await self._decisions(inst.id),
                )
            )
        return out

    async def _task_results(self, instance_id: uuid.UUID) -> list[WorkflowTaskResultItem]:
        rows = (
            (
                await self._s.execute(
                    select(WorkflowTaskResult)
                    .where(WorkflowTaskResult.instance_id == instance_id)
                    .order_by(WorkflowTaskResult.completed_at.asc())
                )
            )
            .scalars()
            .all()
        )
        return [
            WorkflowTaskResultItem(
                node_key=r.node_key,
                result=r.result,
                completed_by=r.completed_by,
                completed_at=r.completed_at,
            )
            for r in rows
        ]

    async def _decisions(self, instance_id: uuid.UUID) -> list[WorkflowDecisionItem]:
        rows = (
            (
                await self._s.execute(
                    select(WorkflowDecision)
                    .where(WorkflowDecision.instance_id == instance_id)
                    .order_by(WorkflowDecision.decided_at.asc())
                )
            )
            .scalars()
            .all()
        )
        return [
            WorkflowDecisionItem(
                connector_node_key=r.connector_node_key,
                chosen_branches=r.chosen_branches,
                auto=r.auto,
                decided_by=r.decided_by,
                decided_at=r.decided_at,
            )
            for r in rows
        ]

    async def _audit_refs(self, event_id: uuid.UUID) -> list[AuditRefItem]:
        rows = (
            (
                await self._s.execute(
                    select(AuditEvent)
                    .where(
                        AuditEvent.target_type == "event",
                        AuditEvent.target_id == str(event_id),
                    )
                    .order_by(AuditEvent.occurred_at_utc.asc())
                )
            )
            .scalars()
            .all()
        )
        return [
            AuditRefItem(
                id=r.id,
                occurred_at_utc=r.occurred_at_utc,
                action=r.action,
                actor_user_id=r.actor_user_id,
                correlation_id=r.correlation_id,
                event_seq_ref=r.event_seq_ref,
            )
            for r in rows
        ]
