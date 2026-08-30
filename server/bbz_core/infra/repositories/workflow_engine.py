"""Workflow token engine — persistence, step completion, branch decisions.

Roadmap E05-08 / E05-09. The deterministic token flow lives in
:mod:`bbz_core.domain.workflow.engine`; this service loads the instance's token
state (plus the condition context and the operator decisions recorded so far),
runs the engine, and writes the resulting mutations **in one transaction**.
Every method commits its own transaction, so a crash either commits a whole
step or nothing — and re-running :meth:`advance_instance` from the persisted
token state is a no-op once the step is in (idempotent failover).

An XOR / OR split that the engine resolves from its rule-DSL conditions writes
a ``workflow_decisions`` row (``auto = true``) and a ``WORKFLOW_DECISION_MADE``
audit entry; when nothing resolves, the token parks and :meth:`decide` records
the operator's choice (``auto = false``) and resumes.

Task kinds (E05-10) are settled after every advance:

* ``manual`` / ``confirmation`` / ``documentation`` — the token stays parked
  until :meth:`complete_step` (an operator).
* ``timer`` — ``resume_at`` is stamped on the token; :meth:`fire_due_timers`
  (a worker) resumes it once due, so a restart never loses the deadline.
* ``integration_action`` / ``notification`` / ``event_update`` — exactly one
  ``external_action_outbox`` row is enqueued (stable ``dedupe_key``) and the
  token moves on; the side effect runs exactly-once via the dispatcher.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import AuditAction, AuditService
from bbz_core.domain.workflow import (
    DecisionMade,
    DerivedGraph,
    EngineResult,
    GraphNode,
    Token,
    derive_index,
)
from bbz_core.domain.workflow.engine import StepNotWaitingError, advance, resume_function
from bbz_core.domain.workflow.tasks import (
    AUTO_KINDS,
    TIMER_KINDS,
    outbox_action,
    step_dedupe_key,
    timer_seconds,
)
from bbz_core.infra.models.events import Event
from bbz_core.infra.models.workflow import WorkflowTemplateVersion
from bbz_core.infra.models.workflow_runtime import (
    WorkflowDecision,
    WorkflowInstance,
    WorkflowInstanceStatus,
    WorkflowTaskResult,
    WorkflowToken,
    WorkflowTokenState,
)
from bbz_core.infra.outbox import enqueue

_LIVE = (WorkflowTokenState.ACTIVE.value, WorkflowTokenState.WAITING.value)


class WorkflowEngineError(Exception):
    pass


class InstanceNotFoundError(WorkflowEngineError):
    pass


class StepNotAvailableError(WorkflowEngineError):
    """complete_step() was called for a node that has no step waiting."""


class DecisionNotAvailableError(WorkflowEngineError):
    """decide() was called for a connector with no branch decision pending."""


class InvalidDecisionError(WorkflowEngineError):
    """The decision does not name a valid branch set for this connector."""


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
        await self._drive(inst, graph, actor_id=None)
        await self._s.commit()
        return inst

    async def advance_instance(self, instance_id: uuid.UUID) -> WorkflowInstance:
        """Re-run the engine from the persisted token state (crash recovery)."""
        inst = await self._require(instance_id)
        if inst.status != WorkflowInstanceStatus.RUNNING.value:
            await self._s.commit()
            return inst
        graph = await self._graph(inst.template_version_id)
        await self._drive(inst, graph, actor_id=None)
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
            outcome = resume_function(
                graph,
                await self._tokens(instance_id),
                node_key,
                context=await self._context(inst),
                decisions=await self._decisions(instance_id),
            )
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
        await self._audit_step(instance_id, node_key, actor_id=actor_id)
        await self._apply(inst, outcome, actor_id=None)
        await self._settle(inst, graph)
        await self._s.commit()
        return inst

    async def decide(
        self,
        instance_id: uuid.UUID,
        connector_node_key: str,
        chosen_edge_keys: Iterable[str],
        *,
        actor_id: uuid.UUID | None = None,
    ) -> WorkflowInstance:
        """Record an operator's XOR / OR branch choice and resume the instance.

        Idempotent: a second call for the same connector is a no-op."""
        inst = await self._require(instance_id)
        graph = await self._graph(inst.template_version_id)
        node = _graph_node(graph, connector_node_key)
        if node is None or node.type != "connector" or node.connector_direction != "split":
            raise InvalidDecisionError(f"{connector_node_key!r} is not a branch connector")

        existing = (
            await self._s.execute(
                select(WorkflowDecision.id).where(
                    WorkflowDecision.instance_id == instance_id,
                    WorkflowDecision.connector_node_key == connector_node_key,
                )
            )
        ).first()
        if existing is not None:
            await self._s.commit()
            return inst

        out_keys = {e.key for e in graph.edges if e.from_key == connector_node_key}
        chosen = list(dict.fromkeys(chosen_edge_keys))
        if not chosen or not set(chosen) <= out_keys:
            raise InvalidDecisionError(f"branches {chosen} are not outgoing edges of {node.key!r}")
        if node.connector_type == "xor" and len(chosen) != 1:
            raise InvalidDecisionError("an XOR decision must pick exactly one branch")

        parked_id = (
            await self._s.execute(
                select(WorkflowToken.id).where(
                    WorkflowToken.instance_id == instance_id,
                    WorkflowToken.node_key == connector_node_key,
                    WorkflowToken.state == WorkflowTokenState.WAITING.value,
                )
            )
        ).scalar_one_or_none()
        if parked_id is None:
            raise DecisionNotAvailableError(
                f"no branch decision is pending at {connector_node_key!r}"
            )
        await self._s.execute(
            update(WorkflowToken)
            .where(WorkflowToken.id == parked_id)
            .values(state=WorkflowTokenState.ACTIVE.value)
        )

        self._s.add(
            WorkflowDecision(
                instance_id=instance_id,
                connector_node_key=connector_node_key,
                chosen_branches=chosen,
                auto=False,
                decided_by=actor_id,
            )
        )
        await self._audit_decision(
            instance_id, connector_node_key, chosen, actor_id=actor_id, auto=False
        )
        await self._drive(inst, graph, actor_id=None)
        await self._s.commit()
        return inst

    # -- internals -----------------------------------------------------------

    async def _drive(
        self, inst: WorkflowInstance, graph: DerivedGraph, *, actor_id: uuid.UUID | None
    ) -> None:
        outcome = advance(
            graph,
            await self._tokens(inst.id),
            context=await self._context(inst),
            decisions=await self._decisions(inst.id),
        )
        await self._apply(inst, outcome, actor_id=actor_id)
        await self._settle(inst, graph)

    async def _settle(self, inst: WorkflowInstance, graph: DerivedGraph) -> None:
        """Run the kind-specific handler for every freshly-parked function
        token — arming timers, dispatching auto actions — until the instance
        reaches a state that only an operator (or a due timer) can move on."""
        for _ in range(len(graph.nodes) + 5):
            rows = (
                (
                    await self._s.execute(
                        select(WorkflowToken).where(
                            WorkflowToken.instance_id == inst.id,
                            WorkflowToken.state == WorkflowTokenState.WAITING.value,
                        )
                    )
                )
                .scalars()
                .all()
            )
            auto_key: str | None = None
            armed = False
            for r in rows:
                node = _graph_node(graph, r.node_key)
                kind = node.function_kind if node is not None else None
                if kind in TIMER_KINDS and r.resume_at is None:
                    r.resume_at = _dt.datetime.now(_dt.UTC) + _dt.timedelta(
                        seconds=timer_seconds(node.props if node else None)
                    )
                    armed = True
                elif kind in AUTO_KINDS and auto_key is None:
                    if not await self._step_done(inst.id, r.node_key):
                        auto_key = r.node_key
            if auto_key is not None:
                await self._run_auto(inst, graph, auto_key)
                continue
            if armed:
                await self._s.flush()
            return
        raise WorkflowEngineError("task settling did not converge")  # pragma: no cover

    async def _run_auto(self, inst: WorkflowInstance, graph: DerivedGraph, node_key: str) -> None:
        node = _graph_node(graph, node_key)
        assert node is not None and node.function_kind is not None
        await enqueue(
            self._s,
            dedupe_key=step_dedupe_key(inst.id, node_key),
            action_type=outbox_action(node.function_kind),
            payload={
                "instance_id": str(inst.id),
                "node_key": node_key,
                "kind": node.function_kind,
                "props": node.props,
            },
        )
        self._s.add(
            WorkflowTaskResult(
                instance_id=inst.id,
                node_key=node_key,
                result={"dispatched": True, "kind": node.function_kind},
                completed_by=None,
            )
        )
        await self._audit_step(inst.id, node_key, actor_id=None, kind=node.function_kind)
        outcome = resume_function(
            graph,
            await self._tokens(inst.id),
            node_key,
            context=await self._context(inst),
            decisions=await self._decisions(inst.id),
        )
        await self._apply(inst, outcome, actor_id=None)

    async def fire_due_timers(self, *, now: _dt.datetime | None = None) -> int:
        """Resume every parked ``timer`` token whose ``resume_at`` has passed.

        A worker calls this on a schedule; because ``resume_at`` is persisted,
        a timer still fires at its deadline across a server restart. Commits."""
        now = now or _dt.datetime.now(_dt.UTC)
        rows = (
            (
                await self._s.execute(
                    select(WorkflowToken)
                    .where(
                        WorkflowToken.state == WorkflowTokenState.WAITING.value,
                        WorkflowToken.resume_at.is_not(None),
                        WorkflowToken.resume_at <= now,
                    )
                    .with_for_update(skip_locked=True)
                )
            )
            .scalars()
            .all()
        )
        fired = 0
        seen_instances: dict[uuid.UUID, tuple[WorkflowInstance, DerivedGraph]] = {}
        for r in rows:
            if r.instance_id not in seen_instances:
                inst = await self._require(r.instance_id)
                seen_instances[r.instance_id] = (inst, await self._graph(inst.template_version_id))
            inst, graph = seen_instances[r.instance_id]
            r.resume_at = None
            if inst.status != WorkflowInstanceStatus.RUNNING.value:
                continue
            if await self._step_done(inst.id, r.node_key):
                continue
            self._s.add(
                WorkflowTaskResult(
                    instance_id=inst.id, node_key=r.node_key, result={"timer": "elapsed"}
                )
            )
            await self._audit_step(inst.id, r.node_key, actor_id=None, kind="timer")
            outcome = resume_function(
                graph,
                await self._tokens(inst.id),
                r.node_key,
                context=await self._context(inst),
                decisions=await self._decisions(inst.id),
            )
            await self._apply(inst, outcome, actor_id=None)
            await self._settle(inst, graph)
            fired += 1
        await self._s.commit()
        return fired

    async def _step_done(self, instance_id: uuid.UUID, node_key: str) -> bool:
        row = (
            await self._s.execute(
                select(WorkflowTaskResult.id).where(
                    WorkflowTaskResult.instance_id == instance_id,
                    WorkflowTaskResult.node_key == node_key,
                )
            )
        ).first()
        return row is not None

    async def _audit_step(
        self,
        instance_id: uuid.UUID,
        node_key: str,
        *,
        actor_id: uuid.UUID | None,
        kind: str | None = None,
    ) -> None:
        after: dict[str, Any] = {"node_key": node_key, "instance_id": str(instance_id)}
        if kind is not None:
            after |= {"kind": kind, "auto": True}
        await AuditService(self._s).write(
            AuditAction.ACTION_STEP_COMPLETED,
            actor_user_id=actor_id,
            target_type="workflow_instance",
            target_id=str(instance_id),
            after=after,
        )

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

    async def _context(self, inst: WorkflowInstance) -> dict[str, Any]:
        event = await self._s.get(Event, inst.event_id)
        steps = (
            await self._s.execute(
                select(WorkflowTaskResult.id).where(WorkflowTaskResult.instance_id == inst.id)
            )
        ).all()
        ctx: dict[str, Any] = {"step_completed_count": len(steps), "operator_confirmed": False}
        if event is not None:  # pragma: no branch - FK guarantees the row
            ctx |= {
                "event_priority": event.priority,
                "status": event.status,
                "source": event.source,
                "bbz_id": str(event.bbz_id) if event.bbz_id else None,
                "workplace_id": str(event.workplace_id) if event.workplace_id else None,
            }
        return ctx

    async def _decisions(self, instance_id: uuid.UUID) -> dict[str, list[str]]:
        rows = (
            await self._s.execute(
                select(WorkflowDecision.connector_node_key, WorkflowDecision.chosen_branches).where(
                    WorkflowDecision.instance_id == instance_id
                )
            )
        ).all()
        return {ck: list(branches) for ck, branches in rows}

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

    async def _apply(
        self, inst: WorkflowInstance, res: EngineResult, *, actor_id: uuid.UUID | None
    ) -> None:
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
        await self._record_auto_decisions(inst.id, res.decisions)
        if res.completed and inst.status == WorkflowInstanceStatus.RUNNING.value:
            inst.status = WorkflowInstanceStatus.COMPLETED.value
            inst.ended_at = now
        await self._s.flush()

    async def _record_auto_decisions(
        self, instance_id: uuid.UUID, decisions: list[DecisionMade]
    ) -> None:
        for d in decisions:
            self._s.add(
                WorkflowDecision(
                    instance_id=instance_id,
                    connector_node_key=d.connector_node_key,
                    chosen_branches=list(d.chosen_edge_keys),
                    auto=True,
                    decided_by=None,
                )
            )
            await self._audit_decision(
                instance_id, d.connector_node_key, d.chosen_edge_keys, actor_id=None, auto=True
            )

    async def _audit_decision(
        self,
        instance_id: uuid.UUID,
        connector_node_key: str,
        chosen: Iterable[str],
        *,
        actor_id: uuid.UUID | None,
        auto: bool,
    ) -> None:
        await AuditService(self._s).write(
            AuditAction.WORKFLOW_DECISION_MADE,
            actor_user_id=actor_id,
            target_type="workflow_instance",
            target_id=str(instance_id),
            after={
                "connector_node_key": connector_node_key,
                "chosen_branches": list(chosen),
                "auto": auto,
            },
        )


def _graph_node(graph: DerivedGraph, key: str) -> GraphNode | None:
    return next((n for n in graph.nodes if n.key == key), None)
