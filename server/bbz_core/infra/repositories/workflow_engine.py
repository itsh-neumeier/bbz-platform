"""Workflow token engine — persistence + step completion (roadmap E05-08).

The deterministic token flow lives in :mod:`bbz_core.domain.workflow.engine`;
this service loads the instance's token state, runs the engine, and writes the
resulting mutations **in one transaction**. Every method commits its own
transaction (autobegun by the first query), so a crash either commits a whole
step or nothing — and re-running :meth:`advance_instance` from the persisted
token state is a no-op once the step is in (idempotent failover).

Only AND connectors are handled (see the engine module); XOR / OR is E05-09.
Task *execution* (integration actions, notifications, timers actually firing)
is E05-10 — here a function node simply parks its token until
:meth:`complete_step` is called.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import AuditAction, AuditService
from bbz_core.domain.workflow import DerivedGraph, EngineResult, Token, derive_index
from bbz_core.domain.workflow.engine import StepNotWaitingError, advance, resume_function
from bbz_core.infra.models.workflow import WorkflowTemplateVersion
from bbz_core.infra.models.workflow_runtime import (
    WorkflowInstance,
    WorkflowInstanceStatus,
    WorkflowTaskResult,
    WorkflowToken,
    WorkflowTokenState,
)

_LIVE = (WorkflowTokenState.ACTIVE.value, WorkflowTokenState.WAITING.value)


class WorkflowEngineError(Exception):
    pass


class InstanceNotFoundError(WorkflowEngineError):
    pass


class StepNotAvailableError(WorkflowEngineError):
    """complete_step() was called for a node that has no step waiting."""


class WorkflowEngineService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def start_instance(
        self, *, event_id: uuid.UUID, template_version_id: uuid.UUID
    ) -> WorkflowInstance:
        """Create an instance on a published version, seed the start token, run."""
        inst = WorkflowInstance(event_id=event_id, template_version_id=template_version_id)
        self._s.add(inst)
        await self._s.flush()  # the BEFORE INSERT trigger enforces "published"
        graph = await self._graph(template_version_id)
        self._s.add(
            WorkflowToken(
                instance_id=inst.id,
                node_key=graph.start,
                inbound_edge_key=None,
                state=WorkflowTokenState.ACTIVE.value,
            )
        )
        await self._s.flush()
        await self._apply(inst, advance(graph, await self._tokens(inst.id)))
        await self._s.commit()
        return inst

    async def advance_instance(self, instance_id: uuid.UUID) -> WorkflowInstance:
        """Re-run the engine from the persisted token state (crash recovery)."""
        inst = await self._require(instance_id)
        if inst.status != WorkflowInstanceStatus.RUNNING.value:
            await self._s.commit()
            return inst
        graph = await self._graph(inst.template_version_id)
        await self._apply(inst, advance(graph, await self._tokens(instance_id)))
        await self._s.commit()
        return inst

    async def complete_step(
        self,
        instance_id: uuid.UUID,
        node_key: str,
        *,
        result: dict[str, Any] | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> WorkflowInstance:
        """Record a function node's result, move its token on, then advance.

        Idempotent: a second call for the same ``(instance, node)`` is a no-op
        (no duplicate result row, no duplicate audit entry)."""
        inst = await self._require(instance_id)
        already = (
            await self._s.execute(
                select(WorkflowTaskResult.id).where(
                    WorkflowTaskResult.instance_id == instance_id,
                    WorkflowTaskResult.node_key == node_key,
                )
            )
        ).first()
        if already is not None:
            await self._s.commit()
            return inst

        graph = await self._graph(inst.template_version_id)
        try:
            outcome = resume_function(graph, await self._tokens(instance_id), node_key)
        except StepNotWaitingError as exc:
            raise StepNotAvailableError(str(exc)) from exc

        self._s.add(
            WorkflowTaskResult(
                instance_id=instance_id,
                node_key=node_key,
                result=result or {},
                completed_by=actor_id,
            )
        )
        await AuditService(self._s).write(
            AuditAction.ACTION_STEP_COMPLETED,
            actor_user_id=actor_id,
            target_type="workflow_instance",
            target_id=str(instance_id),
            after={"node_key": node_key, "instance_id": str(instance_id)},
        )
        await self._apply(inst, outcome)
        await self._s.commit()
        return inst

    # -- internals -----------------------------------------------------------

    async def _require(self, instance_id: uuid.UUID) -> WorkflowInstance:
        inst = await self._s.get(WorkflowInstance, instance_id)
        if inst is None:
            raise InstanceNotFoundError(str(instance_id))
        return inst

    async def _graph(self, template_version_id: uuid.UUID) -> DerivedGraph:
        version = await self._s.get(WorkflowTemplateVersion, template_version_id)
        if version is None:  # pragma: no cover - FK guarantees the row exists
            raise WorkflowEngineError(f"template version {template_version_id} vanished")
        return derive_index(version.definition)

    async def _tokens(self, instance_id: uuid.UUID) -> list[Token]:
        rows = (
            (
                await self._s.execute(
                    select(WorkflowToken)
                    .where(
                        WorkflowToken.instance_id == instance_id,
                        WorkflowToken.state.in_(_LIVE),
                    )
                    .order_by(WorkflowToken.node_key, WorkflowToken.entered_at, WorkflowToken.id)
                )
            )
            .scalars()
            .all()
        )
        return [
            Token(
                id=r.id,
                node_key=r.node_key,
                state=r.state,
                inbound_edge_key=r.inbound_edge_key,
            )
            for r in rows
        ]

    async def _apply(self, inst: WorkflowInstance, res: EngineResult) -> None:
        now = _dt.datetime.now(_dt.UTC)
        if res.consumed:
            await self._s.execute(
                update(WorkflowToken)
                .where(WorkflowToken.id.in_(res.consumed))
                .values(state=WorkflowTokenState.CONSUMED.value, left_at=now)
            )
        if res.parked:
            await self._s.execute(
                update(WorkflowToken)
                .where(WorkflowToken.id.in_(res.parked))
                .values(state=WorkflowTokenState.WAITING.value)
            )
        for node_key, inbound in res.spawned:
            self._s.add(
                WorkflowToken(
                    instance_id=inst.id,
                    node_key=node_key,
                    inbound_edge_key=inbound,
                    state=WorkflowTokenState.WAITING.value,
                )
            )
        if res.completed and inst.status == WorkflowInstanceStatus.RUNNING.value:
            inst.status = WorkflowInstanceStatus.COMPLETED.value
            inst.ended_at = now
        await self._s.flush()
